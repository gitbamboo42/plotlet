"""Round-trip tests for `pt.to_json` / `pt.from_json`.

The contract: `from_json(to_json(node)).to_svg()` matches `node.to_svg()`
modulo nondeterministic ids (clip-path identifiers derived from
`id(obj)`, same as conftest's baseline normalization). Encoder and
decoder are mirrors; SVG bytes are the only signal that matters. No
baseline images here — the test fixture itself is the baseline (run
twice, compare bytes).
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import pytest

import plotlet as pt


_VOLATILE_RE = re.compile(
    r' id="pc[0-9a-f]+"'
    r'| clip-path="url\(#pc[0-9a-f]+\)"'
)


def _norm(svg: str) -> str:
    return _VOLATILE_RE.sub("", svg)


def _roundtrip(node):
    blob = pt.to_json(node)
    # Confirm the dict is JSON-string-clean — encoded args mustn't carry
    # numpy/pandas leakage that survives `json.dumps`.
    text = json.dumps(blob)
    revived = pt.from_json(json.loads(text))
    return revived


def _assert_round_trip(node):
    """Round-trip and compare SVG. Uses the same volatile-id normalizer
    the baseline conftest applies, since coord-frame clip-path ids embed
    `id(obj)` and are non-deterministic across renders."""
    revived = _roundtrip(node)
    assert _norm(revived.to_svg()) == _norm(node.to_svg())


def test_leaf_chart_basic():
    c = pt.chart(data_width=200, data_height=150, title="hello",
                 xlabel="x", ylabel="y")
    c.line(data={"x": [1, 2, 3], "y": [4, 5, 6]}, x="x", y="y", color="red")
    _assert_round_trip(c)


def test_leaf_chart_with_numpy():
    c = pt.chart(data_width=200, data_height=150)
    c.scatter(
        data={"x": np.array([1.0, 2.0, 3.0]),
              "y": np.array([0.5, 1.5, 2.5])},
        x="x", y="y",
    )
    _assert_round_trip(c)


def test_leaf_chart_with_dataframe():
    df = pd.DataFrame({"g": ["a", "b", "c"], "x": [1, 2, 3], "y": [3, 2, 1]})
    c = pt.chart(data=df, data_width=200, data_height=150)
    c.scatter(x="x", y="y", color="g")
    _assert_round_trip(c)


def test_h_compose_with_share_and_gap():
    a = pt.chart(data_width=200, data_height=150, title="A")
    a.line(data={"x": [1, 2, 3], "y": [4, 5, 6]}, x="x", y="y")
    b = pt.chart(data_width=200, data_height=150, title="B")
    b.line(data={"x": [1, 2, 3], "y": [6, 5, 4]}, x="x", y="y")
    c = pt.chart(data_width=200, data_height=150, title="C")
    c.line(data={"x": [1, 2, 3], "y": [5, 5, 5]}, x="x", y="y")
    fig = (a | b | c).share_y("all").gap(4)
    _assert_round_trip(fig)


def test_v_of_h_with_share_x_col():
    def row(name):
        x = pt.chart(title=f"{name}-1", data_width=160, data_height=80)
        y = pt.chart(title=f"{name}-2", data_width=110, data_height=80)
        z = pt.chart(title=f"{name}-3", data_width=70, data_height=80)
        x.line(data={"x": [0, 1, 2, 3, 4], "y": [0, 1, 2, 1, 0]}, x="x", y="y")
        y.line(data={"x": [0, 1, 2, 3], "y": [2, 1, 3, 1]}, x="x", y="y")
        z.line(data={"x": [0, 1, 2], "y": [1, 2, 1]}, x="x", y="y")
        return (x | y | z).share_y().gap(0)
    fig = (row("r1") / row("r2")).share_x("col")
    _assert_round_trip(fig)


def test_grid_with_none_cells():
    def cell(t):
        c = pt.chart(data_width=120, data_height=80, title=t)
        c.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
        return c
    fig = pt.grid([[cell("a"), None], [cell("b"), cell("c")]])
    _assert_round_trip(fig)


def test_attach_all_sides():
    host = pt.chart(data_width=200, data_height=160)
    host.scatter(data={"x": [1, 2, 3], "y": [3, 2, 1]}, x="x", y="y")
    l = pt.chart(data_width=50, data_height=160)
    l.line(data={"x": [1, 2], "y": [1, 2]}, x="x", y="y")
    r = pt.chart(data_width=50, data_height=160)
    r.line(data={"x": [1, 2], "y": [2, 1]}, x="x", y="y")
    t = pt.chart(data_width=200, data_height=40)
    t.line(data={"x": [1, 2, 3], "y": [1, 2, 1]}, x="x", y="y")
    b = pt.chart(data_width=200, data_height=40)
    b.line(data={"x": [1, 2, 3], "y": [2, 1, 2]}, x="x", y="y")
    host.attach_left(l).attach_right(r).attach_above(t).attach_below(b)
    _assert_round_trip(host)


def test_linear_coordinate():
    c = pt.chart(data_width=200, data_height=160)
    c.coordinate(pt.LinearCoordinate(angle=30))
    c.line(data={"x": [0, 1, 2], "y": [0, 1, 0]}, x="x", y="y")
    _assert_round_trip(c)


def test_circular_coordinate_on_layout():
    a = pt.chart(data_width=120, data_height=120)
    a.line(data={"x": [0, 1, 2], "y": [1, 2, 1]}, x="x", y="y")
    b = pt.chart(data_width=120, data_height=120)
    b.line(data={"x": [0, 1, 2], "y": [2, 1, 2]}, x="x", y="y")
    fig = (a / b).coordinate(pt.CircularCoordinate(r_inner=0.4, gap=0.08))
    _assert_round_trip(fig)


def test_circular_coordinate_with_inner_chart():
    """`CircularCoordinate.inner` holds a Chart; the encoder must
    collect it as a node and emit it as a `$ref` inside the coord
    kwargs, not flatten or drop it."""
    a = pt.chart(data_width=120, data_height=120)
    a.line(data={"x": [0, 1, 2], "y": [1, 2, 1]}, x="x", y="y")
    b = pt.chart(data_width=120, data_height=120)
    b.line(data={"x": [0, 1, 2], "y": [2, 1, 2]}, x="x", y="y")
    inner = pt.chart(data_width=80, data_height=80)
    inner.scatter(data={"x": [0, 1, 2], "y": [0, 1, 0]}, x="x", y="y")
    fig = (a / b).coordinate(pt.CircularCoordinate(r_inner=0.4, inner=inner))
    _assert_round_trip(fig)


def test_unsupported_value_raises():
    """Codec set is closed — primitives, list/dict, numpy, DataFrame,
    coord, Sectors, Chart/Layout refs. Anything else must raise loudly
    so the user knows to add a codec instead of silently dropping the
    value."""
    class _Custom:
        pass

    c = pt.chart(data_width=120, data_height=80)
    c.scatter(data={"x": [1, 2], "y": [1, 2]}, x="x", y="y",
              palette=_Custom())  # palette objects aren't codec'd yet
    with pytest.raises(TypeError, match="don't know how to encode"):
        pt.to_json(c)


def test_chart_level_coordinate_inner():
    """Regression: `chart.coordinate(coord_with_inner)` (no enclosing
    layout). The collection pass must walk Chart `_calls` args for
    embedded refs, not just `attach_*` entries — otherwise the inner
    Chart escapes id assignment and the encoder hits it raw."""
    inner = pt.chart(data_width=80, data_height=80)
    inner.scatter(data={"x": [0, 1], "y": [0, 1]}, x="x", y="y")
    c = pt.chart(data_width=200, data_height=200)
    c.line(data={"x": [0, 1], "y": [0, 1]}, x="x", y="y")
    c.coordinate(pt.CircularCoordinate(r_inner=0.5, inner=inner))
    _assert_round_trip(c)


def test_chord_links_4tuple_calls():
    """Regression: artists whose `frame_defaults` emit extra calls
    (chord_links, dendrogram, heatmap, …) record 4-tuple entries —
    `(name, args, kwargs, True)` — with the trailing bool flag picked
    up by replay at core.py to route `xscale(order=...)` as a frame
    default rather than a user-explicit call. The encoder and the
    collection pass must tolerate both 3- and 4-tuple shapes, and
    decode must preserve the trailing flag so replay routes the same."""
    import plotlet.extensions.chord_links  # noqa

    links = {"src_group": ["A", "B"], "dst_group": ["B", "A"],
             "src": [1.0, 3.0], "dst": [5.0, 7.0], "kind": ["t", "t"]}
    c = pt.chart(links, xlim=(0, 10), data_width=200, data_height=200)
    c.chord_links(x1="src", x2="dst",
                  x1_sector="src_group", x2_sector="dst_group",
                  color="kind")
    assert any(len(e) == 4 for e in c._calls), (
        "test premise: chord_links should record 4-tuple entries"
    )
    revived = _roundtrip(c)
    assert [len(e) for e in revived._calls] == [len(e) for e in c._calls]
    assert _norm(revived.to_svg()) == _norm(c.to_svg())


def test_sectors_codec():
    """`pt.Sectors(...)` shows up as an arg to `c.sectors(...)` and
    `Layout.sectors(...)`. Round-trip via the `$sectors` envelope."""
    c = pt.chart(data_width=200, data_height=100, xlim=(0, 30))
    c.line(data={"group": ["A", "B", "C"], "x": [5, 15, 25],
                 "y": [1, 2, 1]},
           x="x", y="y")
    c.sectors(pt.Sectors(names=("A", "B", "C"),
                         lengths=(10, 10, 10), gap=2),
              column="group")
    _assert_round_trip(c)
