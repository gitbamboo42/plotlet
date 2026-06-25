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
    assert _roundtrip(fig).to_svg() == fig.to_svg()


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


def test_attach_left():
    host = pt.chart(data_width=240, data_height=180, title="host")
    host.scatter(data={"x": [1, 2, 3], "y": [3, 1, 2]}, x="x", y="y")
    side = pt.chart(data_width=60, data_height=180, title="side")
    side.line(data={"x": [1, 2, 3], "y": [3, 1, 2]}, x="x", y="y")
    host.attach_left(side)
    _assert_round_trip(host)


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
    coord, Chart/Layout refs. Anything else must raise loudly so the
    user knows to add a codec instead of silently dropping the value."""
    class _Custom:
        pass

    c = pt.chart(data_width=120, data_height=80)
    c.scatter(data={"x": [1, 2], "y": [1, 2]}, x="x", y="y",
              palette=_Custom())  # palette objects aren't codec'd yet
    with pytest.raises(TypeError, match="don't know how to encode"):
        pt.to_json(c)
