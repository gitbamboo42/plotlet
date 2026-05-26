"""Smoke + baseline tests for `plotlet.extensions`.

Two passes:

1. **Smoke test** (every extension) — import the module, call `demo()`, check
   it serializes to non-empty SVG. Catches import-path breakage, registration
   errors, draw-callback exceptions, and serialization failures. Fast and
   broad; no baseline file required.

2. **Baseline test** (curated set in `BASELINE_EXTENSIONS`) — byte-compare
   `demo().to_svg()` against `tests/baseline_images/extensions/<name>.svg`.
   Reserved for extensions that are load-bearing for 2+ cookbook recipes,
   where silent visual drift would propagate downstream. Promote here only
   when an extension graduates from "single-file utility" to "depended on."

The vast majority of extensions stay smoke-only — 45+ baseline files for
leaf artists with one or zero callers would just be repo bloat. The
`tests/test_chart.py` baselines cover the chart API surface that all
extensions consume.

Usage:
    python tests/test_extensions.py            # smoke + baseline check
    python tests/test_extensions.py --update   # regenerate baselines
    python tests/test_extensions.py --gallery  # write baseline gallery HTML
"""
from __future__ import annotations

import importlib
import pkgutil
import sys

import plotlet.extensions

import _runner


# Extensions that get byte-compared baselines. Add an extension here when
# 2+ cookbook recipes (or core tests) depend on its rendering.
BASELINE_EXTENSIONS = {"annotation_strip"}


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
        smoke_rc = 1
    else:
        print(f"\n{ok} of {total} extension smoke tests passed")
        smoke_rc = 0

    # Baseline pass: byte-compare demo() output for the curated set.
    print()
    plots = {}
    for name in sorted(BASELINE_EXTENSIONS):
        mod = importlib.import_module(f"plotlet.extensions.{name}")
        plots[name] = mod.demo
    baseline_rc = _runner.run("extensions", plots)

    return 1 if (smoke_rc or baseline_rc) else 0


if __name__ == "__main__":
    sys.exit(main())
