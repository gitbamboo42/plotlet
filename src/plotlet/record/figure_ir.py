"""Figure IR — the middle layer of the journal → IR → plot pipeline.

Three representations of one plot, ordered by distance from the user:

    journal   flat event log of user actions, in the order they happened
              (`journal.py`). "What the user did."
    IR        per-node structured form: a table of nodes in dependency
              order, each carrying its construction state, its method
              ops, and its insets. "What the figure is."
    plot      the rendered SVG. The render half hydrates its private
              node tree from the IR (`render.hydrate`) and runs
              the pipeline over it. This is the only render path —
              `Chart.to_svg()` itself lowers through the IR — so output
              is byte-identical however a figure reaches the renderer.

The journal is the recording format — append-only, interleaved, one
entry per action. The IR is the *compiled* form: events grouped by the
node they target, cross-references resolved into an explicit dependency
order, creation ops normalized into a `kind` + `init` pair. Tools that
want to inspect or transform a figure (diffing, validation, programmatic
edits) work on the IR; tools that want provenance work on the journal.
Lowering is loss-free both ways: `ir_to_journal(journal_to_ir(j))`
replays to the same SVG as `j`. One normalization: a FacetGrid journals
as a single `new_facet_grid` event (provenance — "what the user did"),
and lowering expands it to the grid of charts it denotes, so the IR and
everything downstream see only the four core node kinds.

IR node shape:

    IRNode(
        nid,      # the journal's node id, kept for cross-referencing
        kind,     # "chart" | "legend" | "diagram" | "layout"
        init,     # construction kwargs (the new_* event's payload;
                  # `leaf_kind` is lifted into `kind`)
        ops,      # [{"op": name, "args": [...], "kwargs": {...}}, ...]
                  # in original per-node order
        insets,   # [{"rect": [x, y, w, h], "chart_nid": nid}, ...]
    )

`FigureIR.nodes` is dependency-ordered: every nid a node references —
layout children, legend sources, `{"$node": nid}` envelopes in op args,
inset charts — appears earlier in the list. Hydrating the render tree is
therefore a single forward pass. The order is derived by depth-first
walk from the root, so two IRs of the same figure list nodes identically.

Value envelopes (`{"$node": nid}`, `{"$coord": ...}`, `{"$sectors": ...}`)
are shared with the journal — the IR stores values exactly as
`to_journal` encoded them, and `_json_layer._decode` resolves them back
at hydration time.

A second lowering stage lives in `render/resolved_ir.py`: `FigureIR.resolve()`
returns the resolved IR (trained scales, baked palettes, effective
margins) — the stage the render path itself passes through, so
inspecting it and rendering the figure are two views of one
resolution.

The full contract — node kinds, init keys, op normalization, envelope
forms, ordering — is written down in `docs/ARCHITECTURE.md`; `render.validate`
enforces it at every render entry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._json_layer import _decode

_IR_VERSION = 1

# new_* journal op → IR node kind (new_leaf splits by its leaf_kind;
# new_facet_grid never reaches the node table — `journal_to_ir` expands
# it before grouping).
_CREATE_OPS = {
    "new_chart": "chart",
    "new_layout": "layout",
}
_KIND_TO_CREATE = {v: k for k, v in _CREATE_OPS.items()}


@dataclass
class IRNode:
    """One figure node in compiled form. See module docstring for the
    field contract."""
    nid: int
    kind: str
    init: dict
    ops: list = field(default_factory=list)
    insets: list = field(default_factory=list)


@dataclass
class FigureIR:
    """Compiled figure: dependency-ordered node table plus the root nid.

    Renderable directly — `to_svg()` hands this IR to the render half
    (`render.render_svg`). JSON round-trips via
    `to_dict` / `from_dict` (the `_json_layer` envelopes every
    non-JSON-native value type, same as the journal's JSON form).
    """
    nodes: list[IRNode]
    root_nid: int

    def to_svg(self, *, clean: bool = False) -> str:
        from ..render import render_svg
        return render_svg(self, clean=clean)

    def to_html(self, full_page: bool = False) -> str:
        svg = self.to_svg()
        if full_page:
            return ('<!doctype html><html><head><meta charset="utf-8">'
                    '<title>plotlet</title></head>'
                    f'<body style="margin:24px">{svg}</body></html>')
        return svg

    def resolve(self):
        """Lower one step further: the resolved IR (`render/resolved_ir.py`)
        — trained scales, baked palettes, effective margins. This is
        the render pipeline's own middle stage (`to_svg()` goes through
        it), inspectable via `.root` and renderable via `.to_svg()`.
        One-way — not a round-trip peer."""
        from ..render import resolve
        return resolve(self)

    def validate(self) -> "FigureIR":
        """Check this IR against the render contract (`docs/ARCHITECTURE.md`)
        without rendering — useful when hand-authoring or transforming
        IRs. Raises `ValueError` on the first violation; returns `self`
        so calls chain. Rendering validates implicitly."""
        from ..render import validate
        validate(self)
        return self

    def to_dict(self) -> dict:
        """JSON-safe dict form — `json.dumps(...)` produces the string
        form; `FigureIR.from_dict` is the inverse."""
        from .._json_layer import json_safe
        return {
            "version": _IR_VERSION,
            "root_nid": self.root_nid,
            "nodes": [{
                "nid": n.nid,
                "kind": n.kind,
                "init": json_safe(n.init),
                "ops": json_safe(n.ops),
                "insets": json_safe(n.insets),
            } for n in self.nodes],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FigureIR":
        from .._json_layer import json_hydrate
        ver = d.get("version")
        if ver != _IR_VERSION:
            raise ValueError(
                f"FigureIR.from_dict: unsupported version {ver!r}, "
                f"expected {_IR_VERSION}."
            )
        nodes = [IRNode(
            nid=nd["nid"],
            kind=nd["kind"],
            init=json_hydrate(nd["init"]),
            ops=json_hydrate(nd["ops"]),
            insets=json_hydrate(nd["insets"]),
        ) for nd in d["nodes"]]
        return cls(nodes=nodes, root_nid=d["root_nid"])

    def __repr__(self) -> str:
        return (f"<FigureIR root_nid={self.root_nid} "
                f"nodes={len(self.nodes)}>")


# ---------------------------------------------------------------------------
# journal → IR
# ---------------------------------------------------------------------------


def journal_to_ir(journal, root_nid: int | None = None) -> FigureIR:
    """Lower a `Journal` to a `FigureIR`.

    Two passes: group the flat entries by target nid, then order the
    grouped nodes depth-first from the root so every reference points
    backwards. Grouping a node's ops together is safe by construction —
    `to_journal` already emits each node's events as one contiguous run
    relative to anything that references it (children before parents,
    attachments and legend sources before the entry that names them).

    A `new_facet_grid` root is expanded before grouping — facets are
    recording-side sugar, and the IR carries only core node kinds.
    """
    if root_nid is None:
        root_nid = journal.root_nid
    if root_nid is None:
        raise ValueError(
            "journal_to_ir: journal has no root_nid. "
            "Set Journal.root_nid explicitly, or pass a Journal from to_journal()."
        )

    # Facet lowering — rebuild the FacetGrid recorder from its events,
    # expand it to the grid-of-charts tree it denotes, and lower that.
    # Expansion is deterministic (first-seen group order), so the
    # rendered SVG is unchanged.
    if any(e["nid"] == root_nid and e["op"] == "new_facet_grid"
           for e in journal.entries):
        from .journal import to_journal
        return journal_to_ir(to_journal(_expand_facet(journal, root_nid)))

    nodes: dict[int, IRNode] = {}
    for entry in journal.entries:
        op = entry["op"]
        nid = entry["nid"]
        if op == "new_facet_grid":
            raise ValueError(
                "journal_to_ir: new_facet_grid may only appear as the "
                "journal root — facets are recording-side sugar, expanded "
                "to a grid of charts at lowering."
            )
        if op in _CREATE_OPS:
            nodes[nid] = IRNode(nid, _CREATE_OPS[op], dict(entry["kwargs"]))
        elif op == "new_leaf":
            init = dict(entry["kwargs"])
            kind = init.pop("leaf_kind")
            nodes[nid] = IRNode(nid, kind, init)
        elif op == "_inset_add":
            kw = entry["kwargs"]
            nodes[nid].insets.append({
                "rect": list(kw["rect"]),
                "chart_nid": kw["inset_nid"],
            })
        else:
            nodes[nid].ops.append({
                "op": op,
                "args": entry.get("args", []),
                "kwargs": entry.get("kwargs", {}),
            })

    root_nid = _wrap_root(nodes, root_nid)

    # Dependency order: DFS from the root, dependencies first. The
    # journal guarantees the reference graph is acyclic (an entry can
    # only reference an already-created node), so no cycle check.
    ordered: list[IRNode] = []
    seen: set[int] = set()

    def _visit(nid: int) -> None:
        if nid in seen:
            return
        seen.add(nid)
        node = nodes[nid]
        for ref in _node_refs(node):
            _visit(ref)
        ordered.append(node)

    _visit(root_nid)
    # Anything unreachable from the root (shouldn't occur for journals
    # from `to_journal`, but a hand-built journal may carry extras) is
    # kept, in first-created order, so lowering stays loss-free.
    for nid in nodes:
        _visit(nid)

    return FigureIR(nodes=ordered, root_nid=root_nid)


def _is_container_coord_op(op: dict) -> bool:
    """True when `op` is a `coordinate` call carrying a container-strategy
    coord — one that owns the whole composition render via
    `render_layout` (e.g. `CircularCoordinate`). Values arrive as
    `{"$coord": name, "container": bool}` envelopes from `to_journal`,
    which stamps the flag from the live class at record time; a live
    coord object (hand-built journal) is duck-checked directly. Reading
    the flag instead of resolving the name keeps op *placement* (which
    node carries `coordinate` / `title`) a function of the blob alone.
    A missing flag reads False here — `render.validate` requires it and
    cross-checks it against the registered class, so the mismatch is
    reported there, with context."""
    if op["op"] != "coordinate" or not op["args"]:
        return False
    coord = op["args"][0]
    if isinstance(coord, dict) and "$coord" in coord:
        return coord.get("container") is True
    return hasattr(coord, "render_layout")


def _wrap_root(nodes: dict, root_nid: int) -> int:
    """Canonicalize the root: every IR root is a layout node. A lone
    leaf (chart / legend / diagram) wraps in a 1×1 `"h"` layout, so the
    render half sees one shape — the same one users write by hand as
    `pt.grid([[c]])` — and consumers get a single invariant instead of
    a leaf-or-layout root union.

    A chart root additionally hoists its composition-level ops onto the
    wrapper. The recorder keeps the order-free chart-level API
    (`c.sectors(...)`, `c.coordinate(...)` return `self`); this pass is
    where the sugar lowers away — composition-level state lives on a
    layout, never on a chart.

    Hoist rule: a container-strategy `coordinate` (one whose coord
    class defines `render_layout`) hoists `title` + `coordinate` +
    `sectors` (the overlay path suppresses leaf chrome, so the title
    needs its layout-level home, and its inner-disc inheritance reads
    the layout's calls); otherwise just `sectors` (the rect path
    renders leaf chrome normally — panel titles stay panel titles).
    Non-container coordinates are per-panel point transforms and stay
    on the chart.

    Only the root wraps. A chart inside a layout already has a layout
    home for composition state (the sectors cascade), and `pt.grid`
    cells are charts by API contract — the rect engine's grid passes
    assume leaf cells. Charts referenced as attachments, insets, coord
    inners, or legend sources are sub-panel content — their own
    `sectors` (e.g. an inner chart opting out of inheritance) stay
    panel-level. Mutates `nodes` in place; returns the (possibly new)
    root nid. The wrapper nid mints deterministically above the
    journal's max, so same journal → same IR holds."""
    node = nodes[root_nid]
    if node.kind == "layout":
        return root_nid
    hoisted: list = []
    if node.kind == "chart":
        has_container = any(_is_container_coord_op(op) for op in node.ops)
        hoisted_names = (("title", "coordinate", "sectors") if has_container
                         else ("sectors",))
        hoisted = [op for op in node.ops if op["op"] in hoisted_names]
        node.ops = [op for op in node.ops if op["op"] not in hoisted_names]
    wrapper_nid = max(nodes) + 1
    nodes[wrapper_nid] = IRNode(
        nid=wrapper_nid, kind="layout",
        init={"layout_kind": "h", "children": [root_nid],
              "grid_rows": None, "grid_cols": None},
        ops=hoisted,
    )
    return wrapper_nid


def _node_refs(node: IRNode) -> list[int]:
    """Every nid `node` references, in deterministic encounter order.

    References take three forms: raw-int fields whose meaning is
    positional (`children` on a layout, `legend_sources` on a legend,
    `chart_nid` on an inset) and `{"$node": nid}` envelopes anywhere in
    init / op values (attachments, coord inners, legend name keys)."""
    refs: list[int] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            if "$node" in value and len(value) == 1:
                refs.append(value["$node"])
                return
            for v in value.values():
                _walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                _walk(v)

    if node.kind == "layout":
        refs.extend(c for c in node.init.get("children", []) if c is not None)
    if node.kind == "legend":
        refs.extend(node.init.get("legend_sources", []))
    _walk(node.init)
    for op in node.ops:
        _walk(op["args"])
        _walk(op["kwargs"])
    refs.extend(ins["chart_nid"] for ins in node.insets)
    return refs


def _expand_facet(journal, root_nid: int):
    """Rebuild the `FacetGrid` recorder from its journal events and
    expand it to the Chart tree it denotes. A facet op can't
    meaningfully reference another node, so envelopes decode with an
    empty nid table."""
    from .facet import FacetGrid
    fg = None
    for entry in journal.entries:
        if entry["nid"] != root_nid:
            continue
        if entry["op"] == "new_facet_grid":
            kw = {k: _decode(v, {}) for k, v in entry["kwargs"].items()}
            fg = FacetGrid(kw["data"], by=kw["by"],
                           row=kw["row"], col=kw["col"],
                           col_wrap=kw["col_wrap"],
                           share_x=kw["share_x"], share_y=kw["share_y"],
                           chart_opts=kw["chart_opts"])
        else:
            getattr(fg, entry["op"])(
                *[_decode(a, {}) for a in entry.get("args", [])],
                **{k: _decode(v, {})
                   for k, v in entry.get("kwargs", {}).items()})
    return fg._materialize()


# ---------------------------------------------------------------------------
# IR → journal (flatten back — lowering is loss-free both ways)
# ---------------------------------------------------------------------------


def ir_to_journal(ir: FigureIR):
    """Flatten a `FigureIR` back into a `Journal`. Nodes emit in the
    IR's dependency order — create event, then ops, then insets — which
    is a valid journal ordering (every reference resolves backwards)."""
    from .journal import Journal
    journal = Journal(root_nid=ir.root_nid)
    for n in ir.nodes:
        if n.kind in ("legend", "diagram"):
            journal.append("new_leaf", n.nid,
                           kwargs={"leaf_kind": n.kind, **n.init})
        elif n.kind in _KIND_TO_CREATE:
            journal.append(_KIND_TO_CREATE[n.kind], n.nid, kwargs=n.init)
        else:
            raise ValueError(f"ir_to_journal: unknown node kind {n.kind!r}")
        for op in n.ops:
            journal.append(op["op"], n.nid,
                           args=op["args"], kwargs=op["kwargs"])
        for ins in n.insets:
            journal.append("_inset_add", n.nid,
                           kwargs={"rect": list(ins["rect"]),
                                   "inset_nid": ins["chart_nid"]})
    return journal


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def to_ir(node) -> FigureIR:
    """Compile a plot to its `FigureIR`. Accepts a `Chart` / `Layout` /
    `FacetGrid` (journaled first via `to_journal`), a `Journal`, or a
    `JournalNode`."""
    from .journal import Journal, JournalNode, to_journal
    if isinstance(node, FigureIR):
        return node
    if isinstance(node, JournalNode):
        return journal_to_ir(node._journal, root_nid=node._root_nid)
    if isinstance(node, Journal):
        return journal_to_ir(node)
    return journal_to_ir(to_journal(node))


def from_ir(blob) -> FigureIR:
    """Hydrate a `FigureIR` from its `to_dict()` form (or pass a
    `FigureIR` through). The result renders directly via `.to_svg()`."""
    if isinstance(blob, FigureIR):
        return blob
    return FigureIR.from_dict(blob)

