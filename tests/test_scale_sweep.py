"""Every registered artist renders sanely on nonlinear scales — or is
excused here with a reason.

The scale machinery guarantees pointwise mapping (`scale(v)` is correct
on every kind), but arithmetic *between* data values — offsets, widths,
bands, baselines — happens in data space, where a result can be
unmappable (a zero baseline on log) and leak a literal `nan` into the
SVG. This sweep renders each artist on log / symlog / sqrt and asserts
no non-finite coordinate reaches the output.

Every artist name must appear in exactly one of SWEEP or SKIP — a new
artist fails `test_every_artist_swept_or_excused` until its author
decides which, so nothing dodges the sweep silently.

Known leaks are strict xfails: fixing one turns it XPASS, which fails
the run until its entry is removed from KNOWN_NAN_ON_LOG.
"""
import re

import pytest

import plotlet as pt
from plotlet import aes
from plotlet.registry import all_artist_names, get_artist

XS = [1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0, 34.0]
YS = [2.0, 4.0, 3.5, 9.0, 20.0, 15.0, 55.0, 90.0]
CATS = ["a", "a", "b", "b", "c", "c", "d", "d"]


def _xy():
    return pt.chart({"x": XS, "y": YS}, aes(x="x", y="y"))


def _cat_y():
    return pt.chart({"g": CATS, "y": YS}, aes(x="g", y="y"))


def _x_only():
    return pt.chart({"x": XS}, aes(x="x"))


def _chart_errorbar():
    df = {"x": XS, "y": YS, "sd": [v * 0.1 for v in YS]}
    c = pt.chart(df, aes(x="x", y="y"))
    c.add_errorbar(aes(yerr="sd"))
    return c


def _chart_fill_between():
    df = {"x": XS, "lo": [v * 0.5 for v in YS], "hi": [v * 2 for v in YS]}
    c = pt.chart(df, aes(x="x"))
    c.add_fill_between(aes(y1="lo", y2="hi"))
    return c


def _chart_text():
    df = {"x": XS, "y": YS, "lab": CATS}
    c = pt.chart(df, aes(x="x", y="y", label="lab"))
    c.add_text()
    return c


def _chart_qq():
    c = pt.chart({"s": YS}, aes(sample="s"))
    c.add_qq()
    return c


def _chart_ridge():
    # Ridge draws the value distribution along x; categories band on y.
    c = pt.chart({"g": CATS, "v": YS}, aes(x="g", y="v"))
    c.add_ridge()
    return c


def _add(method, base=_xy, **kw):
    def factory():
        c = base()
        getattr(c, method)(**kw)
        return c
    return factory


# name -> (continuous axis to sweep, chart factory)
SWEEP = {
    "scatter":     ("y", _add("add_scatter")),
    "line":        ("y", _add("add_line")),
    "step":        ("y", _add("add_step")),
    "area":        ("y", _add("add_area")),
    "fill_between": ("y", _chart_fill_between),
    "errorbar":    ("y", _chart_errorbar),
    "pointplot":   ("y", _add("add_pointplot", base=_cat_y)),
    "rug":         ("x", _add("add_rug", base=_x_only)),
    "text":        ("y", _chart_text),
    "strip":       ("y", _add("add_strip", base=_cat_y)),
    "swarm":       ("y", _add("add_swarm", base=_cat_y)),
    "boxplot":     ("y", _add("add_boxplot", base=_cat_y)),
    "violin":      ("y", _add("add_violin", base=_cat_y)),
    "ecdf":        ("x", _add("add_ecdf", base=_x_only)),
    "qq":          ("y", _chart_qq),
    "regression":  ("y", _add("add_regression")),
    "hexbin":      ("y", _add("add_hexbin", gridsize=6)),
    "hist2d":      ("y", _add("add_hist2d", bins=4)),
    "kde_2d":      ("y", _add("add_kde_2d", n_grid=16)),
    "density_1d":  ("x", _add("add_density_1d", base=_x_only)),
    "freqpoly":    ("x", _add("add_freqpoly", base=_x_only)),
    "hist":        ("x", _add("add_hist", base=_x_only)),
    "bar":         ("y", _add("add_bar", base=_cat_y)),
    "numeric_bar": ("y", _add("add_numeric_bar")),
    "ridge":       ("x", _chart_ridge),
}

# name -> why the sweep doesn't apply
SKIP = {
    "annotate":  "literal-coordinate decoration; maps pointwise",
    "axhline":   "literal-coordinate decoration; maps pointwise",
    "axhspan":   "literal-coordinate decoration; maps pointwise",
    "axline":    "literal-coordinate decoration; maps pointwise",
    "axvline":   "literal-coordinate decoration; maps pointwise",
    "axvspan":   "literal-coordinate decoration; maps pointwise",
    "hlines":    "literal-coordinate decoration; maps pointwise",
    "vlines":    "literal-coordinate decoration; maps pointwise",
    "rect":      "literal-coordinate decoration; maps pointwise",
    "polygon":   "literal-coordinate decoration; maps pointwise",
    "polyline":  "literal-coordinate decoration; maps pointwise",
    "heatmap":          "categorical band axes; no continuous axis to sweep",
    "annotation_strip": "categorical band axes; no continuous axis to sweep",
    "chord_links":  "sector/circular artists; no Cartesian continuous axis",
    "chord_ribbon": "sector/circular artists; no Cartesian continuous axis",
    "image_cmap": "index-linear image axes with tight extents",
    "image_rgba": "index-linear image axes with tight extents",
    "contour":    "matrix grid; extent corners map pointwise",
    "dendrogram": "derived merge-height axis",
}

# Force-zero artists must include 0, which log cannot map: the loud
# error is the designed behavior.
RAISES_ON_LOG = {"bar", "numeric_bar"}

# Artists currently known to leak non-finite coordinates on log axes.
# An entry here becomes a strict xfail: fixing the artist flips it to
# XPASS, which fails the run until the entry is removed — the list
# can't go stale in either direction. (Empty since the band/baseline
# emitters clamp unmappable bounds to the panel edge via edge_px.)
KNOWN_NAN_ON_LOG = set()

# The journal type an artist's SVG group carries (step records as line).
EMITTED_TYPE = {"step": "line"}

_NONFINITE = re.compile(r"-?\b(nan|NaN|inf|Infinity)\b")


def test_every_artist_swept_or_excused():
    # Core artists only: other test modules may import plotlet.extensions,
    # whose artists register globally but are the extensions repo's to sweep.
    names = {n for n in all_artist_names()
             if get_artist(n).record.__module__.startswith("plotlet.artists")}
    covered = set(SWEEP) | set(SKIP)
    assert names == covered, (
        f"unswept artists (add to SWEEP or SKIP): {sorted(names - covered)}; "
        f"stale entries: {sorted(covered - names)}"
    )
    assert not set(SWEEP) & set(SKIP)


def _params():
    for name, (axis, factory) in SWEEP.items():
        for scale in ("log", "symlog", "sqrt"):
            marks = ()
            if scale == "log" and name in KNOWN_NAN_ON_LOG:
                marks = (pytest.mark.xfail(
                    strict=True, reason="known: leaks nan into SVG on log"),)
            yield pytest.param(name, axis, factory, scale,
                               id=f"{name}-{scale}", marks=marks)


@pytest.mark.parametrize("name,axis,factory,scale", _params())
def test_artist_renders_sanely_on_scale(name, axis, factory, scale):
    c = factory()
    getattr(c, f"{axis}scale")(scale)
    if scale == "log" and name in RAISES_ON_LOG:
        with pytest.raises(ValueError):
            c.to_svg()
        return
    svg = c.to_svg()
    assert f'data-plotlet-type="{EMITTED_TYPE.get(name, name)}"' in svg
    m = _NONFINITE.search(svg)
    assert m is None, f"non-finite coordinate {m.group()!r} in SVG"
