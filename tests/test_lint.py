"""Behavioral tests for `plotlet.lint` — a known-clean figure produces no
warnings, and an engineered tick-label pile-up is detected. Guards the
lint from regressing to always-empty (nothing else exercises it; the
gallery lint report is a non-test script)."""
import plotlet as pt
from plotlet import aes
from plotlet.lint import lint


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
