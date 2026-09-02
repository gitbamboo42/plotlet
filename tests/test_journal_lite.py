"""journal-lite — the terse authoring form (record/journal_lite.py).

The contract under test, from the module's rule list: `expand` is
pure fill-in and idempotent, every canonical journal is its fixed
point, `simplify` removes only what `expand` re-derives (proved by
round-trip over every shipped example), and a hand-written lite blob
renders byte-identical to the Python session it abbreviates.
"""
from pathlib import Path

import pytest

import plotlet as pt
from plotlet import aes
from plotlet.record.journal_lite import expand, simplify

EXAMPLES = Path(pt.__file__).parent / "examples"

DF = {"month": [1, 2, 3, 1, 2, 3],
      "sales": [12, 17, 14, 9, 13, 16],
      "region": ["north", "north", "north",
                 "south", "south", "south"]}


def _line_chart():
    c = pt.chart(DF, aes(x="month", y="sales", color="region"))
    c.add_line()
    c.title("Sales by region")
    return c


# ---------------------------------------------------------------------------
# expand — fixed point, idempotence, fill-in rules
# ---------------------------------------------------------------------------


def test_canonical_journal_is_a_fixed_point():
    j = pt.to_journal(_line_chart()).to_dict()
    assert expand(j) == j


def test_fixed_point_holds_for_inherit_aes_false_figures():
    # The hazard case that shaped the all-or-nothing rule: the
    # canonical form doesn't carry the opt-out, so expansion must not
    # re-inject chart keys into an entry that already has a mapping.
    c = pt.chart(DF, aes(x="month", y="sales", color="region"))
    c.add_scatter(aes(x="month", y="sales"), data=DF, inherit_aes=False)
    j = pt.to_journal(c).to_dict()
    assert expand(j) == j


def test_expand_is_idempotent_on_lite_input():
    lite = {"entries": [
        {"op": "new_chart", "nid": 1,
         "kwargs": {"data": dict(DF),
                    "aes": {"x": "month", "y": "sales"}}},
        {"op": "add_line", "nid": 1},
    ]}
    once = expand(lite)
    assert expand(once) == once


def test_minimal_lite_blob_renders_like_the_python_session():
    lite = {"entries": [
        {"op": "new_chart", "nid": 1,
         "kwargs": {"data": dict(DF),
                    "aes": {"x": "month", "y": "sales",
                                "color": "region"}}},
        {"op": "add_line", "nid": 1},
        {"op": "title", "nid": 1, "args": ["Sales by region"]},
    ]}
    assert pt.from_json_lite(lite).to_svg() == _line_chart().to_svg()


def test_expand_fills_version_root_and_entry_containers():
    j = expand({"entries": [{"op": "new_chart", "nid": 1}]})
    assert j["version"] == 1
    assert j["root_nid"] == 1
    e = j["entries"][0]
    assert e["args"] == [] and "kwargs" in e
    assert e["kwargs"]["data_width"] == 524


def test_root_nid_defaults_to_the_last_node_created():
    lite = {"entries": [
        {"op": "new_chart", "nid": 2,
         "kwargs": {"data": dict(DF),
                    "aes": {"x": "month", "y": "sales"}}},
        {"op": "add_line", "nid": 2},
        {"op": "new_layout", "nid": 1,
         "kwargs": {"layout_kind": "h", "children": [2],
                    "grid_rows": None, "grid_cols": None}},
    ]}
    assert expand(lite)["root_nid"] == 1


def test_present_mapping_is_complete_no_per_key_merge():
    lite = {"entries": [
        {"op": "new_chart", "nid": 1,
         "kwargs": {"data": dict(DF),
                    "aes": {"x": "month", "y": "sales",
                                "color": "region"}}},
        {"op": "add_line", "nid": 1,
         "kwargs": {"aes": {"x": "month", "y": "sales"}}},
    ]}
    e = expand(lite)["entries"][1]
    assert e["kwargs"]["aes"] == {"x": "month", "y": "sales"}
    # data still comes along — a mapping is in play and none was given
    assert e["kwargs"]["data"] == {"$data": "d1"}


def test_inherit_aes_false_suppresses_all_inheritance():
    lite = {"entries": [
        {"op": "new_chart", "nid": 1,
         "kwargs": {"data": dict(DF),
                    "aes": {"x": "month", "y": "sales"}}},
        {"op": "add_axhline", "nid": 1,
         "args": [13], "kwargs": {"inherit_aes": False}},
    ]}
    e = expand(lite)["entries"][1]
    assert "inherit_aes" not in e["kwargs"]
    assert "aes" not in e["kwargs"] and "data" not in e["kwargs"]


def test_inline_tables_intern_without_id_collisions():
    lite = {
        "data": {"d1": {"a": [1, 2]}},
        "entries": [
            {"op": "new_chart", "nid": 1,
             "kwargs": {"data": dict(DF),
                        "aes": {"x": "month", "y": "sales"}}},
            {"op": "add_line", "nid": 1},
        ],
    }
    j = expand(lite)
    assert j["entries"][0]["kwargs"]["data"] == {"$data": "d2"}
    assert j["data"]["d2"]["month"] == DF["month"]
    assert j["data"]["d1"] == {"a": [1, 2]}


def test_inline_matrix_interns_positionally():
    lite = {"entries": [
        {"op": "new_chart", "nid": 1},
        {"op": "add_image_cmap", "nid": 1,
         "args": [[[1, 2], [3, 4]]]},
    ]}
    j = expand(lite)
    assert j["entries"][1]["args"][0] == {"$data": "d1"}
    assert j["data"]["d1"] == [[1, 2], [3, 4]]


# ---------------------------------------------------------------------------
# simplify / to_json_lite — inverse direction
# ---------------------------------------------------------------------------


def test_every_example_round_trips_through_simplify():
    # The conformance sweep: for every shipped example figure,
    # simplify removes only what expand re-derives. (simplify also
    # self-checks, so this doubles as "simplify never raises".)
    ran = 0
    for py_path in sorted(EXAMPLES.glob("*.py")):
        ns: dict = {}
        exec(compile(py_path.read_text(encoding="utf-8"),
                     str(py_path), "exec"), ns)
        j = pt.to_journal(ns["c"]).to_dict()
        assert expand(simplify(j)) == j, py_path.name
        ran += 1
    assert ran > 20  # the sweep actually swept


def test_to_json_lite_drops_defaults_and_keeps_overrides():
    lite = pt.to_json_lite(_line_chart())
    assert '"data_width"' not in lite
    assert '"aes"' not in lite.split('"add_line"')[1].split("}")[0]
    c = pt.chart(DF, aes(x="month", y="sales"), data_width=700)
    c.add_line()
    assert '"data_width": 700' in pt.to_json_lite(c)


def test_lite_round_trip_renders_byte_identical():
    c = _line_chart()
    assert pt.from_json_lite(pt.to_json_lite(c)).to_svg() == c.to_svg()


def test_from_json_lite_accepts_canonical_journals():
    c = _line_chart()
    assert pt.from_json_lite(pt.to_json(c)).to_svg() == c.to_svg()
