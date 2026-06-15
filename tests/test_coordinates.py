"""Baseline tests for coordinate-aware artists (plotlet.coordinates).

Two groups:

  1. Angle variants   — a lightweight custom artist at angle=0/+30/−20 with
                        c.coordinate(LinearCoordinate(angle=...)) verifies that
                        svg_transform() and draw_frame() produce correct geometry.

  2. Built-in artists — line, scatter, bar, fill_between, and heatmap used
                        inside LinearCoordinate via ``c.coordinate(...)``.
                        Most exercise the svg_transform path (existing artists
                        unchanged, wrapped in an SVG affine matrix); heatmap
                        also exercises categorical-y normalization in draw_frame.
"""
from __future__ import annotations

import math
import random

import plotlet as pt
from plotlet import draw
from plotlet.coordinates import LinearCoordinate
from plotlet.registry import ArtistSpec, add_artist
import pytest


# ---------------------------------------------------------------------------
# Minimal custom artist — used only for angle-variant tests.
# _DynamicAngle reads angle from the artist dict so one ArtistSpec covers
# all test angles without needing separate registrations.
# ---------------------------------------------------------------------------

def _record(args, kw):
    kw = dict(kw)
    return {
        "type": "coord_test_dots",
        "ts":   list(kw.pop("t")),
        "rs":   list(kw.pop("r")),
        "opts": kw,
    }


def _draw(a, ctx):
    col = ctx.color or "#4477aa"
    return "".join(
        draw.circle(ctx.x_scale(t), ctx.y_scale(r), 4, fill=col)
        for t, r in zip(a["ts"], a["rs"])
    )


add_artist(ArtistSpec(
    name="coord_test_dots",
    record=_record,
    draw=_draw,
    xdomain=lambda a: a["ts"],
    ydomain=lambda a: a["rs"],
))

_TS = [i / 8 for i in range(9)]
_RS = [0.2, 0.5, 0.8, 0.4, 0.6, 0.3, 0.7, 0.5, 0.4]


def _dots_chart(angle, title):
    c = pt.chart(title=title, xlabel="t", ylabel="r",
                 xlim=(0.0, 1.0), ylim=(0.0, 1.0),
                 data_width=240, data_height=240)
    c.coordinate(LinearCoordinate(angle=angle))
    c.coord_test_dots(t=_TS, r=_RS)
    return c


# ---------------------------------------------------------------------------
# Built-in artists inside LinearCoordinate via c.coordinate(...)
# ---------------------------------------------------------------------------

_COORD_30 = LinearCoordinate(angle=30)


def coord_line_angle30():
    xs = [i / 10 for i in range(11)]
    ys = [math.sin(x * math.pi) for x in xs]
    df = {"x": xs, "y": ys}
    c = pt.chart(title="line — angle=30", xlabel="x", ylabel="y",
                 xlim=(0.0, 1.0), ylim=(-1.1, 1.1),
                 data_width=240, data_height=240)
    c.coordinate(_COORD_30)
    c.line(data=df, x="x", y="y")
    return c


def coord_scatter_angle30():
    rng = random.Random(0)
    xs = [rng.random() for _ in range(30)]
    ys = [rng.random() for _ in range(30)]
    c = pt.chart(title="scatter — angle=30", xlabel="x", ylabel="y",
                 xlim=(0.0, 1.0), ylim=(0.0, 1.0),
                 data_width=240, data_height=240)
    c.coordinate(_COORD_30)
    c.scatter(data={"x": xs, "y": ys}, x="x", y="y")
    return c


def coord_bar_angle30():
    df = {"cat": ["A", "B", "C", "D"], "val": [3, 7, 4, 6]}
    c = pt.chart(title="bar — angle=30", xlabel="cat", ylabel="value",
                 data_width=240, data_height=240)
    c.coordinate(_COORD_30)
    c.bar(data=df, x="cat", y="val")
    return c


def coord_fill_between_angle30():
    xs = [i / 10 for i in range(11)]
    mn = [math.sin(x * math.pi) for x in xs]
    df_band = {"x": xs, "lo": [v - 0.25 for v in mn], "hi": [v + 0.25 for v in mn]}
    df_line = {"x": xs, "y": mn}
    c = pt.chart(title="fill_between — angle=30", xlabel="x", ylabel="y",
                 xlim=(0.0, 1.0), data_width=240, data_height=240)
    c.coordinate(_COORD_30)
    c.fill_between(data=df_band, x="x", y1="lo", y2="hi", fill="C0", alpha=0.3)
    c.line(data=df_line, x="x", y="y")
    return c


def coord_heatmap_angle20():
    # Heatmap: categorical y-ticks exercise draw_frame's y_scale normalization.
    data = [[math.sin(r * 0.8) * math.cos(c * 0.5) for c in range(5)]
            for r in range(4)]
    c = pt.chart(title="heatmap — angle=20", xlabel="col", ylabel="row",
                 data_width=240, data_height=240)
    c.coordinate(LinearCoordinate(angle=20))
    c.heatmap(data,
              xticklabels=["C0", "C1", "C2", "C3", "C4"],
              yticklabels=["R0", "R1", "R2", "R3"],
              cmap="viridis")
    return c


# ---------------------------------------------------------------------------
# PLOTS registry and parametrized test
# ---------------------------------------------------------------------------

PLOTS = {
    # Angle variants (custom dots artist)
    "linear_angle0":      lambda: _dots_chart(0.0,   "angle=0 (Cartesian)"),
    "linear_angle30":     lambda: _dots_chart(30.0,  "angle=30"),
    "linear_angle_neg20": lambda: _dots_chart(-20.0, "angle=−20"),
    # Built-in artists
    "line_angle30":         coord_line_angle30,
    "scatter_angle30":      coord_scatter_angle30,
    "bar_angle30":          coord_bar_angle30,
    "fill_between_angle30": coord_fill_between_angle30,
    "heatmap_angle20":      coord_heatmap_angle20,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_coordinates_baseline(name, fn, baseline_compare):
    baseline_compare("coordinates", name, fn().to_svg())
