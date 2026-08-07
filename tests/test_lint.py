"""Behavioral tests for `plotlet.lint` — a known-clean figure produces no
warnings, and an engineered tick-label pile-up is detected. Guards the
lint from regressing to always-empty (nothing else exercises it; the
gallery lint report is a non-test script)."""
import re

import plotlet as pt
from plotlet import aes
from plotlet.lint import lint


def test_lint_is_exported_on_pt():
    # `pt.lint(c)` is the documented spelling; the submodule import
    # keeps working via sys.modules (os.path-style shadowing).
    assert pt.lint is lint


def test_lint_clean_chart_is_quiet():
    df = {"x": [1, 2, 3], "y": [1, 4, 9]}
    c = pt.chart(df)
    c.add_line(aes(x="x", y="y"))
    assert lint(c) == []


def test_lint_detects_crowded_tick_labels():
    # Long unrotated category labels on a 120px-wide panel must collide.
    df = {"cat": [f"long label {i}" for i in range(8)],
          "v": list(range(8))}
    c = pt.chart(df,
                 data_width=120, data_height=80)
    c.add_bar(aes(x="cat", y="v"))
    warnings = lint(c)
    assert warnings, "expected overlap warnings on a crowded axis"
    assert any("tick-x" in str(w) and "overlap" in str(w) for w in warnings)


def test_lint_clusters_one_crowded_axis_into_one_warning():
    # 6 colliding labels → one clustered warning naming the pair count
    # and the worst pair's texts, not O(N²) restatements.
    df = {"cat": [f"a very long category label {i}" for i in range(6)],
          "v": list(range(6))}
    c = pt.chart(df, data_width=200, data_height=100)
    c.add_bar(aes(x="cat", y="v"))
    warnings = [w for w in lint(c) if w.region == "tick-x ↔ tick-x"]
    assert len(warnings) == 1
    msg = str(warnings[0])
    assert "overlapping pairs among" in msg
    assert "category label" in msg   # names the colliding labels


def test_lint_inside_legend_is_structural():
    # A legend the user placed inside the panel overlaps it on purpose.
    df = {"x": [1, 2, 3], "y": [1.0, 2.0, 3.0], "g": ["a", "a", "b"]}
    c = pt.chart(df, aes(x="x", y="y", color="g"),
                 data_width=240, data_height=160)
    c.add_line()
    c.legend(True, position="top-left")
    assert lint(c) == []


def test_lint_circular_chrome_is_structural():
    # Circular charts keep all chrome inside the panel rect by design —
    # tick labels and sector walls must not read as overlap bugs.
    import math
    n = 12
    df = {"t": [i / n for i in range(n + 1)],
          "v": [0.5 + 0.35 * math.sin(2 * math.pi * i / n)
                for i in range(n + 1)]}
    c = pt.chart(df, aes(x="t", y="v"))
    c.add_line()
    c.coordinate(pt.CircularCoordinate())
    assert lint(c) == []


def test_lint_inset_chrome_is_structural():
    # An inset lives inside the parent panel by design.
    df = {"x": [1, 2, 3, 4], "y": [1.0, 3.0, 2.0, 4.0]}
    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line()
    ins = c.inset((0.55, 0.55, 0.4, 0.4))
    ins.add_scatter(df, aes(x="x", y="y"))
    assert lint(c) == []


def test_lint_rotated_labels_use_precise_polygons():
    # 45°-rotated labels sit cleanly side by side — their AABBs overlap
    # hugely but the actual rotated rectangles don't. Must not flag.
    df = {"s": ["sample_alpha_2024", "sample_beta_2024", "sample_gamma_2024",
                "sample_delta_2024", "sample_epsilon_2024"],
          "n": [12, 7, 19, 14, 9]}
    c = pt.chart(df, aes(x="s", y="n"), data_width=300, data_height=180)
    c.add_bar()
    c.xticks(rotation=45)
    assert lint(c) == []


def test_lint_rotated_labels_still_flag_when_truly_crammed():
    df = {"s": [f"extremely_long_sample_label_{i}_2024" for i in range(10)],
          "n": list(range(10))}
    c = pt.chart(df, aes(x="s", y="n"), data_width=100, data_height=100)
    c.add_bar()
    c.xticks(rotation=45)
    warnings = lint(c)
    assert any("tick-x ↔ tick-x" in str(w) for w in warnings)


def test_lint_tall_legend_does_not_stretch_or_clip_panels():
    # A pt.legend leaf taller than the chart row hands the charts more
    # room than their canvas. The data region must stay the size the
    # user set (slack goes into the margin, like _pad_canvases does
    # between data siblings) — stretching it used to draw a denser
    # tick set than the margins were measured for, clipping labels off
    # the figure edge.
    import math
    xs = [i * 0.2 for i in range(50)]
    df = {"x": xs, "y": [math.sin(x) for x in xs],
          "mass": [1.0 + (i % 7) for i in range(50)]}

    def chart(title):
        c = pt.chart(df, aes(x="x", y="y", size="mass"), title=title,
                     data_width=200, data_height=140)
        c.add_scatter(sizes=(1, 5), label="signal")
        return c

    fig = (chart("a") | chart("b") | chart("c")) | pt.legend()
    assert [w for w in lint(fig) if w.check == "edge_clip"] == []
    # and the data regions render at exactly the set 200×140
    areas = re.findall(r'data-plotlet-data-area="([^"]+)"', fig.to_svg())
    assert all(a.endswith(",200,140") for a in areas)
