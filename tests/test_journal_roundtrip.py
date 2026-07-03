"""Journal round-trip correctness: `from_journal(to_journal(fig)).to_svg()`
must be byte-identical to `fig.to_svg()` for every baseline plot.

The invariant is stronger than the SVG baselines themselves: any state
that lives in a field but doesn't survive the journal would render
correctly on the tree path and wrong on the journal path — this test
would catch it.

Reuses every `PLOTS` registry the codebase already has for baseline
comparison, plus the extension demos.

NOTE: JSON round-trip (`pt.to_json` / `pt.from_json`) is NOT covered
here yet. The `_json_layer` needs envelopes for tuple / set / date /
datetime before the JSON path is round-trip-clean across all fixtures.
Follow-up: add those envelopes, then add a `test_json_roundtrip`
parametrized over the same PLOTS list."""
from __future__ import annotations

import pytest

import plotlet as pt


def _collect_plots():
    """Gather (label, factory) pairs from every baseline test module.

    Modules keep a `PLOTS = {name: fn}` registry; the extensions test
    walks a directory of modules with a `demo()` function. Pull them
    all so the round-trip runs across the same surface as baselines."""
    plots: list[tuple[str, callable]] = []

    def add(source, name, fn):
        plots.append((f"{source}::{name}", fn))

    from tests import test_chart, test_layout_diagram, test_sectors
    from tests import test_subplots, test_legend, test_attachments
    from tests import test_circular_coordinate, test_themes
    for mod, source in [
        (test_chart, "chart"),
        (test_layout_diagram, "layout_diagram"),
        (test_sectors, "sectors"),
        (test_subplots, "subplots"),
        (test_legend, "legend"),
        (test_attachments, "attachments"),
        (test_circular_coordinate, "circular"),
        (test_themes, "themes"),
    ]:
        for name, fn in getattr(mod, "PLOTS", {}).items():
            add(source, name, fn)

    # Extension demos — every `plotlet/extensions/<name>.py` exposes
    # `demo() -> Chart|Layout` (per test_extensions.py smoke test).
    from tests.test_extensions import _ALL_EXTENSIONS
    import importlib
    for name in _ALL_EXTENSIONS:
        mod = importlib.import_module(f"plotlet.extensions.{name}")
        if hasattr(mod, "demo"):
            add("extensions", name, mod.demo)

    return plots


PLOTS = _collect_plots()


@pytest.mark.parametrize("label,fn", PLOTS, ids=[p[0] for p in PLOTS])
def test_journal_roundtrip(label, fn):
    """Original SVG and journal-reconstructed SVG must match byte-for-byte."""
    fig = fn()
    svg_original = fig.to_svg()

    journal = pt.to_journal(fig)
    fig_from_journal = pt.from_journal(journal)
    svg_from_journal = fig_from_journal.to_svg()

    assert svg_original == svg_from_journal, (
        f"{label}: round-trip diverged "
        f"(original={len(svg_original)} bytes, "
        f"replayed={len(svg_from_journal)} bytes)"
    )
