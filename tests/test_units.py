#!/usr/bin/env python3
"""Unit-parsing smoke tests for the dimensional API.

    python tests/test_units.py    # run; exit 1 on failure

Covers `_to_px`'s string handling (`"4in"`, `"10cm"`, `"100mm"`, `"72pt"`,
`"30px"`, bare-number strings) and end-to-end `pt.figure(...)` /
`pt.chart(...)` constructor wiring. Internal layout math stays in pixels —
these tests assert that string inputs resolve to the same pixel
dimensions that bare ints would, so SVG output is byte-identical.

Conversion factors are CSS standard: 96 px/in, 2.54 cm/in, 72 pt/in.
"""
from __future__ import annotations

import sys

import plotlet as pt
from plotlet.core import _to_px


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

    # ---- end-to-end via Figure / pt.figure / pt.chart ---------------------
    # `data_width="4in"` should produce the same Figure as `data_width=384`.
    f_str = pt.figure(data_width="4in", data_height="3in")
    f_int = pt.figure(data_width=384,   data_height=288)
    _check("figure data_width via str",  f_str._data_width,  f_int._data_width,  failures)
    _check("figure data_height via str", f_str._data_height, f_int._data_height, failures)
    _check("figure canvas_width matches",  f_str._canvas_width,  f_int._canvas_width,  failures)
    _check("figure canvas_height matches", f_str._canvas_height, f_int._canvas_height, failures)

    # Positional strings.
    f_pos = pt.figure("4in", "3in")
    _check("positional str data_width",  f_pos._data_width,  f_int._data_width,  failures)
    _check("positional str data_height", f_pos._data_height, f_int._data_height, failures)

    # Mixed string / int.
    f_mix = pt.figure(data_width="4in", data_height=300)
    _check("mixed str/int data_width",  f_mix._data_width,  384, failures)
    _check("mixed str/int data_height", f_mix._data_height, 300, failures)

    # canvas_* path with string.
    f_canv = pt.figure(canvas_width="6in", canvas_height="4in")
    _check("canvas_width via str",  f_canv._canvas_width,  576, failures)  # 6 * 96
    _check("canvas_height via str", f_canv._canvas_height, 384, failures)  # 4 * 96

    # pt.chart() forwards correctly.
    c = pt.chart(data_width="4in", data_height="3in")
    _check("chart data_width via str",  c._fig._data_width,  384, failures)
    _check("chart data_height via str", c._fig._data_height, 288, failures)

    # Mutual-exclusion still fires with strings.
    _check_raises("data + canvas mutex with strings",
                  lambda: pt.figure(data_width="4in", canvas_width="6in"),
                  ValueError, failures)

    # SVG byte-identity: string input → same SVG as numeric equivalent.
    if pt.figure("4in", "3in").to_svg() != pt.figure(384, 288).to_svg():
        failures.append("FAIL: SVG output for string vs numeric dim differs")

    if failures:
        for f in failures:
            print(f)
        print(f"\n{len(failures)} unit-parse test(s) failed")
        return 1
    print(f"OK     unit-parse tests ({26} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
