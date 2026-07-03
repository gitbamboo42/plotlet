"""Journal round-trip correctness: two paths, one contract.

  - In-memory:  `from_journal(to_journal(fig)).to_svg()` == `fig.to_svg()`
  - JSON:       `from_json(json.loads(json.dumps(to_json(fig)))).to_svg()`
                                                              == `fig.to_svg()`

The in-memory path exercises the journal event log itself. The JSON
path additionally exercises `_json_layer` — every non-JSON-native value
type (numpy / pandas / tuple / set / date / datetime / non-string-keyed
dict) must survive `json.dumps` and rehydrate identically.

Reuses every `PLOTS` registry the codebase already has for baseline
comparison. (Extension demos are round-tripped in the plotlet-extensions
repo's own copy of this test.)
"""
from __future__ import annotations

import json

import pytest

import plotlet as pt


def _collect_plots():
    """Gather (label, factory) pairs from every baseline test module.

    Modules keep a `PLOTS = {name: fn}` registry. Pull them all so the
    round-trip runs across the same surface as baselines."""
    plots: list[tuple[str, callable]] = []

    def add(source, name, fn):
        plots.append((f"{source}::{name}", fn))

    import test_chart, test_layout_diagram, test_sectors
    import test_subplots, test_legend, test_attachments
    import test_circular_coordinate, test_themes
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


@pytest.mark.parametrize("label,fn", PLOTS, ids=[p[0] for p in PLOTS])
def test_json_roundtrip(label, fn):
    """JSON round-trip via `pt.to_json` / `pt.from_json`. Exercises the
    `_json_layer` — every non-JSON-native value type must envelope through
    `json.dumps` / `json.loads` and rehydrate identically."""
    fig = fn()
    svg_original = fig.to_svg()

    blob = pt.to_json(fig)
    text = json.dumps(blob)
    fig_from_json = pt.from_json(json.loads(text))
    svg_from_json = fig_from_json.to_svg()

    assert svg_original == svg_from_json, (
        f"{label}: JSON round-trip diverged "
        f"(original={len(svg_original)} bytes, "
        f"replayed={len(svg_from_json)} bytes)"
    )
