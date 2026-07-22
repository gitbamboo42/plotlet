"""Baseline SVG regression tests for the axis artist/topic.

    pytest tests/test_chart_axis.py
    pytest tests/test_chart_axis.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest
from _chart_helpers import _dendro_sample


def chart_category_x_scatter():
    # scatter on a categorical x — categories supplied alphabetically by default.
    rng = random.Random(3)
    samples = ["S1", "S2", "S3", "S4"]
    df = {
        "sample": [s for s in samples for _ in range(8)],
        "value":  [rng.gauss(0, 1) for _ in range(32)],
    }
    c = pt.chart(df, aes(x="sample", y="value"), title="scatter on categorical x",
                 xlabel="sample", ylabel="value", xscale="category")
    c.add_scatter(color="C0", alpha=0.6)
    return c


def chart_category_x_order():
    # Explicit order= reorders bars from their default first-appearance.
    df = {"sample": ["S1", "S2", "S3"], "count": [12, 7, 19]}
    c = pt.chart(df, aes(x="sample", y="count"), title="bar with explicit category order",
                 xlabel="sample", ylabel="count")
    c.xscale("category", order=["S3", "S1", "S2"])
    c.add_bar(fill="C2")
    return c


def chart_category_y_scatter():
    # scatter on a categorical y — groups stack top-to-bottom.
    rng = random.Random(11)
    groups = ["alpha", "beta", "gamma"]
    df = {
        "group": [g for g in groups for _ in range(10)],
        "x":     [rng.gauss(0, 1) for _ in range(30)],
    }
    c = pt.chart(df, aes(x="x", y="group"), title="scatter on categorical y",
                 xlabel="x", ylabel="group", yscale="category")
    c.add_scatter(color="C3", alpha=0.6)
    return c


def chart_category_y_order():
    # Explicit y order= overrides the default alphabetical layout.
    rng = random.Random(11)
    groups = ["alpha", "beta", "gamma"]
    df = {
        "group": [g for g in groups for _ in range(10)],
        "x":     [rng.gauss(0, 1) for _ in range(30)],
    }
    c = pt.chart(df, aes(x="x", y="group"), title="scatter on categorical y, explicit order",
                 xlabel="x", ylabel="group")
    c.yscale("category", order=["gamma", "alpha", "beta"])
    c.add_scatter(color="C3", alpha=0.6)
    return c


def chart_hide_yticks():
    # Metadata-strip pattern: numeric y for positioning, but ticks suppressed
    # via yticks([]).
    df = {"sample": ["S1", "S2", "S3", "S4"], "stage": [0.5] * 4}
    c = pt.chart(df, aes(x="sample", y="stage"), data_width=320, data_height=24,
                 title="metadata strip", ylabel="stage")
    c.add_bar(fill="C1")
    c.ylim(0, 1)
    c.yticks([])
    return c


def chart_xticks_rotation():
    # Rotate category labels that would crowd horizontally.
    df = {"month": ["Jan", "Feb", "Mar", "Apr", "May"],
          "count": [12, 7, 19, 14, 9]}
    c = pt.chart(df, aes(x="month", y="count"), data_width=320, data_height=180,
                 title="rotated x labels", ylabel="count")
    c.add_bar(fill="C0")
    c.xticks(rotation=45)
    return c


def chart_xticks_top_share_x():
    # share_x="col" v-stack where the BOTTOM panel flips x-axis to top.
    # Without joined-pair routing of top-label suppression, the bottom
    # panel's tick label glyphs would render unanchored at the joint
    # between the two panels. With the fix, those labels suppress and
    # only the upper panel's bottom-edge labels remain at the shared
    # edge (which here is the default bottom side of the upper panel).
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    df2 = {"x": xs, "y": [math.cos(t) for t in xs]}
    top = pt.chart(df, aes(x="x", y="y"), ylabel="sin").add_line()
    bot = pt.chart(df2, aes(x="x", y="y"), xlabel="x", ylabel="cos").add_line()
    bot.xticks(side="top")
    return pt.grid([[top], [bot]]).share_x("col")


def chart_xticks_flipped_sides():
    # x-axis on top, y-axis on right via side="top"/"right". Margins,
    # xlabel/ylabel and title all follow.
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    c = pt.chart(df, aes(x="x", y="y"), title="x on top, y on right",
                 xlabel="x", ylabel="y")
    c.add_line()
    c.xticks(side="top")
    c.yticks(side="right")
    return c


def chart_xticks_inward():
    # Inward tick direction — ticks pointing into the data
    # area. Just covers `direction="in"`; default outward look is in every
    # other test.
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    c = pt.chart(df, aes(x="x", y="y"), title="inward ticks", xlabel="x", ylabel="y")
    c.add_line()
    c.xticks(direction="in")
    c.yticks(direction="in")
    return c


def chart_xticks_marks_off():
    # Hide tick marks but keep labels (compare to xticks([]) which hides both).
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    c = pt.chart(df, aes(x="x", y="y"), title="labels only, no tick marks", xlabel="x", ylabel="y")
    c.add_line()
    c.xticks(marks=False)
    c.yticks(marks=False)
    return c


def chart_xticks_explicit():
    # Explicit positions and labels, plus a fontsize override.
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    c = pt.chart(df, aes(x="x", y="y"), title="explicit ticks", xlabel="x", ylabel="y")
    c.add_line()
    c.xticks([0, math.pi, 2 * math.pi], ["0", "π", "2π"], fontsize=14)
    return c


def chart_category_padding_zero():
    # Contiguous track: cells butt up with no inner gap.
    df = {"x": ["a", "b", "c", "d", "e"], "v": [1, 2, 3, 2, 1]}
    c = pt.chart(df, aes(x="x", y="v"), data_width=320, data_height=60,
                 title="padding=0 (contiguous)")
    c.xscale("category", padding=0)
    c.add_bar(fill="C0")
    return c


def chart_errorbar_category_x():
    # Categorical x + numeric yerr — common "bar with error bars" pattern.
    df = {"cat":  ["control", "low", "mid", "high"],
          "mean": [2.1, 3.4, 4.6, 5.2],
          "sd":   [0.3, 0.4, 0.5, 0.6]}
    c = pt.chart(df, aes(x="cat", y="mean"), title="response by level",
                 xlabel="level", ylabel="response")
    c.add_bar(fill="#cccccc")
    c.add_errorbar(aes(yerr="sd"))
    return c


def chart_dendrogram_explicit_xticks():
    # Explicit tick subset recorded BEFORE the artist: the dendrogram's
    # `marks=False` frame default toggles marks only — it must not reset
    # tick content, so exactly the two named leaves keep their labels.
    labels = ["sample_" + ch for ch in "ABCDEFGH"]
    c = pt.chart(title="dendrogram — explicit tick subset", data_height=200)
    c.xticks(["sample_A", "sample_D"])
    c.add_dendrogram(_dendro_sample(), method="ward", labels=labels)
    return c


def chart_long_rotated_xticks():
    # Long x-tick labels rotated 45° — the rotated bbox height grows the
    # bottom margin so labels don't overflow the canvas. Without rotation
    # they'd crowd horizontally; without measure-driven they'd spill past
    # the bottom edge.
    df = {"sample": ["sample_alpha_2024", "sample_beta_2024", "sample_gamma_2024",
                      "sample_delta_2024", "sample_epsilon_2024"],
          "count":  [12, 7, 19, 14, 9]}
    c = pt.chart(df, aes(x="sample", y="count"), data_width=300, data_height=180,
                 title="long rotated x-tick labels", ylabel="count")
    c.add_bar(fill="C0")
    c.xticks(rotation=45)
    return c


def chart_xticks_fontstyle_italic():
    # Italic axis-tick labels via fontstyle — renders with the real
    # DejaVuSans-Oblique face (synthetic skew is only the fallback for
    # path-loaded fonts with no italic sibling).
    df = {"label": ["alpha", "beta", "gamma", "delta", "epsilon"],
          "rate": [0.42, 0.35, 0.28, 0.21, 0.18]}
    c = pt.chart(df, aes(x="label", y="rate"), data_width=320, data_height=200,
                 title="italic labels", ylabel="rate")
    c.add_bar(fill="#5599aa")
    c.xticks(fontstyle="italic")
    return c


def chart_xticks_decoration():
    # CSS-style text-decoration on tick labels: underline / line-through /
    # overline. Each is rendered as a stroke line at the conventional
    # offset relative to the baseline / cap-top.
    df = {"cat": ["under", "strike", "over"], "val": [3, 4, 5]}
    c = pt.chart(df, aes(x="cat", y="val"), data_width=260, data_height=160,
                 title="tick label decorations")
    c.add_bar(fill="#5599aa")
    # Single-axis-wide style; mixing three on one chart isn't currently
    # supported (would need per-tick override).
    c.xticks(decoration="underline")
    c.yticks(decoration="line-through")
    return c


def chart_xticks_rotation_negative():
    # Negative rotation (CW on screen) — labels must extend BELOW the
    # tick into the bottom margin, not upward into the data area. Older
    # behavior used anchor="end" for all rotations, which pushed CW-
    # rotated labels into the chart body.
    df = {"sample": ["Sample-1", "Sample-2", "Sample-3", "Sample-4"],
          "value":  [10, 20, 15, 25]}
    c = pt.chart(df, aes(x="sample", y="value"), data_width=300, data_height=180,
                 title="negative rotation stays below data",
                 xlabel="samples", ylabel="value")
    c.add_bar(fill="#888")
    c.xticks(rotation=-90)
    return c


def chart_ticks_step():
    df = {"x": [0, 0.5, 1.0, 1.5, 2.0], "y": [0, 1, 4, 9, 16]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=400, data_height=170,
                 title="step=0.25", xlabel="x", ylabel="y", gridlines=True)
    c.add_line(marker="o")
    c.xticks(step=0.25)
    return c


def chart_ticks_count():
    df = {"x": list(range(11)), "y": [i * i for i in range(11)]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=400, data_height=170,
                 title="count=4", xlabel="x", ylabel="y", gridlines=True)
    c.add_line(marker="o")
    c.xticks(count=4)
    return c


def chart_minor_ticks_linear():
    df = {"x": [0, 1, 2, 3, 4, 5], "y": [0, 1, 4, 9, 16, 25]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=400, data_height=180,
                 title="minor ticks", xlabel="x", ylabel="y", gridlines=True)
    c.add_line(marker="o")
    c.xticks(minor=True)
    c.yticks(minor=True)
    return c


def chart_power10_math_text():
    # power10 log ticks + unicode super/subscripts in axis labels +
    # italic in-plot text — the math-text vocabulary in one baseline.
    df = {"x": [1, 10, 100, 1000, 10000],
          "y": [0.001, 0.01, 0.1, 1, 10]}

    c = pt.chart(data_width=400, data_height=190, title="math text",
                 xlabel="dose (mol·L" + pt.superscript("-1") + ")",
                 ylabel="H" + pt.subscript("2") + "O flux (kg·m"
                        + pt.superscript("-2") + ")")
    c.add_line(df, aes(x="x", y="y"), marker="o")
    c.xscale("log")
    c.yscale("log")
    c.xticks(format="power10")
    c.yticks(format="power10")
    df2 = {"x": [10], "y": [1], "s": ["BRCA1"]}
    c.add_text(df2, aes(x="x", y="y", label="s"), fontstyle="italic")
    return c


def chart_minor_grid():
    # which="both": thin minor lines between the major ones, auto
    # positions on the linear axes without minor ticks enabled.
    df = {"x": [0, 1, 2, 3, 4, 5], "y": [0, 1, 4, 9, 16, 25]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=400, data_height=180,
                 title="minor grid", xlabel="x", ylabel="y", gridlines="both")
    c.add_line(marker="o")
    return c


def chart_minor_grid_log():
    # log x: minor gridlines at the 2..9 decade multipliers, drawn from
    # c.gridlines(which=) with explicit minor ticks shown too.
    df = {"x": [1, 10, 100, 1000, 10000], "y": [1, 5, 12, 25, 60]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=400, data_height=180,
                 title="minor grid log", xlabel="freq", ylabel="amp")
    c.add_line(marker="o")
    c.xscale("log")
    c.xticks(minor=True)
    c.gridlines(which="both")
    return c


def chart_minor_ticks_log():
    df = {"x": [1, 10, 100, 1000, 10000], "y": [1, 5, 12, 25, 60]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=400, data_height=180,
                 title="minor ticks log", xlabel="freq", ylabel="amp")
    c.add_line(marker="o")
    c.xscale("log")
    c.xticks(minor=True)
    return c


def chart_reverse_y():
    # Reversed y axis: classic oceanography depth profile (0 on top).
    times = list(range(8))
    depths = [10, 28, 65, 130, 220, 360, 480, 620]
    df = {"x": times, "y": depths}

    c = pt.chart(df, aes(x="x", y="y"), data_width=320, data_height=180,
                 title="depth profile", xlabel="time", ylabel="depth (m)")
    c.add_line(marker="o")
    c.yscale("linear", reverse=True)
    return c


def chart_sqrt_y():
    # sqrt scale on y compresses large counts while keeping small ones visible.
    df = {"bin": ["A", "B", "C", "D", "E", "F", "G"],
          "count": [1, 9, 25, 49, 100, 256, 484]}
    c = pt.chart(df, aes(x="bin", y="count"), data_width=320, data_height=180,
                 title="sqrt y", xlabel="bin", ylabel="count")
    c.add_bar()
    c.yscale("sqrt")
    return c


def chart_symlog_x():
    # Symlog on x: spans both signs across many orders of magnitude, with
    # a linear band around 0. Signed-magnitude domains.
    xs = [-2000, -250, -25, -2, -0.5, 0, 0.5, 2, 25, 250, 2000]
    ys = [abs(x) ** 0.5 for x in xs]
    df = {"x": xs, "y": ys}

    c = pt.chart(df, aes(x="x", y="y"), data_width=400, data_height=180,
                 title="symlog axis", xlabel="signed magnitude", ylabel="sqrt(|x|)")
    c.add_scatter(size=2.5)
    c.xscale("symlog", linthresh=1.0)
    return c


def chart_tick_format_string():
    # Format string: '{:.0%}' renders y-ticks as percentages.
    df = {"x": list(range(8)), "y": [0.05, 0.12, 0.18, 0.27, 0.42, 0.55, 0.71, 0.88]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=320, data_height=180,
                 title="completion rate", xlabel="week", ylabel="rate")
    c.add_line()
    c.yticks(format="{:.0%}")
    return c


def chart_tick_format_named():
    # Named formatter: `pt.formatters.money` handles the K/M compaction.
    df = {"x": list(range(8)), "y": [1200, 4500, 8300, 18000, 45000, 92000, 410000, 1_250_000]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=320, data_height=180,
                 title="revenue", xlabel="month", ylabel="revenue")
    c.add_line()
    c.yticks(format="money")
    return c


def chart_time_axis_dates():
    # Auto-detect: date values on x → time scale, calendar-aligned ticks.
    dates = [datetime.date(2024, 1, 1) + datetime.timedelta(days=30 * i) for i in range(12)]
    vals  = [10, 12, 9, 15, 18, 22, 25, 21, 17, 14, 12, 11]
    df = {"x": dates, "y": vals}

    c = pt.chart(df, aes(x="x", y="y"), data_width=400, data_height=180,
                 title="2024 monthly units", ylabel="units", gridlines=True)
    c.add_line(marker="o")
    return c


def chart_time_axis_hours():
    # Hour-resolution datetimes on the y-axis — labels stack vertically so a
    # full day's worth of "HH:MM" ticks have room without rotation.
    base = datetime.datetime(2024, 6, 1, 0, 0, tzinfo=datetime.timezone.utc)
    times = [base + datetime.timedelta(hours=i) for i in range(0, 25, 2)]
    vals  = [math.sin(i / 4) * 5 + 10 for i in range(len(times))]
    df = {"x": vals, "y": times}

    c = pt.chart(df, aes(x="x", y="y"), data_width=220, data_height=320,
                 title="signal over a day", xlabel="value", ylabel="time (UTC)")
    c.add_line()
    return c


PLOTS = {
    "category_x_scatter": chart_category_x_scatter,
    "category_x_order": chart_category_x_order,
    "category_y_scatter": chart_category_y_scatter,
    "category_y_order": chart_category_y_order,
    "hide_yticks": chart_hide_yticks,
    "xticks_rotation": chart_xticks_rotation,
    "xticks_top_share_x": chart_xticks_top_share_x,
    "xticks_flipped_sides": chart_xticks_flipped_sides,
    "xticks_inward": chart_xticks_inward,
    "xticks_marks_off": chart_xticks_marks_off,
    "xticks_explicit": chart_xticks_explicit,
    "category_padding_0": chart_category_padding_zero,
    "errorbar_category_x": chart_errorbar_category_x,
    "dendrogram_explicit_xticks": chart_dendrogram_explicit_xticks,
    "long_rotated_xticks": chart_long_rotated_xticks,
    "xticks_fontstyle_italic": chart_xticks_fontstyle_italic,
    "xticks_decoration": chart_xticks_decoration,
    "xticks_rotation_negative": chart_xticks_rotation_negative,
    "ticks_step": chart_ticks_step,
    "ticks_count": chart_ticks_count,
    "minor_ticks_linear": chart_minor_ticks_linear,
    "power10_math_text": chart_power10_math_text,
    "minor_grid": chart_minor_grid,
    "minor_grid_log": chart_minor_grid_log,
    "minor_ticks_log": chart_minor_ticks_log,
    "reverse_y": chart_reverse_y,
    "sqrt_y": chart_sqrt_y,
    "symlog_x": chart_symlog_x,
    "tick_format_string": chart_tick_format_string,
    "tick_format_named": chart_tick_format_named,
    "time_axis_dates": chart_time_axis_dates,
    "time_axis_hours": chart_time_axis_hours,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_axis_baseline(name, fn, baseline_compare):
    baseline_compare("chart_axis", name, fn().to_svg())


def test_log_scale_single_point_domain():
    # lo == hi padding must stay positive on log scales — the linear
    # ±0.5 pad used to push a value < 0.5 to a negative bound and crash
    # with "log scale needs strictly positive domain".
    import re
    df = {"x": [0.3], "y": [1.0]}
    c = pt.chart(df, aes(x="x", y="y"))
    c.add_scatter()
    c.xscale("log")
    m = re.search(r'data-plotlet-xlim="([^"]*)"', c.to_svg())
    lo, hi = (float(v) for v in m.group(1).split(","))
    assert 0 < lo < 0.3 < hi
