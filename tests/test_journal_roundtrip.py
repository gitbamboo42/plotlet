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

import importlib
import json
import pathlib

import pytest

import plotlet as pt
from plotlet import aes

# Modules that consume this file's PLOTS rather than defining their own —
# importing them here would be a cycle.
_SKIP = {"test_journal_roundtrip", "test_ir", "test_ir_resolved"}


def _collect_plots():
    """Gather (label, factory) pairs from every baseline test module.

    Each baseline suite keeps a `PLOTS = {name: fn}` registry. Discover
    them by scanning the directory so the round-trip runs across the same
    surface as baselines — no hand-maintained module list to fall out of
    date when suites are added or split."""
    plots: list[tuple[str, callable]] = []
    here = pathlib.Path(__file__).parent
    for py in sorted(here.glob("test_*.py")):
        if py.stem in _SKIP:
            continue
        mod = importlib.import_module(py.stem)
        for name, fn in getattr(mod, "PLOTS", {}).items():
            plots.append((f"{py.stem[5:]}::{name}", fn))
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


def test_json_roundtrip_dates_in_dataframe():
    """Date cells inside normalized tabular data must wire as `$date`
    envelopes — `json_safe` recurses into the `$dataframe` payload.
    Regression: values used to pass through raw and crash json.dumps."""
    import datetime
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({
        "day": [datetime.date(2026, 1, 1), datetime.date(2026, 1, 2),
                datetime.date(2026, 1, 3)],
        "v": [1.5, 2.5, 2.0],
    })
    c = pt.chart(df, aes(x="day", y="v"))
    c.add_line()
    svg_original = c.to_svg()

    text = json.dumps(pt.to_json(c))
    assert '"$date"' in text
    assert pt.from_json(json.loads(text)).to_svg() == svg_original


def test_json_roundtrip_integer_dataframe():
    """All-int frames make `.values` an int64 ndarray; iterating it yields
    np.int64 cells, which are not `int` and crash json.dumps. Regression:
    normalization must hand the journal plain Python scalars."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    c = pt.chart(df, aes(x="a", y="b"))
    c.add_line()
    svg_original = c.to_svg()

    journal_df = c._data
    assert all(type(v) is int for row in journal_df.values for v in row)
    text = json.dumps(pt.to_json(c))
    assert pt.from_json(json.loads(text)).to_svg() == svg_original


def test_almost_primitive_rows_still_take_the_slow_path():
    """The walkers' `all_primitive` bail-out treats a row of plain
    scalars as one unit. This pins its safety condition: a row that is
    *almost* primitive — foreign scalars (numpy) or special values
    (dates) hiding past the first element — must fail the scan and get
    the full per-element treatment, everywhere from normalization to
    JSON."""
    np = pytest.importorskip("numpy")
    # numpy scalars after a long plain prefix: normalization must still
    # convert every one (json.dumps crashes on np.int64 if it doesn't).
    df = {"x": list(range(50)) + [np.int64(50), np.int64(51)],
          "y": [float(v) for v in range(50)] + [np.float64(2.5),
                                                np.float64(7.5)]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line()
    svg_original = c.to_svg()
    text = json.dumps(pt.to_json(c))
    assert pt.from_json(json.loads(text)).to_svg() == svg_original

    # A date past a long primitive prefix must still envelope as $date.
    import datetime
    from plotlet._json_layer import json_safe
    out = json_safe([1.0] * 50 + [datetime.date(2026, 1, 1)])
    assert out[-1] == {"$date": "2026-01-01"}
    assert out[:50] == [1.0] * 50


def test_data_lives_in_the_data_section():
    """Bulk tables sit once in the journal's data section; entries carry
    `{"$data": id}` refs. A chart and its bare artists share one table
    object, so they intern to a single entry."""
    df = {"x": [1, 2, 3], "y": [3, 1, 2]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line()
    c.add_scatter()

    journal = pt.to_journal(c)
    assert list(journal.data) == ["d1"]
    for entry in journal.entries:
        data = entry["kwargs"].get("data")
        if data is not None:
            assert data == {"$data": "d1"}

    blob = journal.to_dict()
    assert list(blob["data"]) == ["d1"]
    assert '"$data"' in json.dumps(blob["entries"])


def test_data_section_ids_are_deterministic():
    """Two journals of the same figure mint identical data ids —
    first-encounter order, like nids."""
    df = {"x": [1, 2], "y": [3, 4]}
    df2 = {"x": [0, 3], "y": [1, 1]}

    def build():
        c = pt.chart(df, aes(x="x", y="y"))
        c.add_line()
        c.add_scatter(df2, aes(x="x", y="y"), inherit_aes=False)
        return c

    j1, j2 = pt.to_journal(build()), pt.to_journal(build())
    assert j1.entries == j2.entries
    assert j1.data == j2.data
    assert list(j1.data) == ["d1", "d2"]


def test_facet_journal_stores_one_table():
    """A facet journals its full table once — panel subsets only appear
    in the expanded (lowered) form, one entry each."""
    df = {"t": [1, 2, 3], "v": [5, 6, 4], "grp": ["p", "p", "q"]}

    fg = pt.facet(df, by="grp")
    fg.add_line(aes(x="t", y="v"))

    journal = pt.to_journal(fg)
    assert list(journal.data) == ["d1"]
    assert journal.data["d1"] == df
