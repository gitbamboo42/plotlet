"""Data-shaping helpers for use inside a custom artist's `record` and `draw`.

These functions are the canonical home for the conversion / broadcasting /
binning / category-collection helpers used internally by the built-in
artists, exposed under public names for use when authoring your own
`ArtistSpec`.

Example:

    from plotlet import utils

    def my_record(args, kw):
        xs = utils.to_list(args[0])
        ys = utils.to_list(args[1])
        return {"type": "mything", "xs": xs, "ys": ys, "opts": kw}

The inverse-direction primitives (emit SVG strings) live in `plotlet.draw`.
"""
import math
import re

from .registry import get_artist
from .draw import TAB10, resolve_color


_UNIT_PX = {
    "px": 1.0,
    "in": 96.0,
    "cm": 96.0 / 2.54,
    "mm": 96.0 / 25.4,
    "pt": 96.0 / 72.0,
}
_DIM_RE = re.compile(r"^\s*([+-]?\d*\.?\d+)\s*([a-zA-Z]*)\s*$")


def _to_px(value):
    """Resolve a dim value to integer pixels.

    Accepts:
      - `int` / `float`: bare pixels.
      - `str`: a number with an optional unit suffix
        (`"4in"`, `"10cm"`, `"100mm"`, `"72pt"`, `"30px"` or `"30"`).
        Whitespace and case insensitive (`"5 IN"` works).
      - `None`: passthrough (constructors interpret as "use default").
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # Guard against `True`/`False` slipping through `int` — almost never
        # what the user meant for a dimension.
        raise TypeError(f"dim value cannot be bool; got {value!r}")
    if isinstance(value, (int, float)):
        return int(round(value))
    if not isinstance(value, str):
        raise TypeError(
            f"dim value must be int, float, or str; got {type(value).__name__}"
        )
    m = _DIM_RE.match(value)
    if not m:
        raise ValueError(
            f"could not parse dim value {value!r}; expected '<number>[unit]' "
            f"where unit is one of: {', '.join(sorted(_UNIT_PX))}"
        )
    num = float(m.group(1))
    unit = m.group(2).lower() or "px"
    if unit not in _UNIT_PX:
        raise ValueError(
            f"unknown unit {unit!r} in {value!r}; expected one of: "
            f"{', '.join(sorted(_UNIT_PX))}"
        )
    return int(round(num * _UNIT_PX[unit]))


def to_list(obj):
    """Convert numpy / pandas / arbitrary iterables to plain Python lists."""
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, (list, tuple)):
        return list(obj)
    return list(obj)


class DataFrameLite:
    """Canonical in-memory form for DataFrame-shaped inputs.

    Any pandas / polars / duck-typed DataFrame the user passes goes
    through `_normalize_data` at the recorder boundary and lands here.
    The class supports the two access patterns plotlet artists actually
    use: attributes (`.values`, `.columns`, `.index` — heatmap) and
    column indexing (`df[col]` returns a plain list — line, scatter,
    bar, etc.). Everything is plain Python so the journal never holds
    a library-specific object and JSON serialization is trivial."""
    __slots__ = ("values", "columns", "index", "_col_index")

    def __init__(self, values, columns, index):
        self.values = values
        self.columns = list(columns)
        self.index = list(index)
        self._col_index = {c: i for i, c in enumerate(self.columns)}

    def __getitem__(self, key):
        return [row[self._col_index[key]] for row in self.values]

    def __contains__(self, key):
        return key in self._col_index

    def __iter__(self):
        return iter(self.columns)

    def __len__(self):
        return len(self.values)


def _normalize_data(data):
    """Coerce DataFrame-shaped and numpy inputs to plain Python at the
    boundary. After this, no library-specific value ever enters the
    journal — the JSON layer only sees plain Python and DataFrameLite.

    Idempotent: already-normalized values pass through unchanged.

      - pandas / polars / duck-typed DataFrame  → DataFrameLite
      - numpy scalar                             → Python scalar
      - numpy array (any dim) / pandas Series    → nested list via .tolist()
      - dict                                     → recurse over values
      - list / tuple                             → recurse over elements
      - everything else                          → passthrough

    Column and index labels are coerced to `str` — uniform label type
    simplifies downstream code and keeps JSON round-trip deterministic.
    Pass strings if you rely on `df[42]`-style integer-column lookups;
    after normalization the column would be named `"42"`."""
    if data is None or isinstance(data, DataFrameLite):
        return data
    # DataFrame-shaped duck type. Excludes plain dicts (which have
    # `.values` as a method but no `.columns` / `.index`).
    if (hasattr(data, "values") and hasattr(data, "columns")
            and hasattr(data, "index")
            and not isinstance(data, dict)):
        return DataFrameLite(
            values=[list(row) for row in data.values],
            columns=[str(c) for c in data.columns],
            index=[str(i) for i in data.index],
        )
    # numpy scalar → Python scalar. `np.generic` covers int64/float64/etc.
    try:
        import numpy as np
    except ImportError:
        np = None
    if np is not None and isinstance(data, np.generic):
        return data.item()
    # numpy array / pandas Series / anything with .tolist()
    if hasattr(data, "tolist"):
        out = data.tolist()
        # Recurse: 2-D arrays produce list-of-lists; inner elements may
        # still be numpy scalars if they slipped through `tolist`.
        return _normalize_data(out) if isinstance(out, (list, dict)) else out
    if isinstance(data, dict):
        return {k: _normalize_data(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_normalize_data(v) for v in data]
    if isinstance(data, tuple):
        return tuple(_normalize_data(v) for v in data)
    return data


def to_list_2d(obj):
    """Convert a 2-D input (list-of-lists, numpy 2-D, DataFrame) to nested lists."""
    if hasattr(obj, "values") and not hasattr(obj, "tolist"):
        obj = obj.values
    if hasattr(obj, "tolist"):
        out = obj.tolist()
    else:
        out = [list(row) for row in obj]
    if not out:
        return out
    if not isinstance(out[0], list):
        raise ValueError("imshow data must be 2-D")
    return out


def broadcast(*vals):
    """Each input is scalar or list-like; broadcast to a common length.
    Length-1 lists broadcast like scalars; mismatched longer lengths raise."""
    arrs = []
    for v in vals:
        if hasattr(v, "__iter__") and not isinstance(v, str):
            arrs.append(to_list(v))
        else:
            arrs.append([v])
    n = max(len(a) for a in arrs)
    out = []
    for a in arrs:
        if len(a) == 1:
            out.append(list(a) * n)
        elif len(a) == n:
            out.append(list(a))
        else:
            raise ValueError(f"cannot broadcast length {len(a)} to {n}")
    return out


def histogram(data, bins, density=False):
    """Equal-width binning. Returns list of {'x0', 'x1', 'count'} dicts.
    With `density=True`, `count` is the probability density (count divided
    by `total × bin_width`) so the integral over bins equals 1."""
    data = [v for v in to_list(data)
            if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not data:
        return []
    lo, hi = min(data), max(data)
    if lo == hi:
        hi = lo + 1
    n = bins if isinstance(bins, int) else 10
    width = (hi - lo) / n
    counts = [0] * n
    for v in data:
        if v == hi:
            counts[-1] += 1
        else:
            i = int((v - lo) / width)
            if 0 <= i < n:
                counts[i] += 1
    if density:
        total = sum(counts)
        scale = 1.0 / (total * width) if total and width else 0.0
        counts = [c * scale for c in counts]
    return [{"x0": lo + i * width, "x1": lo + (i + 1) * width, "count": counts[i]}
            for i in range(n)]


def quantile(xs, q, *, _skipna=True):
    """Linear-interpolation quantile (Tukey / numpy default `linear`).
    NaN values are skipped by default. Returns NaN for empty input, the
    single value for length-1 input."""
    if _skipna:
        xs = _drop_nan(xs)
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return float("nan")
    if n == 1:
        return xs[0]
    pos = (n - 1) * q
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _data_has_column(data, name):
    """True iff `data` has a column named `name`. Works for DataFrames,
    dict-of-lists, and anything else supporting `in` containment."""
    if data is None:
        return False
    if hasattr(data, "columns"):
        return name in data.columns
    try:
        return name in data
    except TypeError:
        return False


def resolve_aes(data, value):
    """Classify an aes value (e.g. `fill=`, `color=`, `group=`) as either
    a literal or a column reference.

    Returns `("literal", value)` when `value` is None, a non-string, or a
    string that does not match a column of `data`. Returns
    `("column", values_list)` when `value` is a string and `data` has a
    column with that name — in which case the per-row column values are
    materialized via `to_list(...)`. With no `data=` bound, every value
    is literal."""
    if value is None or not isinstance(value, str):
        return ("literal", value)
    if _data_has_column(data, value):
        return ("column", to_list(data[value]))
    return ("literal", value)


def palette_color(palette, value, index):
    """Resolve a hue-category value to a color via `palette`. Returns
    `None` when `palette` is `None`/empty or doesn't cover `value`, in
    which case the caller falls through to its own cycle. Accepts a
    dict (category → color) or a sequence indexed by category-appearance
    order (wraps modulo length). Palette values pass through
    `resolve_color`, so the standard shortcuts (`"C0"`–`"C9"`, named
    colors, single-letter codes) work alongside hex / CSS strings."""
    if not palette:
        return None
    if isinstance(palette, dict):
        return resolve_color(palette.get(value))
    return resolve_color(palette[index % len(palette)])


def dodge_positions(cat_scale, cat, n_groups, j, *, band_frac=0.6, gap=0.1):
    """Compute the centered-dodge position and box size for sub-box `j`
    of `n_groups` within category `cat`.

    `cat_scale` is the scale of whichever axis holds the categories
    (x_scale in vertical mode, y_scale in horizontal). `band_frac` is
    the total dodge-group size as a fraction of the category band; `gap`
    is the fraction of each slot left as spacing between adjacent boxes
    (ignored when `n_groups == 1`). Returns `(center, box_size)` in pixel
    coordinates along the categorical axis."""
    band = getattr(cat_scale, "bandwidth", 1.0)
    slot_w = band * band_frac / n_groups
    box_w = slot_w * (1 - gap) if n_groups > 1 else slot_w
    center = cat_scale(cat) + (j - (n_groups - 1) / 2) * slot_w
    return center, box_w


def categorical_groups(data, x_col, y_col, group_col=None):
    """Bin a long-form table into per-(x, group) value lists.

    Returns `(cats, groups, vals)`:
      `cats`   — unique x values in appearance order.
      `groups` — unique group-column values in appearance order, or
                 `[None]` when `group_col is None`.
      `vals`   — nested list with `vals[i][j]` = y values where
                 `x == cats[i]` and (`group_col_value == groups[j]` or
                 grouping is absent).

    Used by categorical artists that accept long-form
    `(data=df, x=col, y=col, fill=col)` input."""
    if data is None:
        raise ValueError("categorical_groups: data= is required.")
    xs = to_list(data[x_col])
    ys = to_list(data[y_col])
    hs = to_list(data[group_col]) if group_col is not None else [None] * len(xs)
    cats, groups = [], []
    for v in xs:
        if v not in cats: cats.append(v)
    for v in hs:
        if v not in groups: groups.append(v)
    vals = [[[] for _ in groups] for _ in cats]
    cat_idx = {c: i for i, c in enumerate(cats)}
    group_idx = {g: j for j, g in enumerate(groups)}
    for x, y, h in zip(xs, ys, hs):
        vals[cat_idx[x]][group_idx[h]].append(y)
    return cats, groups, vals


def collect_categories(artists, axis):
    """Unique values an artist contributes on `axis`, in first-appearance order.

    Preserves the order the user gave (e.g. clustering order, time order)
    rather than alphabetizing it. To override, pass `xscale("category",
    order=[...])` explicitly."""
    seen = set()
    out = []
    for a in artists:
        spec = get_artist(a["type"])
        if spec is None: continue
        fn = spec.xdomain if axis == "x" else spec.ydomain
        vals = fn(a)
        if vals is None: continue
        for v in vals:
            if v is None: continue
            if v not in seen:
                seen.add(v); out.append(v)
    return out


def long_form_xy(data, x_col, y_col, group_col=None):
    """Long-form xy table -> (groups, xy). `xy[j]` is the `(xs, ys)`
    pair where the group-column value equals `groups[j]`. With
    `group_col=None`, returns `([None], [(xs, ys)])` so callers can
    handle both cases uniformly.

    Used by xy artists (scatter, line, regression, ...) that accept
    long-form `(data=df, x=col, y=col, color=col)` input."""
    if data is None:
        raise ValueError("long_form_xy: data= is required.")
    xs_all = to_list(data[x_col])
    ys_all = to_list(data[y_col])
    if group_col is None:
        return [None], [(xs_all, ys_all)]
    hs = to_list(data[group_col])
    groups = []
    for h in hs:
        if h not in groups: groups.append(h)
    xy = [([], []) for _ in groups]
    group_idx = {h: j for j, h in enumerate(groups)}
    for x, y, h in zip(xs_all, ys_all, hs):
        j = group_idx[h]
        xy[j][0].append(x)
        xy[j][1].append(y)
    return groups, xy


def long_form_1d(data, x_col, group_col=None):
    """Long-form 1-D table -> (groups, vals). `vals[j]` is the list of
    values where the group-column value equals `groups[j]`. With
    `group_col=None`, returns `([None], [values])`.

    Used by 1-D distribution artists (hist, density_1d, ecdf, ...) that
    accept long-form `(data=df, x=col, color=col)` input."""
    if data is None:
        raise ValueError("long_form_1d: data= is required.")
    xs_all = to_list(data[x_col])
    if group_col is None:
        return [None], [xs_all]
    hs = to_list(data[group_col])
    groups = []
    for h in hs:
        if h not in groups: groups.append(h)
    vals = [[] for _ in groups]
    group_idx = {h: j for j, h in enumerate(groups)}
    for x, h in zip(xs_all, hs):
        vals[group_idx[h]].append(x)
    return groups, vals


def _drop_nan(xs):
    return [x for x in xs if not (isinstance(x, float) and math.isnan(x))]


def silverman_bw(xs):
    """Silverman's rule-of-thumb bandwidth for a 1-D Gaussian KDE.
    NaN values are skipped (matches numpy's nan-aware convention)."""
    xs = _drop_nan(xs)
    n = len(xs)
    if n < 2:
        return 1.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / n
    sd = math.sqrt(var) or 1.0
    return 1.06 * sd * n ** (-1 / 5)


def kde_1d(samples, grid, bw):
    """Evaluate a 1-D Gaussian KDE at each point in `grid`. NaN samples
    are skipped.

    Returns density values (same length as grid) normalised to integrate to 1.
    """
    samples = _drop_nan(samples)
    if not samples:
        return [0.0] * len(grid)
    inv = 1.0 / (bw * math.sqrt(2 * math.pi) * len(samples))
    out = []
    for g in grid:
        s = sum(math.exp(-0.5 * ((g - x) / bw) ** 2) for x in samples)
        out.append(s * inv)
    return out


__all__ = ["to_list", "to_list_2d", "broadcast", "histogram", "quantile",
           "resolve_aes", "palette_color", "dodge_positions",
           "categorical_groups", "collect_categories",
           "long_form_xy", "long_form_1d",
           "silverman_bw", "kde_1d"]
