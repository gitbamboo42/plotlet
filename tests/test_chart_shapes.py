"""Baseline SVG regression tests for the shapes artist/topic.

    pytest tests/test_chart_shapes.py
    pytest tests/test_chart_shapes.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_split_rect():
    # Row 1 "sym":     n=1..8, symmetric=True  — cuts land on corners.
    # Row 2 "n":       n=1..8, symmetric=False — equal arc length.
    # Row 3 "rotate":  n=4, start sweeps 0..7/8.
    # Row 4 "weights": n=4, first sector weight grows 1..8.
    from plotlet import draw
    from plotlet.registry import ArtistSpec, add_artist

    _SR_COLORS = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
                  "#59a14f", "#edc948", "#b07aa1", "#ff9da7"]
    _COLS = [str(k) for k in range(8)]
    _ROWS = ["sym", "n", "rotate", "weights"]

    def _sr_record(**kw):
        return {"type": "split_rect_demo", "opts": kw}

    def _sr_xdomain(a): return _COLS
    def _sr_ydomain(a): return _ROWS

    def _sr_draw(a, ctx):
        out = []
        bw = ctx.x_scale.bandwidth
        bh = ctx.y_scale.bandwidth
        for k, col in enumerate(_COLS):
            cx = ctx.x_scale(col)
            for row in _ROWS:
                cy = ctx.y_scale(row)
                px, py = cx - bw / 2, cy - bh / 2
                if row == "sym":
                    n = k + 1
                    for i in range(n):
                        out.append(draw.split_rect(
                            px, py, bw, bh, n, i,
                            fill=_SR_COLORS[i % len(_SR_COLORS)], padding=2,
                            symmetric=True))
                elif row == "n":
                    n = k + 1
                    for i in range(n):
                        out.append(draw.split_rect(
                            px, py, bw, bh, n, i,
                            fill=_SR_COLORS[i % len(_SR_COLORS)], padding=2))
                elif row == "rotate":
                    for i in range(4):
                        out.append(draw.split_rect(
                            px, py, bw, bh, 4, i,
                            fill=_SR_COLORS[i], padding=2, start=k / 8))
                elif row == "weights":
                    wts = [k + 1, 1, 1, 1]
                    for i in range(4):
                        out.append(draw.split_rect(
                            px, py, bw, bh, 4, i,
                            fill=_SR_COLORS[i], padding=2, weights=wts))
        return "".join(out)

    add_artist(ArtistSpec(
        name="split_rect_demo",
        record=_sr_record,
        xdomain=_sr_xdomain,
        ydomain=_sr_ydomain,
        draw=_sr_draw,
    ))
    c = pt.chart(data_width=480, data_height=280,
                 title="draw.split_rect — symmetric / arc / rotate / weights")
    c.add_split_rect_demo()
    c.xticks(marks=False)
    c.yticks(marks=False)
    return c


def chart_split_pie():
    # Row 1 "n":       n=1..8 equal sectors.
    # Row 2 "rotate":  n=4, start sweeps 0..7/8.
    # Row 3 "weights": n=4, first sector weight grows 1..8.
    # Row 4 "gap":     n=4, gap grows 0..14°.
    from plotlet import draw
    from plotlet.registry import ArtistSpec, add_artist

    _SP_COLORS = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
                  "#59a14f", "#edc948", "#b07aa1", "#ff9da7"]
    _COLS = [str(k) for k in range(8)]
    _ROWS = ["n", "rotate", "weights", "gap"]

    def _sp_record(**kw):
        return {"type": "split_pie_demo", "opts": kw}

    def _sp_xdomain(a): return _COLS
    def _sp_ydomain(a): return _ROWS

    def _sp_draw(a, ctx):
        out = []
        bw = ctx.x_scale.bandwidth
        bh = ctx.y_scale.bandwidth
        for k, col in enumerate(_COLS):
            cx = ctx.x_scale(col)
            for row in _ROWS:
                cy = ctx.y_scale(row)
                px, py = cx - bw / 2, cy - bh / 2
                if row == "n":
                    n = k + 1
                    for i in range(n):
                        out.append(draw.split_pie(
                            px, py, bw, bh, n, i,
                            fill=_SP_COLORS[i % len(_SP_COLORS)], padding=2))
                elif row == "rotate":
                    for i in range(4):
                        out.append(draw.split_pie(
                            px, py, bw, bh, 4, i,
                            fill=_SP_COLORS[i], padding=2, start=k / 8))
                elif row == "weights":
                    wts = [k + 1, 1, 1, 1]
                    for i in range(4):
                        out.append(draw.split_pie(
                            px, py, bw, bh, 4, i,
                            fill=_SP_COLORS[i], padding=2, weights=wts))
                elif row == "gap":
                    for i in range(4):
                        out.append(draw.split_pie(
                            px, py, bw, bh, 4, i,
                            fill=_SP_COLORS[i], padding=2, gap=k * 2))
        return "".join(out)

    add_artist(ArtistSpec(
        name="split_pie_demo",
        record=_sp_record,
        xdomain=_sp_xdomain,
        ydomain=_sp_ydomain,
        draw=_sp_draw,
    ))
    c = pt.chart(data_width=480, data_height=280,
                 title="draw.split_pie — n / rotate / weights / gap")
    c.add_split_pie_demo()
    c.xticks(marks=False)
    c.yticks(marks=False)
    return c


def chart_rect():
    # Mixed scalar / list inputs — broadcast covers the multi-track,
    # gantt-style, and interval-model use cases that motivated adding rect.
    # Also exercises color= (outline) + linewidth so the stroke path is
    # covered.
    c = pt.chart(title="rect (broadcast + outline)",
                 xlabel="x", ylabel="y", legend=True)
    c.add_rect([0, 2, 4, 6], 0, [1.5, 1.5, 1.5, 1.5], 2, fill="C0",
           alpha=0.6, label="intervals")
    c.add_rect(0.5, 2.5, 7, 1, fill="C1", alpha=0.3,
           color="C3", linewidth=1.5, label="overlay")
    c.add_rect(3, 0.2, 1, 1.6, fill="none", color="black",
           linewidth=2, label="outline")
    return c


def chart_polygon():
    # Two polygons composed in one chart: a filled triangle (color cycle)
    # and an outlined diamond (fill="none"). Polygon auto-closes — the
    # last vertex doesn't need to repeat the first.
    c = pt.chart(title="polygon", xlabel="x", ylabel="y", legend=True)
    c.add_polygon([0, 2, 1], [0, 0, 2], alpha=0.5, label="triangle")
    c.add_polygon([3, 4, 3, 2], [1, 2, 3, 2], fill="none", linewidth=2,
              label="diamond")
    return c


PLOTS = {
    "split_rect": chart_split_rect,
    "split_pie": chart_split_pie,
    "rect": chart_rect,
    "polygon": chart_polygon,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_shapes_baseline(name, fn, baseline_compare):
    baseline_compare("chart_shapes", name, fn().to_svg())
