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

import plotlet.extensions
import pytest


# Extensions that get byte-compared baselines. Add an extension here when
# 2+ cookbook recipes (or core tests) depend on its rendering.
BASELINE_EXTENSIONS = {"annotation_strip", "bubble_grid", "labels_strip",
                       "significance_brackets"}


def _iter_extensions():
    for info in pkgutil.iter_modules(plotlet.extensions.__path__):
        if info.name.startswith("_"):
            continue
        yield info.name


_ALL_EXTENSIONS = sorted(_iter_extensions())


@pytest.mark.parametrize("ext_name", _ALL_EXTENSIONS)
def test_extension_smoke(ext_name):
    """Every extension must import cleanly, expose a `demo()` callable, and
    produce SVG output. Catches registration/import/draw regressions across
    all ~45 extensions without per-file baseline files."""
    mod = importlib.import_module(f"plotlet.extensions.{ext_name}")
    assert hasattr(mod, "demo"), (
        f"extensions/{ext_name}.py has no `demo()` function"
    )
    chart = mod.demo()
    svg = chart.to_svg()
    assert "<svg" in svg, f"extensions/{ext_name}.py demo().to_svg() produced no <svg>"


@pytest.mark.parametrize("ext_name", sorted(BASELINE_EXTENSIONS))
def test_extension_baseline(ext_name, baseline_compare):
    """Byte-compare demo() output for the curated set in
    `BASELINE_EXTENSIONS`. Promote here when 2+ cookbook recipes
    (or core tests) depend on the extension's rendering."""
    mod = importlib.import_module(f"plotlet.extensions.{ext_name}")
    baseline_compare("extensions", ext_name, mod.demo().to_svg())
