"""FigureIR validation — the contract check at the render seam.

An IR that reaches the render half may be hand-authored or loaded from
JSON, so nothing the recorder normally guarantees can be assumed here.
`validate` walks the node table once and raises `ValueError` with an
actionable message on the first violation; `hydrate` calls it at entry,
so every render path is covered. The checks mirror the contract spelled
out in `docs/IR.md`:

  * the node table is non-empty, nids are unique, the root nid exists
  * every kind is in the render vocabulary (chart / legend / diagram /
    layout) and carries its required init keys
  * every reference — layout children, legend sources, inset charts,
    `{"$node": ...}` envelopes — resolves to a node *earlier* in the
    table (dependency order, the property hydration relies on)
  * references are kind-appropriate: insets live on leaf nodes and
    target chart nodes; legend sources are leaf nodes
  * value envelopes are well-formed and `{"$coord": ...}` names resolve
    in the coord registry
  * op names resolve: chart-family ops against the artist registry ∪
    the frame-method set ∪ `attach_*`; layout ops against the
    materialized ∪ passthrough sets

Interpretation is registry-relative by design — an IR referencing an
extension artist or a custom coord validates only once the module
registering it has been imported. JSON-level concerns (the `version`
field, `_json_layer` envelope decoding) are enforced upstream in
`FigureIR.from_dict`, before a `FigureIR` exists to validate.
"""
from __future__ import annotations

_KINDS = ("chart", "legend", "diagram", "layout")
_LAYOUT_KINDS = ("h", "v", "grid")
_MARGIN_SIDES = ("left", "right", "top", "bottom")
_ATTACH_OPS = frozenset({
    "attach_left", "attach_right", "attach_above", "attach_below",
})


def _err(msg: str) -> ValueError:
    return ValueError(f"invalid FigureIR: {msg}")


def _chart_op_ok(name: str) -> bool:
    from ..registry import get_artist
    from .core import _FRAME_OPS
    return (name in _FRAME_OPS or name in _ATTACH_OPS
            or get_artist(name) is not None)


def _layout_op_ok(name: str) -> bool:
    from ._nodes import _LAYOUT_MATERIALIZED, _LAYOUT_PASSTHROUGH
    return name in _LAYOUT_MATERIALIZED or name in _LAYOUT_PASSTHROUGH


def _check_values(value, kinds: dict, where: str) -> None:
    """Walk one init / op value: every `{"$node"}` envelope must point at
    an earlier node, `{"$coord"}` names must resolve, and both must be
    well-formed. Containers recurse; everything else passes."""
    if isinstance(value, dict):
        if "$node" in value:
            if len(value) != 1 or not isinstance(value["$node"], int):
                raise _err(
                    f"{where}: malformed $node envelope {value!r} — "
                    f"expected exactly {{'$node': <int nid>}}."
                )
            if value["$node"] not in kinds:
                raise _err(
                    f"{where}: $node envelope references node "
                    f"{value['$node']}, which is not defined earlier in "
                    f"the table (nodes must be in dependency order)."
                )
            return
        if "$coord" in value:
            name = value["$coord"]
            if not isinstance(name, str):
                raise _err(
                    f"{where}: malformed $coord envelope {value!r} — "
                    f"the value must be the registered coord class name."
                )
            from .._coord_registry import resolve_coord
            try:
                resolve_coord(name)
            except KeyError as e:
                raise _err(f"{where}: {e.args[0]}") from None
            _check_values(value.get("kwargs", {}), kinds, where)
            return
        if "$sectors" in value:
            if not isinstance(value["$sectors"], dict):
                raise _err(
                    f"{where}: malformed $sectors envelope {value!r} — "
                    f"the payload must be the Sectors dict form."
                )
            _check_values(value["$sectors"], kinds, where)
            return
        for v in value.values():
            _check_values(v, kinds, where)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _check_values(v, kinds, where)


def _check_init(node, kinds: dict) -> None:
    where = f"node {node.nid} ({node.kind}) init"
    if not isinstance(node.init, dict):
        raise _err(f"{where}: expected a dict, got {type(node.init).__name__}.")

    margin = node.init.get("margin")
    if margin is not None:
        if (not isinstance(margin, dict)
                or any(s not in margin for s in _MARGIN_SIDES)):
            raise _err(
                f"{where}: margin must be a dict with keys "
                f"{list(_MARGIN_SIDES)}; got {margin!r}."
            )

    if node.kind in ("legend", "diagram"):
        for key in ("canvas_width", "canvas_height"):
            if key not in node.init:
                raise _err(
                    f"{where}: {node.kind} nodes require {key!r} — the "
                    f"canvas is their dimensional primitive."
                )

    if node.kind == "legend":
        for src in node.init.get("legend_sources", []):
            if src not in kinds:
                raise _err(
                    f"{where}: legend_sources references node {src}, "
                    f"which is not defined earlier in the table."
                )
            if kinds[src] == "layout":
                raise _err(
                    f"{where}: legend_sources references node {src}, a "
                    f"layout — sources must be leaf nodes (the factory "
                    f"rule: leaf charts, not composed parents)."
                )

    if node.kind == "layout":
        lk = node.init.get("layout_kind")
        if lk not in _LAYOUT_KINDS:
            raise _err(
                f"{where}: layout_kind must be one of {list(_LAYOUT_KINDS)}; "
                f"got {lk!r}."
            )
        children = node.init.get("children")
        if not isinstance(children, list) or not children:
            raise _err(f"{where}: children must be a non-empty list of "
                       f"nids (None for grid holes); got {children!r}.")
        for c in children:
            if c is None:
                continue
            if c not in kinds:
                raise _err(
                    f"{where}: children references node {c}, which is "
                    f"not defined earlier in the table."
                )
        if lk == "grid":
            rows, cols = node.init.get("grid_rows"), node.init.get("grid_cols")
            if not isinstance(rows, int) or not isinstance(cols, int):
                raise _err(f"{where}: grid layouts require integer "
                           f"grid_rows and grid_cols.")
            if rows * cols != len(children):
                raise _err(
                    f"{where}: grid_rows * grid_cols is {rows * cols} but "
                    f"children has {len(children)} entries."
                )

    _check_values(node.init, kinds, where)


def _check_ops(node, kinds: dict) -> None:
    op_ok = _layout_op_ok if node.kind == "layout" else _chart_op_ok
    family = ("a layout-state method" if node.kind == "layout"
              else "a registered artist, frame method, or attach_*")
    if not isinstance(node.ops, list):
        raise _err(f"node {node.nid} ({node.kind}): ops must be a list, "
                   f"got {type(node.ops).__name__}.")
    for i, op in enumerate(node.ops):
        where = f"node {node.nid} ({node.kind}) ops[{i}]"
        if (not isinstance(op, dict) or "op" not in op
                or not isinstance(op.get("args", []), list)
                or not isinstance(op.get("kwargs", {}), dict)):
            raise _err(
                f"{where}: expected {{'op': <name>, 'args': [...], "
                f"'kwargs': {{...}}}}; got {op!r}."
            )
        if not op_ok(op["op"]):
            raise _err(
                f"{where}: op {op['op']!r} does not resolve to {family}. "
                f"Extension artists register on import — a figure "
                f"referencing one needs `import plotlet.extensions.<name>` "
                f"first."
            )
        _check_values(op["args"], kinds, where)
        _check_values(op["kwargs"], kinds, where)


def _check_insets(node, kinds: dict) -> None:
    if not isinstance(node.insets, list):
        raise _err(f"node {node.nid} ({node.kind}): insets must be a list, "
                   f"got {type(node.insets).__name__}.")
    if node.kind == "layout" and node.insets:
        raise _err(
            f"node {node.nid} (layout): layout nodes cannot carry insets "
            f"— an inset embeds in a leaf's data area."
        )
    for i, ins in enumerate(node.insets):
        where = f"node {node.nid} ({node.kind}) insets[{i}]"
        rect = ins.get("rect") if isinstance(ins, dict) else None
        if (not isinstance(ins, dict) or "chart_nid" not in ins
                or not isinstance(rect, (list, tuple)) or len(rect) != 4):
            raise _err(
                f"{where}: expected {{'rect': [x, y, w, h], "
                f"'chart_nid': <nid>}}; got {ins!r}."
            )
        if ins["chart_nid"] not in kinds:
            raise _err(
                f"{where}: chart_nid references node {ins['chart_nid']}, "
                f"which is not defined earlier in the table."
            )
        if kinds[ins["chart_nid"]] != "chart":
            raise _err(
                f"{where}: chart_nid must reference a chart node; node "
                f"{ins['chart_nid']} is a {kinds[ins['chart_nid']]}."
            )


def validate(ir):
    """Check `ir` against the FigureIR contract (`docs/IR.md`). Raises
    `ValueError` on the first violation; returns `ir` unchanged so calls
    chain. `hydrate` runs this at entry — every render is validated."""
    if not getattr(ir, "nodes", None):
        raise _err("the node table is empty.")

    kinds: dict[int, str] = {}
    for node in ir.nodes:
        if not isinstance(node.nid, int):
            raise _err(f"node nid {node.nid!r} is not an int.")
        if node.nid in kinds:
            raise _err(f"duplicate nid {node.nid} in the node table.")
        if node.kind not in _KINDS:
            raise _err(
                f"node {node.nid}: unknown kind {node.kind!r} — the render "
                f"vocabulary is {list(_KINDS)}."
            )
        _check_init(node, kinds)
        _check_ops(node, kinds)
        _check_insets(node, kinds)
        kinds[node.nid] = node.kind

    if ir.root_nid not in kinds:
        raise _err(f"root_nid {ir.root_nid!r} is not in the node table "
                   f"(nids: {sorted(kinds)}).")
    return ir
