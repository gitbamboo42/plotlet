#!/usr/bin/env python3
"""Smoke tests for the dimensional API.

    python tests/test_units.py    # run; exit 1 on failure

Two layers:

1. `_to_px` string handling (`"4in"`, `"10cm"`, `"100mm"`, `"72pt"`,
   `"30px"`, bare-number strings) and end-to-end `pt.chart(...)`
   constructor wiring. Internal layout math stays in
   pixels — these tests assert that string inputs resolve to the same
   pixel dimensions that bare ints would, so SVG output is byte-identical.
   Conversion factors are CSS standard: 96 px/in, 2.54 cm/in, 72 pt/in.

2. The body-first geometric promise: a chart asked for `data_width=W,
   data_height=H` actually renders a data region of exactly W × H. The
   spines bound that region, so we extract them from the rendered SVG
   and check the rect they form. Also covers standalone-vs-in-layout
   parity for the no-sibling case (1×1 `pt.grid`), where per-column /
   row coordination has nothing to coordinate against and the data
   region should be identical to the standalone render.
"""
from __future__ import annotations

import re
import sys

import plotlet as pt
from plotlet.core import _to_px


# Spines have all-integer-valued coords — `0` and `iw` / `ih`. Standalone
# emits them as bare ints (`240`); the layout path emits floats (`240.0`)
# because iw/ih come from float arithmetic. The regex accepts both.
# Tick lines use `_TICK_LEN = 3.5`, so their endpoints always carry a
# non-zero decimal (e.g. `176.5`) and can't masquerade as a spine even
# when their other coord happens to be integer-valued (`0.00`, `80.00`).
# Grid lines use `_GRID` (not `#000000`) so they're filtered by stroke.
_INT_COORD = r'\d+(?:\.0+)?'
_SPINE_LINE_RE = re.compile(
    rf'<line x1="({_INT_COORD})" y1="({_INT_COORD})" '
    rf'x2="({_INT_COORD})" y2="({_INT_COORD})" '
    rf'stroke="#000000" stroke-width="0\.8"/>'
)


def _spine_rects(svg: str) -> list[tuple[int, int]]:
    """Return one `(iw, ih)` per panel found in `svg`.

    A panel's four spines form a rect anchored at (0, 0) in panel-local
    coords (the outer `<g transform="translate(...)">` does the offset).
    Group consecutive matches into rects of four; iw/ih come from the
    max x/y across the group.
    """
    matches = _SPINE_LINE_RE.findall(svg)
    if len(matches) % 4 != 0:
        raise AssertionError(
            f"expected spine lines to come in groups of 4, got {len(matches)}"
        )
    rects: list[tuple[int, int]] = []
    for i in range(0, len(matches), 4):
        group = [tuple(int(float(c)) for c in m) for m in matches[i : i + 4]]
        iw = max(max(x1, x2) for x1, _, x2, _ in group)
        ih = max(max(y1, y2) for _, y1, _, y2 in group)
        rects.append((iw, ih))
    return rects


def _check(label, got, expected, failures):
    if got != expected:
        failures.append(f"FAIL {label}: got {got!r}, expected {expected!r}")


def _check_raises(label, fn, exc_type, failures):
    try:
        fn()
    except exc_type:
        return
    except Exception as ex:
        failures.append(f"FAIL {label}: expected {exc_type.__name__}, got "
                        f"{type(ex).__name__}: {ex}")
        return
    failures.append(f"FAIL {label}: expected {exc_type.__name__}, no exception raised")


def main() -> int:
    failures: list[str] = []

    # ---- _to_px direct ----------------------------------------------------
    # Bare ints / floats / None passthrough.
    _check("bare int",     _to_px(400),     400,  failures)
    _check("bare float",   _to_px(400.6),   401,  failures)  # round-half-even
    _check("None",         _to_px(None),    None, failures)

    # Absolute units, CSS standard.
    _check('"4in"',        _to_px("4in"),    384, failures)   # 4 * 96
    _check('"96px"',       _to_px("96px"),    96, failures)
    _check('"96"',         _to_px("96"),      96, failures)   # no suffix = px
    _check('"72pt"',       _to_px("72pt"),    96, failures)   # 72 * (96/72)
    _check('"2.54cm"',     _to_px("2.54cm"),  96, failures)   # 1 inch in cm
    _check('"25.4mm"',     _to_px("25.4mm"),  96, failures)   # 1 inch in mm

    # Whitespace + case insensitivity.
    _check('"  5 IN  "',   _to_px("  5 IN  "), 480, failures)
    _check('"5 cm"',       _to_px("5 cm"),     189, failures)  # round(5*37.795)

    # Errors.
    _check_raises("unknown unit",
                  lambda: _to_px("5parsec"), ValueError, failures)
    _check_raises("garbage string",
                  lambda: _to_px("abc"), ValueError, failures)
    _check_raises("bool rejected",
                  lambda: _to_px(True), TypeError, failures)
    _check_raises("list rejected",
                  lambda: _to_px([1, 2]), TypeError, failures)

    # ---- end-to-end via pt.chart -----------------------------------------
    # `data_width="4in"` should produce the same Chart as `data_width=384`.
    f_str = pt.chart(data_width="4in", data_height="3in")
    f_int = pt.chart(data_width=384,   data_height=288)
    _check("chart data_width via str",  f_str._data_width,  f_int._data_width,  failures)
    _check("chart data_height via str", f_str._data_height, f_int._data_height, failures)
    _check("chart canvas_width matches",  f_str._canvas_width,  f_int._canvas_width,  failures)
    _check("chart canvas_height matches", f_str._canvas_height, f_int._canvas_height, failures)

    # Mixed string / int.
    f_mix = pt.chart(data_width="4in", data_height=300)
    _check("mixed str/int data_width",  f_mix._data_width,  384, failures)
    _check("mixed str/int data_height", f_mix._data_height, 300, failures)

    # `pt.chart(canvas_width=…)` no longer exists (removed in 0.4.0 —
    # use `data_width=` to size the data region, or `.fit(canvas_width=…)`
    # on a composed chart to scale the data region until the figure fits
    # the target canvas).
    _check_raises("canvas_width on pt.chart raises",
                  lambda: pt.chart(canvas_width="6in"), TypeError, failures)
    _check_raises("canvas_height on pt.chart raises",
                  lambda: pt.chart(canvas_height=400), TypeError, failures)

    # `.fit()` accepts unit-suffixed strings just like data_width=.
    fit_str = pt.chart(data_width=400, data_height=240).fit(canvas_width="6in")
    fit_int = pt.chart(data_width=400, data_height=240).fit(canvas_width=576)
    if fit_str.to_svg() != fit_int.to_svg():
        failures.append("FAIL: .fit() with str vs int canvas_width differ")

    # `.fit()` rejects empty calls and non-positive dims.
    _check_raises(".fit() with no args raises",
                  lambda: pt.chart(data_width=100).fit(), ValueError, failures)
    _check_raises(".fit() with zero canvas_width raises",
                  lambda: pt.chart(data_width=100).fit(canvas_width=0),
                  ValueError, failures)

    # SVG byte-identity: string input → same SVG as numeric equivalent.
    if (pt.chart(data_width="4in", data_height="3in").to_svg()
            != pt.chart(data_width=384, data_height=288).to_svg()):
        failures.append("FAIL: SVG output for string vs numeric dim differs")

    # ---- spine-rect: data region matches data_width / data_height ---------
    # Render at several body sizes (including non-default and unit-suffixed)
    # and extract the spine rect from the rendered SVG. The body-first
    # promise: iw == data_width, ih == data_height — full stop. If
    # measure-driven margins ever start eating into the data region this
    # will catch it.
    spine_cases: list[tuple[object, object, int, int]] = [
        (200, 150, 200, 150),
        (500, 300, 500, 300),
        (640, 480, 640, 480),
        ("4in", "3in", 384, 288),     # string units, end-to-end
        ("10cm", "8cm", 378, 302),    # round(10*37.795), round(8*37.795)
    ]
    for dw, dh, exp_iw, exp_ih in spine_cases:
        svg = pt.chart(data_width=dw, data_height=dh).to_svg()
        rects = _spine_rects(svg)
        _check(f"spine rect count for ({dw!r},{dh!r})", len(rects), 1, failures)
        if rects:
            _check(f"spine iw  for data_width={dw!r}",  rects[0][0], exp_iw, failures)
            _check(f"spine ih  for data_height={dh!r}", rects[0][1], exp_ih, failures)

    # Same check on a chart with content (so spines render alongside data
    # artists / ticks / grid). Extra `<line>` elements should not pollute
    # the spine match.
    c = pt.chart(data_width=300, data_height=200, grid=True)
    c.line([1, 2, 3, 4], [1, 4, 9, 16], label="sq")
    rects = _spine_rects(c.to_svg())
    _check("spine rect count, chart with content", len(rects), 1, failures)
    if rects:
        _check("spine iw, chart with content", rects[0][0], 300, failures)
        _check("spine ih, chart with content", rects[0][1], 200, failures)

    # ---- standalone leaf == leaf inside 1×1 grid (no-sibling case) --------
    # Per-column / row margin coordination only kicks in when a sibling
    # actually pushes margins wider. With a single cell there's nothing
    # to coordinate against, so the data region inside the grid must
    # match the standalone render exactly.
    def _make_leaf():
        c = pt.chart(data_width=240, data_height=180, title="hi", xlabel="x")
        c.line([0, 1, 2, 3], [0, 1, 4, 9])
        return c

    standalone = _spine_rects(_make_leaf().to_svg())
    in_grid    = _spine_rects(pt.grid([[_make_leaf()]]).to_svg())
    _check("standalone rect count", len(standalone), 1, failures)
    _check("1×1 grid rect count",   len(in_grid),   1, failures)
    if standalone and in_grid:
        _check("standalone iw == 1×1 grid iw", in_grid[0][0], standalone[0][0], failures)
        _check("standalone ih == 1×1 grid ih", in_grid[0][1], standalone[0][1], failures)
        _check("standalone iw == data_width",  standalone[0][0], 240, failures)
        _check("standalone ih == data_height", standalone[0][1], 180, failures)

    if failures:
        for f in failures:
            print(f)
        print(f"\n{len(failures)} dimensional test(s) failed")
        return 1
    print("OK     dimensional API tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
