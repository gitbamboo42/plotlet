"""Journal-only plot representation.

A plot as a flat, append-only list of events. Every user action is one
entry. The journal is a complete record — `from_journal(to_journal(fig))`
produces a figure that renders byte-identical to the original. That
round-trip is the correctness invariant.

Deliberately kept separate from `chart.py` / `_layout_engine.py`: the
journal is a different way to hold what the user built — one flat list
instead of a graph of Chart / Layout objects. The two must not blur.

Event shape:

    {"op": <name>, "nid": <int>, "args": <list>, "kwargs": <dict>}

Ops:
    "new_chart"    Data chart. kwargs: data, data_width, data_height,
                   margin, and aes (x/y/color/palette/...).
    "new_leaf"     Legend or diagram leaf. kwargs: leaf_kind,
                   canvas_width, canvas_height, margin, and any
                   leaf-specific state that isn't journaled elsewhere.
    "new_layout"   Layout node. kwargs: layout_kind ("h"/"v"/"grid"),
                   children (list of nids or None for empty grid cells),
                   grid_rows, grid_cols.
    "new_facet_grid" FacetGrid — a top-level recorder, expanded to the
                   grid-of-charts tree it denotes when the journal
                   lowers to the IR (`journal_to_ir`). kwargs: data,
                   by, col_wrap, share_x, share_y, chart_opts.
    <method>       Method call on the target node. `args` and `kwargs`
                   go straight to the method. Cross-node references
                   (attach_left(other), CircularCoordinate(inner=other),
                   legend sources) are encoded as {"$node": nid} and
                   resolved back on replay.

Node ids: opaque monotonic ints from a process-global counter. Two
journals never share ids by construction.

Rendering goes journal → IR → plot: at render time the journal is
lowered to the figure IR (`_ir.py`) — the per-node compiled form — and
the render half hydrates its private node tree from that
(`render/_nodes.py`) and runs the pipeline. Round-trip proves the
journal is complete; the IR is the surface for inspection and
programmatic transformation (`to_ir` / `from_ir`).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Journal:
    """Flat event list.

    Order is significant: a node's `new_*` event precedes any method
    event that targets it, and any node referenced as a Layout child /
    attachment / `coord.inner` gets its `new_*` before the reference.

    `root_nid` names which node in the journal is the plot root — set
    by `to_journal`; can't be inferred from the entries alone (an
    inner-coord chart or attachment may follow the root's `new_*`).
    """
    entries: list[dict] = field(default_factory=list)
    root_nid: int | None = None

    def append(self, op: str, nid: int,
               args: list | None = None,
               kwargs: dict | None = None) -> None:
        self.entries.append({
            "op": op,
            "nid": nid,
            "args": list(args) if args else [],
            "kwargs": dict(kwargs) if kwargs else {},
        })

    def to_dict(self) -> dict:
        """JSON-safe dict form. Walks entries via the JSON layer to
        envelope the remaining non-JSON-native types (tuple, set,
        date, datetime, DataFrameLite); plotlet envelopes ($node etc.)
        were already added at `to_journal` time."""
        from ._json_layer import json_safe
        return {
            "version": _JOURNAL_VERSION,
            "root_nid": self.root_nid,
            "entries": json_safe(self.entries),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Journal":
        from ._json_layer import json_hydrate
        ver = d.get("version")
        if ver != _JOURNAL_VERSION:
            raise ValueError(
                f"Journal.from_dict: unsupported version {ver!r}, "
                f"expected {_JOURNAL_VERSION}."
            )
        return cls(entries=json_hydrate(d["entries"]),
                   root_nid=d["root_nid"])


_JOURNAL_VERSION = 1


class JournalNode:
    """Handle wrapping (journal, root_nid). `to_svg()` lowers the
    journal to the figure IR (`_ir.py`) and renders it through the
    render half's seam.

    Users don't build JournalNodes directly — they come from
    `from_journal(...)`."""

    def __init__(self, journal: Journal, root_nid: int):
        self._journal = journal
        self._root_nid = root_nid

    def _to_ir(self):
        from ._ir import journal_to_ir
        return journal_to_ir(self._journal, root_nid=self._root_nid)

    def to_svg(self, *, clean: bool = False) -> str:
        return self._to_ir().to_svg(clean=clean)

    def to_html(self, full_page: bool = False) -> str:
        return self._to_ir().to_html(full_page=full_page)

    def __repr__(self) -> str:
        return (f"<JournalNode nid={self._root_nid} "
                f"entries={len(self._journal.entries)}>")


# ---------------------------------------------------------------------------
# to_journal — walk a Chart/Layout tree, emit a flat journal
# ---------------------------------------------------------------------------


def to_journal(root) -> Journal:
    """Serialize a tree-based Chart/Layout into a journal.

    The journal captures everything needed to rebuild an equivalent
    plot: construction state, composition topology, attachments,
    coord.inner sub-charts, insets, legend sources, FacetGrid
    identity, and every recorded method call in order.
    """
    from .facet import FacetGrid

    journal = Journal()
    nid_map: dict[int, int] = {}    # id(python_object) → nid
    # Per-journal counter — start at 1 so 0 can mean "unset". Local so two
    # journals of the same plot have identical nids and diffing is sane.
    nid_counter = itertools.count(1)

    def _nid_of(node) -> int:
        if id(node) not in nid_map:
            nid_map[id(node)] = next(nid_counter)
        return nid_map[id(node)]

    def _encode(value: Any) -> Any:
        """Envelope plotlet-typed values so the flat journal carries no
        hidden object pointers:
          - Chart / Layout / FacetGrid  → {"$node": nid}
          - Sectors                     → {"$sectors": ...}
          - Registered coord            → {"$coord": name, "kwargs": ...}
        Everything else (primitives, DataFrameLite, user dicts / lists)
        is passed through unchanged — pandas / numpy have already been
        normalized at the recorder boundary."""
        # Late import to avoid a cycle with chart.py at module load.
        from .chart import _Renderable
        from .sectors import Sectors
        if isinstance(value, _Renderable):
            _emit_node(value)
            return {"$node": _nid_of(value)}
        if isinstance(value, Sectors):
            return {"$sectors": _encode(value._to_dict())}
        from ._coord_registry import _COORD_REGISTRY
        if type(value).__name__ in _COORD_REGISTRY:
            return {
                "$coord": type(value).__name__,
                "kwargs": _encode(value._to_dict()),
            }
        if isinstance(value, dict):
            return {k: _encode(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_encode(v) for v in value]
        if isinstance(value, tuple):
            return tuple(_encode(v) for v in value)
        return value

    emitted: set[int] = set()

    def _emit_node(node) -> None:
        """Emit `node`'s new_* event and all its method events, in
        dependency order (children/attachments first)."""
        if id(node) in emitted:
            return
        emitted.add(id(node))
        nid = _nid_of(node)

        # Sub-nodes referenced by `node` need nids and create events
        # BEFORE `node`'s create event, so a `new_layout` referencing
        # children by nid can resolve them at replay time. Same for a
        # Chart's attach_* entries and legend sources.
        if getattr(node, "_is_parent", False):
            for child in node._children:
                if child is not None:
                    _emit_node(child)
        else:
            for entry in node._calls:
                if entry[0].startswith("attach_"):
                    for atch in entry[1]:
                        _emit_node(atch)
            for src in getattr(node, "_legend_sources", ()):
                _emit_node(src)

        # Coord.inner sub-charts live inside a `coordinate` entry —
        # encode them via _encode which recurses through _to_dict.
        # `_encode` also emits their new_* events when it walks them.

        if isinstance(node, FacetGrid):
            _emit_facet_grid(node, nid)
        elif getattr(node, "_is_parent", False):
            _emit_layout(node, nid)
        elif getattr(node, "_leaf_kind", "data") == "data":
            _emit_chart(node, nid)
        else:
            _emit_leaf(node, nid)

        # Method events (frame + artist + state calls). Sub-nodes
        # referenced in args/kwargs get their new_* emitted lazily via
        # `_encode` if not already done.
        for entry in node._calls:
            _emit_call(nid, entry)

        # Insets — `chart.inset(rect)` returns a fresh Chart stored in
        # `chart._insets` as `(rect, inset_chart)` pairs; NOT recorded
        # in `_calls`, so we emit synthetic `_inset_add` events after
        # the host's method events. Insets recurse: emit the inset
        # chart's `new_*` and methods first so it exists by the time
        # the host binds it.
        for rect, inset_chart in getattr(node, "_insets", ()):
            _emit_node(inset_chart)
            journal.append("_inset_add", nid,
                          kwargs={"rect": list(rect),
                                  "inset_nid": _nid_of(inset_chart)})

    def _emit_facet_grid(fg, nid: int) -> None:
        journal.append("new_facet_grid", nid, kwargs={
            "data": fg._data,
            "by": fg._by,
            "row": fg._row,
            "col": fg._col,
            "col_wrap": fg._col_wrap,
            "share_x": fg._share_x,
            "share_y": fg._share_y,
            "chart_opts": dict(fg._chart_opts),
        })

    def _emit_chart(chart, nid: int) -> None:
        aes = {k: v for k, v in chart._aes.items() if v is not None}
        journal.append("new_chart", nid, kwargs={
            "data": chart._data,
            "data_width": chart._orig_data_width,
            "data_height": chart._orig_data_height,
            "margin": dict(chart._margin),
            **aes,
        })

    def _emit_leaf(leaf, nid: int) -> None:
        # Non-data leaves — legend and diagram. Constructor state that
        # isn't journaled via _calls: canvas dims, legend metadata,
        # diagram inner SVG.
        kwargs = {
            "leaf_kind": leaf._leaf_kind,
            "canvas_width": leaf._canvas_width,
            "canvas_height": leaf._canvas_height,
            "margin": dict(leaf._margin),
        }
        if leaf._leaf_kind == "legend":
            # `_legend_names` has Chart-instance keys. Encode as pairs so
            # the flat journal carries no hidden object pointers as dict
            # keys; wrap Chart keys in the `$node` envelope so a decoder
            # can't confuse them with any other int-valued key.
            names_pairs = [
                [{"$node": _nid_of(k)} if hasattr(k, "_is_parent") else k, v]
                for k, v in leaf._legend_names.items()
            ]
            kwargs.update({
                "legend_sources": [_nid_of(s) for s in leaf._legend_sources],
                "legend_names_pairs": names_pairs,
                "legend_group_by_chart": leaf._legend_group_by_chart,
                "legend_valign": leaf._legend_valign,
                "legend_ncols": leaf._legend_ncols,
                "legend_user_width": leaf._legend_user_width,
                "legend_user_height": leaf._legend_user_height,
                "legend_gap": leaf._legend_gap,
            })
        if leaf._leaf_kind == "diagram":
            kwargs["diagram_inner"] = leaf._diagram_inner
        journal.append("new_leaf", nid, kwargs=kwargs)

    def _emit_layout(layout, nid: int) -> None:
        children_nids = [
            _nid_of(c) if c is not None else None
            for c in layout._children
        ]
        journal.append("new_layout", nid, kwargs={
            "layout_kind": layout._layout_kind,
            "children": children_nids,
            "grid_rows": layout._grid_rows,
            "grid_cols": layout._grid_cols,
        })

    def _emit_call(nid: int, entry) -> None:
        """A `_calls` entry — `(name, args, kwargs)`, always a user
        action. Artist frame defaults are never recorded; `_replay`
        regenerates them from the artist call on every render."""
        name, args, kwargs = entry
        journal.append(name, nid,
                       args=[_encode(a) for a in args],
                       kwargs={k: _encode(v) for k, v in kwargs.items()})

    _emit_node(root)
    journal.root_nid = nid_map[id(root)]
    return journal


# ---------------------------------------------------------------------------
# from_journal — build a JournalNode from a journal (Journal or plain list)
# ---------------------------------------------------------------------------


def from_journal(events) -> JournalNode:
    """Construct a `JournalNode` from a `Journal` (or its raw entries).

    The journal names its own root; callers who pass a plain list must
    already know the root nid and pass a `Journal(entries=..., root_nid=...)`.
    """
    if isinstance(events, Journal):
        journal = events
    else:
        journal = Journal(entries=list(events))
    if journal.root_nid is None:
        raise ValueError(
            "from_journal: journal has no root_nid. "
            "Set Journal.root_nid explicitly, or pass a Journal from to_journal()."
        )
    return JournalNode(journal, journal.root_nid)


def to_json(node) -> dict:
    """Serialize a plot to a JSON-safe dict. `json.dumps(...)` produces
    the string form. Round-trips through `from_json`."""
    return to_journal(node).to_dict()


def from_json(blob: dict) -> JournalNode:
    """Inverse of `to_json`. Returns a `JournalNode` that renders to
    the same SVG as the original."""
    return from_journal(Journal.from_dict(blob))


# Rendering lives behind the render half's seam: the journal lowers to
# the figure IR (`journal_to_ir` in `_ir.py`), and `render.render_svg`
# hydrates its private node tree from the IR. Contract: `docs/IR.md`.
