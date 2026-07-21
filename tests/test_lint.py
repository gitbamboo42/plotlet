"""Behavioral tests for `plotlet.lint` — a known-clean figure produces no
warnings, and an engineered tick-label pile-up is detected. Guards the
lint from regressing to always-empty (nothing else exercises it; the
gallery lint report is a non-test script)."""
import plotlet as pt
from plotlet.lint import lint


def test_lint_clean_chart_is_quiet():
    c = pt.chart({"x": [1, 2, 3], "y": [1, 4, 9]})
    c.add_line(x="x", y="y")
    assert lint(c) == []


def test_lint_detects_crowded_tick_labels():
    # Long unrotated category labels on a 120px-wide panel must collide.
    c = pt.chart({"cat": [f"long label {i}" for i in range(8)],
                  "v": list(range(8))},
                 data_width=120, data_height=80)
    c.add_bar(x="cat", y="v")
    warnings = lint(c)
    assert warnings, "expected overlap warnings on a crowded axis"
    assert any("tick-x" in str(w) and "overlap" in str(w) for w in warnings)
