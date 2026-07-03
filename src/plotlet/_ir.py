"""Figure IR — the middle layer of the journal → IR → plot pipeline.

Three representations of one plot, ordered by distance from the user:

    journal   flat event log of user actions, in the order they happened
              (`_journal.py`). "What the user did."
    IR        per-node structured form: a table of nodes in dependency
              order, each carrying its construction state, its method
              ops, and its insets. "What the figure is."
    plot      the rendered SVG. The IR materializes the same Chart /
              Layout objects the tree path would build and renders
              through the existing pipeline, so output is byte-identical
              to the original figure.

The journal is the recording format — append-only, interleaved, one
entry per action. The IR is the *compiled* form: events grouped by the
node they target, cross-references resolved into an explicit dependency
order, creation ops normalized into a `kind` + `init` pair. Tools that
want to inspect or transform a figure (diffing, validation, programmatic
edits) work on the IR; tools that want provenance work on the journal.
Lowering is loss-free both ways: `ir_to_journal(journal_to_ir(j))`
replays to the same SVG as `j`.

IR node shape:

    IRNode(
        nid,      # the journal's node id, kept for cross-referencing
        kind,     # "chart" | "legend" | "diagram" | "layout" | "facet_grid"
        init,     # construction kwargs (the new_* event's payload;
                  # `leaf_kind` is lifted into `kind`)
        ops,      # [{"op": name, "args": [...], "kwargs": {...}}, ...]
                  # in original per-node order
        insets,   # [{"rect": [x, y, w, h], "chart_nid": nid}, ...]
    )

`FigureIR.nodes` is dependency-ordered: every nid a node references —
layout children, legend sources, `{"$node": nid}` envelopes in op args,
inset charts — appears earlier in the list. Materialization is therefore
a single forward pass. The order is derived by depth-first walk from the
root, so two IRs of the same figure list nodes identically.

Value envelopes (`{"$node": nid}`, `{"$coord": ...}`, `{"$sectors": ...}`)
are shared with the journal — the IR stores values exactly as
`to_journal` encoded them, and `_decode` here resolves them back at
materialization time.

A second lowering stage lives in `_ir_resolved.py`: `FigureIR.resolve()`
projects the figure into a pre-layout render plan (resolved scales,
baked palettes, effective margins) for inspection and tooling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_IR_VERSION = 1

# new_* journal op → IR node kind (new_leaf splits by its leaf_kind).
_CREATE_OPS = {
    "new_chart": "chart",
    "new_layout": "layout",
    "new_facet_grid": "facet_grid",
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

    Renderable directly — `to_svg()` materializes the Chart / Layout
    tree and renders through the existing pipeline. JSON round-trips via
    `to_dict` / `from_dict` (the `_json_layer` envelopes every
    non-JSON-native value type, same as the journal's JSON form).
    """
    nodes: list[IRNode]
    root_nid: int

    def to_svg(self, *, clean: bool = False) -> str:
        return _materialize(self, self.root_nid).to_svg(clean=clean)

    def to_html(self, full_page: bool = False) -> str:
        return _materialize(self, self.root_nid).to_html(full_page=full_page)

    def resolve(self):
        """Lower one step further: the resolved IR (`_ir_resolved.py`)
        — a pre-layout render plan with resolved scales, baked
        palettes, and effective margins. A projection for inspection
        and tooling, not a round-trip peer."""
        from ._ir_resolved import resolve_ir
        return resolve_ir(self)

    def to_dict(self) -> dict:
        """JSON-safe dict form — `json.dumps(...)` produces the string
        form; `FigureIR.from_dict` is the inverse."""
        from ._json_layer import json_safe
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
        from ._json_layer import json_hydrate
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
    """
    if root_nid is None:
        root_nid = journal.root_nid
    if root_nid is None:
        raise ValueError(
            "journal_to_ir: journal has no root_nid. "
            "Set Journal.root_nid explicitly, or pass a Journal from to_journal()."
        )

    nodes: dict[int, IRNode] = {}
    for entry in journal.entries:
        op = entry["op"]
        nid = entry["nid"]
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


# ---------------------------------------------------------------------------
# IR → journal (flatten back — lowering is loss-free both ways)
# ---------------------------------------------------------------------------


def ir_to_journal(ir: FigureIR):
    """Flatten a `FigureIR` back into a `Journal`. Nodes emit in the
    IR's dependency order — create event, then ops, then insets — which
    is a valid journal ordering (every reference resolves backwards)."""
    from ._journal import Journal
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
# IR → plot (materialize Chart/Layout objects, render via the tree path)
# ---------------------------------------------------------------------------


def _materialize(ir: FigureIR, root_nid: int):
    """Single forward pass over the dependency-ordered node table:
    construct each node, apply its ops in order, bind its insets.
    Envelopes in values resolve to real objects on demand."""
    from .chart import Chart, Layout

    nid_to_node: dict[int, object] = {}

    def _decode(value: Any) -> Any:
        if isinstance(value, dict):
            if "$node" in value and len(value) == 1:
                return nid_to_node[value["$node"]]
            if "$coord" in value:
                from ._coord_registry import _COORD_REGISTRY
                cls = _COORD_REGISTRY[value["$coord"]]
                return cls._from_dict(_decode(value.get("kwargs", {})))
            if "$sectors" in value:
                from .sectors import Sectors
                return Sectors._from_dict(_decode(value["$sectors"]))
            return {k: _decode(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_decode(v) for v in value]
        if isinstance(value, tuple):
            return tuple(_decode(v) for v in value)
        return value

    for n in ir.nodes:
        kwargs = {k: _decode(v) for k, v in n.init.items()}

        if n.kind == "chart":
            # `Chart.__init__` accepts only field-state kwargs (see
            # chart.py). `init` carries exactly those — method-sugar
            # kwargs live on the `chart()` factory and appear in the
            # IR as ops, not as construction state.
            nid_to_node[n.nid] = Chart(**kwargs)
        elif n.kind in ("legend", "diagram"):
            nid_to_node[n.nid] = _materialize_leaf(n.kind, kwargs, nid_to_node)
        elif n.kind == "layout":
            children = [nid_to_node[c] if c is not None else None
                        for c in kwargs["children"]]
            layout = Layout(kwargs["layout_kind"], children)
            if kwargs.get("grid_rows") is not None:
                layout._grid_rows = kwargs["grid_rows"]
            if kwargs.get("grid_cols") is not None:
                layout._grid_cols = kwargs["grid_cols"]
            nid_to_node[n.nid] = layout
        elif n.kind == "facet_grid":
            from .facet import FacetGrid
            nid_to_node[n.nid] = FacetGrid(
                kwargs["data"], kwargs["by"],
                col_wrap=kwargs["col_wrap"],
                share_x=kwargs["share_x"],
                share_y=kwargs["share_y"],
                chart_opts=kwargs["chart_opts"],
            )
        else:
            raise ValueError(f"FigureIR: unknown node kind {n.kind!r}")

        obj = nid_to_node[n.nid]

        # Method ops — go through the normal recorder path. Any
        # frame_defaults an artist injects regenerate here, so the IR
        # (like the journal) deliberately doesn't carry them.
        for op in n.ops:
            method = getattr(obj, op["op"])
            method(*[_decode(a) for a in op["args"]],
                   **{k: _decode(v) for k, v in op["kwargs"].items()})

        # Insets bind after the host's ops, matching journal order
        # (`to_journal` emits `_inset_add` after all method events).
        for ins in n.insets:
            obj._attach_inset(tuple(ins["rect"]),
                              nid_to_node[ins["chart_nid"]])

    return nid_to_node[root_nid]


def _materialize_leaf(kind: str, kwargs: dict, nid_to_node: dict):
    """Recreate a legend or diagram leaf. Non-data leaves go through
    `Chart._new_sized_leaf`, then per-kind state gets restored."""
    from .chart import Chart
    leaf = Chart._new_sized_leaf(
        canvas_width=kwargs["canvas_width"],
        canvas_height=kwargs["canvas_height"],
        leaf_kind=kind,
        margin=kwargs.get("margin"),
    )
    if kind == "legend":
        leaf._legend_sources = [nid_to_node[n]
                                for n in kwargs.get("legend_sources", [])]
        leaf._legend_names = dict(kwargs.get("legend_names_pairs", []))
        leaf._legend_group_by_chart = kwargs.get("legend_group_by_chart", True)
        leaf._legend_valign = kwargs.get("legend_valign")
        leaf._legend_user_width = kwargs.get("legend_user_width")
        leaf._legend_user_height = kwargs.get("legend_user_height")
        leaf._legend_gap = kwargs.get("legend_gap")
    if kind == "diagram":
        leaf._diagram_inner = kwargs.get("diagram_inner")
    return leaf


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def to_ir(node) -> FigureIR:
    """Compile a plot to its `FigureIR`. Accepts a `Chart` / `Layout` /
    `FacetGrid` (journaled first via `to_journal`), a `Journal`, or a
    `JournalNode`."""
    from ._journal import Journal, JournalNode, to_journal
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
