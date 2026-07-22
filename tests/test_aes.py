"""aes() semantics — only aes(...) maps to data; bare strings are
literal. The disambiguation this buys: a column literally named
"purple" no longer collides with the color "purple"."""
import json

import plotlet as pt
from plotlet import aes


def _df():
    # a column whose *name* is also a valid CSS color
    return {"x": [1, 2, 3, 4], "y": [4, 3, 2, 1],
            "purple": ["a", "a", "b", "b"]}


def test_bare_string_is_literal_even_when_it_matches_a_column():
    df = _df()
    lit = pt.chart(df)
    lit.add_scatter(aes(x="x", y="y"), color="purple")

    ref = pt.chart(df)
    ref.add_scatter(aes(x="x", y="y"), color=pt.draw.resolve_color("purple"))

    # literal "purple" renders as the color purple — same marks as its
    # resolved spelling, no per-level split
    assert lit.to_svg() == ref.to_svg()


def test_aes_maps_the_same_string_to_the_column():
    df = _df()
    mapped = pt.chart(df)
    mapped.add_scatter(aes(x="x", y="y", color="purple"))

    lit = pt.chart(df)
    lit.add_scatter(aes(x="x", y="y"), color="purple")

    # the mapped spelling splits by level ("a"/"b") — different render
    assert mapped.to_svg() != lit.to_svg()
    # and the journal records the mapping explicitly
    blob = pt.to_json(mapped)
    art = [e for e in blob["entries"] if e["op"] == "scatter"][0]
    assert art["kwargs"]["mapping"] == {"x": "x", "y": "y", "color": "purple"}
    assert "color" not in art["kwargs"]


def test_aes_roundtrips_through_json():
    df = _df()
    c = pt.chart(df, aes(x="x", y="y", color="purple"))
    c.add_scatter()
    blob = json.loads(json.dumps(pt.to_json(c)))
    assert pt.from_json(blob).to_svg() == c.to_svg()


def test_aes_missing_column_fails_loudly():
    df = _df()
    c = pt.chart(df)
    c.add_scatter(aes(x="x", y="y", color="no_such_column"))
    try:
        c.to_svg()
    except KeyError as e:
        assert "no_such_column" in str(e)
    else:
        raise AssertionError("expected KeyError for unknown column")


def test_aes_rejects_non_string_values():
    try:
        aes(size=3)
    except TypeError as e:
        assert "column names" in str(e)
    else:
        raise AssertionError("expected TypeError for non-string aes value")


def test_aes_and_bare_kwarg_collision_raises():
    df = _df()
    c = pt.chart(df)
    try:
        c.add_scatter(aes(x="x", y="y", color="purple"), color="red")
    except TypeError as e:
        assert "pick one" in str(e)
    else:
        raise AssertionError("expected TypeError for aes/kwarg collision")


def test_inherit_aes_false_ignores_chart_mapping():
    """inherit_aes=False opts an artist out of chart-level aes, so a layer
    drawn from its own table (without the chart's mapped columns) doesn't
    inherit a mapping it can't satisfy."""
    chart_df = {"x": [1, 2, 3, 4], "y": [1, 2, 3, 4], "g": ["a", "a", "b", "b"]}
    line_df = {"px": [1, 4], "py": [4, 1]}   # no "g" column

    c = pt.chart(chart_df, aes(x="x", y="y", color="g"))
    c.add_scatter()
    # without inherit_aes=False the chart's color="g" would leak in and
    # KeyError on line_df; opting out keeps only the call's own aes
    c.add_line(line_df, aes(x="px", y="py"), inherit_aes=False)
    assert c.to_svg()


def test_inherit_aes_false_equals_no_chart_aes():
    """A self-describing artist with inherit_aes=False renders identically
    to the same artist on a chart that has no aes to inherit."""
    df = {"x": [1, 2, 3, 4], "y": [1, 2, 3, 4], "g": ["a", "a", "b", "b"]}

    optout = pt.chart(df, aes(x="x", y="y", color="g"))
    optout.add_line(aes(x="x", y="y"), inherit_aes=False)

    ref = pt.chart(df)
    ref.add_line(aes(x="x", y="y"))

    assert optout.to_svg() == ref.to_svg()


def test_inherit_aes_false_still_inherits_data():
    """inherit_aes controls aes only (like ggplot2's inherit.aes) — the
    chart-level table is still inherited when the artist brings none."""
    df = {"x": [1, 2, 3, 4], "y": [1, 2, 3, 4], "g": ["a", "a", "b", "b"]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line(aes(x="x", y="y"), inherit_aes=False)   # no own table
    assert c.to_svg()


def test_inherit_aes_is_a_directive_not_recorded():
    """inherit_aes is consumed at record time — it never lands in the
    journal or reaches the artist's record fn."""
    df = {"x": [1, 2, 3, 4], "y": [1, 2, 3, 4], "g": ["a", "a", "b", "b"]}

    c = pt.chart(df, aes(x="x", y="y", color="g"))
    c.add_line(aes(x="x", y="y"), inherit_aes=False)
    blob = pt.to_json(c)
    art = [e for e in blob["entries"] if e["op"] == "line"][0]
    assert "inherit_aes" not in art["kwargs"]
    # the recorded mapping carries only what the call kept (no color="g")
    assert "color" not in art["kwargs"]["mapping"]
