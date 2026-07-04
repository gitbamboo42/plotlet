"""`render.validate` — the FigureIR contract check at the render seam.

Happy paths are covered wholesale by the baseline corpus (every render
validates via `hydrate`); this suite covers the error surface: each
contract rule broken one at a time on an otherwise-valid IR, asserting
a `ValueError` whose message names the offending node and rule. IRs are
built from real charts and then mutated — closer to what a buggy
transform or hand-edit produces than fully synthetic tables.
"""
from __future__ import annotations

import pytest

import plotlet as pt
from plotlet.render import validate


def _chart_ir():
    c = pt.chart({"x": [1, 2, 3], "y": [1, 4, 9]}, title="t")
    c.scatter(x="x", y="y")
    return pt.to_ir(c)


def _layout_ir():
    a = pt.chart({"x": [1, 2], "y": [3, 4]})
    a.scatter(x="x", y="y")
    b = pt.chart({"x": [1, 2], "y": [4, 3]})
    b.line(x="x", y="y")
    return pt.to_ir(a | b)


def _legend_ir():
    c = pt.chart({"x": [1, 2], "y": [3, 4], "g": ["a", "b"]})
    c.scatter(x="x", y="y", color="g")
    return pt.to_ir(c | pt.legend(c))


def _grid_ir():
    cells = []
    for i in range(4):
        c = pt.chart({"x": [1, 2], "y": [3, 4]})
        c.scatter(x="x", y="y")
        cells.append(c)
    return pt.to_ir(pt.grid([cells[:2], cells[2:]]))


def _node(ir, kind):
    return next(n for n in ir.nodes if n.kind == kind)


def _expect(ir, fragment):
    with pytest.raises(ValueError, match="invalid FigureIR") as e:
        validate(ir)
    assert fragment in str(e.value), \
        f"expected {fragment!r} in error:\n{e.value}"


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_valid_irs_pass_and_chain():
    for ir in (_chart_ir(), _layout_ir(), _legend_ir(), _grid_ir()):
        assert validate(ir) is ir
    ir = _chart_ir()
    assert ir.validate() is ir  # FigureIR convenience method


def test_json_round_trip_validates():
    ir = pt.from_ir(_legend_ir().to_dict())
    assert validate(ir) is ir


# ---------------------------------------------------------------------------
# Table-level rules
# ---------------------------------------------------------------------------


def test_empty_table():
    ir = _chart_ir()
    ir.nodes = []
    _expect(ir, "node table is empty")


def test_root_nid_missing():
    ir = _chart_ir()
    ir.root_nid = 9999
    _expect(ir, "root_nid 9999")


def test_duplicate_nid():
    ir = _layout_ir()
    ir.nodes[1].nid = ir.nodes[0].nid
    _expect(ir, "duplicate nid")


def test_unknown_kind():
    ir = _chart_ir()
    ir.nodes[0].kind = "facet_grid"
    _expect(ir, "unknown kind 'facet_grid'")


def test_forward_reference():
    ir = _layout_ir()
    ir.nodes.reverse()  # layout now precedes the charts it references
    _expect(ir, "not defined earlier")


# ---------------------------------------------------------------------------
# Per-kind init rules
# ---------------------------------------------------------------------------


def test_layout_bad_kind():
    ir = _layout_ir()
    _node(ir, "layout").init["layout_kind"] = "diagonal"
    _expect(ir, "layout_kind")


def test_layout_unknown_child():
    ir = _layout_ir()
    _node(ir, "layout").init["children"][0] = 4242
    _expect(ir, "references node 4242")


def test_grid_shape_mismatch():
    ir = _grid_ir()
    _node(ir, "layout").init["grid_cols"] = 3
    _expect(ir, "grid_rows * grid_cols")


def test_legend_missing_canvas():
    ir = _legend_ir()
    del _node(ir, "legend").init["canvas_width"]
    _expect(ir, "require 'canvas_width'")


def test_legend_unknown_source():
    ir = _legend_ir()
    _node(ir, "legend").init["legend_sources"] = [4242]
    _expect(ir, "legend_sources references node 4242")


def test_malformed_margin():
    ir = _chart_ir()
    _node(ir, "chart").init["margin"] = {"left": 10}
    _expect(ir, "margin")


# ---------------------------------------------------------------------------
# Ops and envelopes
# ---------------------------------------------------------------------------


def test_unknown_chart_op():
    ir = _chart_ir()
    _node(ir, "chart").ops.append({"op": "sparkle", "args": [], "kwargs": {}})
    _expect(ir, "'sparkle'")


def test_unknown_layout_op():
    ir = _layout_ir()
    _node(ir, "layout").ops.append({"op": "twinx", "args": [], "kwargs": {}})
    _expect(ir, "'twinx'")


def test_malformed_op_entry():
    ir = _chart_ir()
    _node(ir, "chart").ops.append({"name": "scatter"})  # wrong key
    _expect(ir, "expected {'op'")


def test_malformed_node_envelope():
    ir = _chart_ir()
    _node(ir, "chart").ops.append(
        {"op": "title", "args": [{"$node": "not-an-int"}], "kwargs": {}})
    _expect(ir, "malformed $node")


def test_node_envelope_forward_reference():
    ir = _chart_ir()
    _node(ir, "chart").ops.append(
        {"op": "title", "args": [{"$node": 4242}], "kwargs": {}})
    _expect(ir, "references node 4242")


def test_unknown_coord():
    ir = _chart_ir()
    _node(ir, "chart").ops.append(
        {"op": "coordinate", "args": [{"$coord": "HexagonalCoordinate"}],
         "kwargs": {}})
    _expect(ir, "HexagonalCoordinate")


def test_malformed_inset():
    ir = _chart_ir()
    _node(ir, "chart").insets.append({"rect": [0, 0, 1], "chart_nid": 1})
    _expect(ir, "insets[0]")


def test_inset_unknown_chart():
    ir = _chart_ir()
    _node(ir, "chart").insets.append(
        {"rect": [0.5, 0.5, 0.4, 0.4], "chart_nid": 4242})
    _expect(ir, "chart_nid references node 4242")


def test_layout_cannot_carry_insets():
    # The recorder can't produce this (Layout has no `.inset()`), but a
    # hand-authored IR could — and hydration would die with a raw
    # AttributeError (RenderLayout has no `_insets`) instead of the
    # promised contract error.
    ir = _layout_ir()
    chart_nid = _node(ir, "chart").nid
    _node(ir, "layout").insets.append(
        {"rect": [0.5, 0.5, 0.4, 0.4], "chart_nid": chart_nid})
    _expect(ir, "layout nodes cannot carry insets")


def test_inset_target_must_be_chart_kind():
    # Host must come after the target in the table for the kind check
    # (not the earlier-reference check) to be what fires — a legend leaf
    # composed before the chart gives that ordering.
    ir = _legend_kind_target_ir()
    legend_nid = _node(ir, "legend").nid
    _node(ir, "chart").insets.append(
        {"rect": [0.1, 0.1, 0.3, 0.3], "chart_nid": legend_nid})
    _expect(ir, "chart_nid must reference a chart node")


def test_legend_sources_must_be_leaves():
    # An inner layout (kept un-flattened by its share_y call) precedes
    # the legend in dependency order, so pointing legend_sources at it
    # exercises the kind check, not the earlier-reference check.
    a = pt.chart({"x": [1, 2], "y": [3, 4]})
    a.scatter(x="x", y="y")
    b = pt.chart({"x": [1, 2], "y": [4, 3]})
    b.line(x="x", y="y")
    inner = (a | b).share_y()
    ir = pt.to_ir(inner | pt.legend(a))
    inner_nid = next(n.nid for n in ir.nodes
                     if n.kind == "layout" and n.nid != ir.root_nid)
    _node(ir, "legend").init["legend_sources"] = [inner_nid]
    _expect(ir, "sources must be leaf nodes")


def _legend_kind_target_ir():
    """`pt.legend() | chart` — the legend leaf lands *before* the chart
    in the node table."""
    c = pt.chart({"x": [1, 2], "y": [3, 4]})
    c.scatter(x="x", y="y")
    return pt.to_ir(pt.legend() | c)


# ---------------------------------------------------------------------------
# Enforcement at the render entry
# ---------------------------------------------------------------------------


def test_render_entry_rejects_broken_ir():
    ir = _chart_ir()
    ir.nodes[0].kind = "mystery"
    with pytest.raises(ValueError, match="invalid FigureIR"):
        ir.to_svg()
    with pytest.raises(ValueError, match="invalid FigureIR"):
        ir.resolve()
