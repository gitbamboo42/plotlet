"""Smoke test for every extension in `plotlet.extensions`.

Imports each extension module, calls its `demo()` function, and checks the
returned Chart serializes to non-empty SVG. This catches:
  - import-path breakage (e.g., after a core refactor that moves modules)
  - registration-time errors in `pt.add_artist(...)`
  - runtime errors in the extension's `draw` callback
  - SVG-serialization failures

It does NOT compare against committed baselines — extensions evolve faster
than core, and 64 baseline files would bloat the repo. For visual-regression
coverage of the most-trafficked extensions, see `tests/test_chart.py` (which
exercises the public chart API that extensions consume).
"""
from __future__ import annotations

import importlib
import pkgutil
import sys

import plotlet.extensions


def _iter_extensions():
    for info in pkgutil.iter_modules(plotlet.extensions.__path__):
        if info.name.startswith("_"):
            continue
        yield info.name


def main() -> int:
    failed = []
    no_demo = []
    ok = 0
    total = 0

    for name in sorted(_iter_extensions()):
        total += 1
        try:
            mod = importlib.import_module(f"plotlet.extensions.{name}")
        except Exception as e:
            failed.append((name, f"import {type(e).__name__}: {e}"))
            print(f"FAIL   extensions/{name}.py  (import {type(e).__name__})")
            continue

        if not hasattr(mod, "demo"):
            no_demo.append(name)
            print(f"MISS   extensions/{name}.py  (no demo() function)")
            continue

        try:
            chart = mod.demo()
        except Exception as e:
            failed.append((name, f"demo() {type(e).__name__}: {e}"))
            print(f"FAIL   extensions/{name}.py  (demo() {type(e).__name__})")
            continue

        try:
            svg = chart.to_svg()
        except Exception as e:
            failed.append((name, f"to_svg() {type(e).__name__}: {e}"))
            print(f"FAIL   extensions/{name}.py  (to_svg() {type(e).__name__})")
            continue

        if "<svg" not in svg:
            failed.append((name, "no <svg in output"))
            print(f"FAIL   extensions/{name}.py  (no <svg in output)")
            continue

        ok += 1
        print(f"OK     extensions/{name}.py  ({len(svg)} chars)")

    n_failed = len(failed) + len(no_demo)
    if n_failed:
        print(f"\n{n_failed} of {total} extension smoke tests FAILED")
        for n, e in failed:
            print(f"  FAIL  {n}: {e[:120]}")
        for n in no_demo:
            print(f"  MISS  {n}: no demo() function")
        return 1
    print(f"\n{ok} of {total} extension smoke tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
