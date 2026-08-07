"""`pt.describe` — text summary read purely from the `data-plotlet-*`
schema, so it reports what the finished SVG actually says."""
import plotlet as pt
from plotlet import aes


def _revenue_chart():
    df = {"day": [1, 2, 3, 4], "usd": [10.5, 12.3, 11.0, 14.7]}
    c = pt.chart(df, aes(x="day", y="usd"))
    c.add_line(label="actual")
    c.title("Daily revenue").xlabel("day").ylabel("USD")
    return c


def test_describe_line_chart():
    out = pt.describe(_revenue_chart())
    lines = out.splitlines()
    assert lines[0].startswith("SVG ") and "schema=2" in lines[0]
    assert 'PANEL 0 title="Daily revenue" xlabel="day" ylabel="USD"' in out
    assert "xscale=linear" in out and "yscale=linear" in out
    assert 'ARTIST 0 line label="actual" color=#1f77b4' in out
    assert "n=4" in out and "x-min=1" in out and "y-max=14.7" in out


def test_describe_categorical_axis_and_grid():
    df = {"q": ["Q1", "Q2", "Q3", "Q4"], "v": [3.0, 5.0, 2.0, 6.0]}
    c1 = pt.chart(df, aes(x="q", y="v"))
    c1.add_bar()
    c2 = _revenue_chart()
    out = pt.describe(pt.grid([[c1, c2]]))
    assert "xcategories=[Q1,Q2,Q3,Q4]" in out
    assert "PANEL 0" in out and "PANEL 1" in out


def test_describe_accepts_raw_svg():
    # A raw SVG string (e.g. read back from a saved file) works too.
    c = _revenue_chart()
    assert pt.describe(c.to_svg()) == pt.describe(_revenue_chart())


def test_describe_recurses_into_insets():
    c = _revenue_chart()
    df = {"day": [1, 2], "usd": [10.5, 12.3]}
    ins = c.inset((0.6, 0.6, 0.35, 0.35))
    ins.add_scatter(df, aes(x="day", y="usd"))
    out = pt.describe(c)
    assert "INSET" in out
    assert "PANEL 1" in out   # the inset's own panel, numbered after the host


def test_describe_shows_standalone_legend_leaf():
    c = _revenue_chart()
    fig = c | pt.legend(c)
    assert "LEGEND" in pt.describe(fig)
