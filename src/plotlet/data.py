"""Bundled example datasets — `pt.load("penguins")` and friends.

Datasets ship as CSV files under `_datasets/` and are loaded into a
dict-of-lists (`{col: [values, ...]}`) — the same shape `pt.chart()`
accepts directly. Numeric columns are converted to float; missing
values become `float('nan')`. Categorical columns stay strings.

Available datasets:

  - "penguins" — Palmer Penguins (Gorman, Williams & Fraser 2014; CC0).
    344 rows × 8 columns: species, island, bill_length_mm, bill_depth_mm,
    flipper_length_mm, body_mass_g, sex, year.

Example:

    import plotlet as pt
    penguins = pt.load("penguins")
    c = pt.chart(penguins, x="bill_length_mm", y="bill_depth_mm", color="species")
    c.scatter()
"""
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


def load(name):
    """Load a bundled example dataset as a `dict[col, list]`.

    Pass directly to `pt.chart(...)`:

        df = pt.load("penguins")
        pt.chart(df, x="bill_length_mm", y="bill_depth_mm", color="species")

    See `pt.list_datasets()` for what's available.
    """
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
    return sorted(p.stem for p in _DATA_DIR.glob("*.csv"))
