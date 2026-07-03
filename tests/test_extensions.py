"""Smoke tests for the extensions that ship in *core* plotlet.

Most extensions live in the separate `plotlet-extensions` package (which has
its own suite). A few that core's own tests depend on ship here under
`plotlet.extensions`; this smoke-tests them — import cleanly, expose a
`demo()` callable, and serialize to SVG.

`curved_tree`, `annotation_strip`, and `numeric_bar` additionally get
byte-compared baselines via `test_chart.py` / `test_circular_coordinate.py`;
`chord_links` and `chord_ribbon` are smoke-only here.
"""
from __future__ import annotations

import importlib

import pytest


# The extensions kept in core (the rest live in the plotlet-extensions
# package). Keep in sync with `src/plotlet/extensions/`.
CORE_EXTENSIONS = ["numeric_bar", "curved_tree", "annotation_strip",
                   "chord_links", "chord_ribbon"]


@pytest.mark.parametrize("ext_name", CORE_EXTENSIONS)
def test_core_extension_smoke(ext_name):
    """Import the module (registers its artist), call `demo()`, and check it
    serializes to non-empty SVG."""
    mod = importlib.import_module(f"plotlet.extensions.{ext_name}")
    assert hasattr(mod, "demo"), f"extensions/{ext_name}.py has no `demo()` function"
    svg = mod.demo().to_svg()
    assert "<svg" in svg, f"extensions/{ext_name}.py demo().to_svg() produced no <svg>"
