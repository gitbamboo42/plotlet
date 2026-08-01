"""Bundled example datasets — `pt.load_dataset("penguins")` and friends.

Tabular datasets ship as CSV files under `_datasets/` and are loaded
into a dict-of-lists (`{col: [values, ...]}`) — the same shape
`pt.chart()` accepts directly. Numeric columns are converted to float;
missing values become `float('nan')`. Categorical columns stay strings.
Image datasets ship as compressed `.npz` and load as a uint8 numpy
array ready for `c.add_image_rgba(...)`.

Available datasets:

  - "penguins" — Palmer Penguins (Gorman, Williams & Fraser 2014; CC0).
    344 rows × 8 columns: species, island, bill_length_mm, bill_depth_mm,
    flipper_length_mm, body_mass_g, sex, year.
  - "flights" — monthly airline passenger totals 1949–1960 (Box &
    Jenkins 1976). 144 rows × 3 columns: year, month, passengers.
    Pivots naturally into a month × year heatmap.
  - "anscombe" — Anscombe's quartet (Anscombe 1973). 44 rows × 3
    columns: dataset, x, y. Four x/y sets with near-identical summary
    statistics — regression and facet demos.
  - "tips" — restaurant tipping records (Bryant & Smith 1995). 244 rows
    × 7 columns: total_bill, tip, sex, smoker, day, time, size.
    Categorical workflows: bar, box, violin, swarm.
  - "earth" — "The Blue Marble", Earth from Apollo 17 (NASA, Dec 7
    1972; public domain, via Wikimedia Commons). (256, 256, 3) uint8
    RGB array — image_rgba demos.

Example:

    import plotlet as pt
    penguins = pt.load_dataset("penguins")
    c = pt.chart(penguins, aes(x="bill_length_mm", y="bill_depth_mm", color="species"))
    c.add_scatter()
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "_datasets"

# Per-dataset column type hints. Anything not listed defaults to string.
_TYPES = {
    "penguins": {
        "bill_length_mm":    float,
        "bill_depth_mm":     float,
        "flipper_length_mm": float,
        "body_mass_g":       float,
        "year":              int,
    },
    "flights": {
        "year":       int,
        "passengers": int,
    },
    "anscombe": {
        "x": float,
        "y": float,
    },
    "tips": {
        "total_bill": float,
        "tip":        float,
        "size":       int,
    },
}


def _coerce(value, kind):
    """Convert a CSV string into `kind`, mapping empty / "NA" to nan."""
    if value == "" or value == "NA":
        return math.nan
    if kind is float:
        return float(value)
    if kind is int:
        # Some columns (e.g. body_mass_g) are conceptually int but become
        # float when NaNs are present — coerce to int only when clean.
        return int(value)
    return value


def load_dataset(name):
    """Load a bundled example dataset — a `dict[col, list]` for tabular
    datasets, a uint8 numpy array for image datasets.

    Pass directly to `pt.chart(...)`:

        df = pt.load_dataset("penguins")
        pt.chart(df, aes(x="bill_length_mm", y="bill_depth_mm", color="species"))

    See `pt.list_datasets()` for what's available.
    """
    npz = _DATA_DIR / f"{name}.npz"
    if npz.exists():
        import numpy as np
        with np.load(npz) as z:
            return z["image"]
    path = _DATA_DIR / f"{name}.csv"
    if not path.exists():
        avail = list_datasets()
        raise ValueError(
            f"Unknown dataset {name!r}. Available: {avail}."
        )
    types = _TYPES.get(name, {})
    with path.open(newline="") as f:
        reader = csv.reader(f)
        cols = next(reader)
        out = {c: [] for c in cols}
        for row in reader:
            for c, v in zip(cols, row):
                out[c].append(_coerce(v, types.get(c, str)))
    return out


def list_datasets():
    """Return the names of bundled datasets."""
    if not _DATA_DIR.is_dir():
        return []
    return sorted(p.stem for p in _DATA_DIR.iterdir()
                  if p.suffix in (".csv", ".npz"))
