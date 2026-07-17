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
import bisect
import math
import numbers
import re

from scipy.stats import t as _t_dist

from .registry import get_artist
from .draw import TAB10, resolve_color
from .draw import palette as _named_palette


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


class _UnsetType:
    """Signature default for the rare kwarg where `None` is itself a
    meaningful user value (e.g. bar's `ci=None` = "no CI", distinct from
    unset = stat-dependent default). The repr keeps `help()` output
    readable."""
    def __repr__(self):
        return "UNSET"


UNSET = _UnsetType()


def pack_opts(**pairs):
    """Build an artist `opts` dict from explicit record-function
    parameters: only user-set entries (non-None) are kept, so downstream
    `opts.get(key, default)` reads still fall through to spec/theme
    defaults exactly as with the legacy leftover-kwargs bag."""
    return {k: v for k, v in pairs.items() if v is not None}


def to_list(obj):
    """Convert numpy / pandas / arbitrary iterables to plain Python lists."""
    if hasattr(obj, "tolist"):
        return obj.tolist()
    return list(obj)


def all_numeric(seq):
    """True iff `seq` is non-empty and every element is a real number
    (bool excluded). The axis-kind dispatch predicate: a numeric column
    puts its axis on a linear scale, anything else stays categorical.

    `numbers.Real` rather than `(int, float)` so numpy scalars (np.int64
    et al. register with the numbers ABCs but don't subclass int) don't
    silently flip an axis categorical. NaN counts as numeric — callers
    that can't render NaN positions must reject it explicitly.
    """
    saw = False
    for v in seq:
        if isinstance(v, bool) or not isinstance(v, numbers.Real):
            return False
        saw = True
    return saw


class DataFrameLite:
    """Canonical in-memory form for DataFrame-shaped inputs.

    Any pandas / polars / duck-typed DataFrame the user passes goes
    through `_normalize_data` at the recorder boundary and lands here.
    The class supports the access patterns plotlet artists actually
    use: column indexing (`df[col]` returns a plain list), `in`
    containment, and iteration over column names. Everything is plain
    Python so the journal never holds a library-specific object and
    JSON serialization is trivial."""
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

      - pandas / duck-typed DataFrame            → DataFrameLite
        (needs `.values` / `.columns` / `.index` — polars has no
        `.index`, so polars frames are not recognized here)
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
        # Iterating a 2-D ndarray row-by-row yields numpy scalars
        # (np.int64 is not an int, so it survives json_safe and breaks
        # json.dumps). `.tolist()` converts numeric dtypes wholesale;
        # the recursion catches numpy scalars that survive inside
        # object-dtype cells and rows from non-numpy duck types.
        raw = data.values
        rows = raw.tolist() if hasattr(raw, "tolist") else [list(r) for r in raw]
        return DataFrameLite(
            values=_normalize_data(rows),
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


def hist_bin_edges(data, *, bins=10, binwidth=None, binrange=None):
    """Resolve histogram bin edges from the hist kwargs vocabulary.

    `bins=` is an int count or an explicit edge sequence (returned as-is);
    `binwidth=` overrides the count with fixed-width bins anchored at the
    range start; `binrange=(lo, hi)` pins the binned span (values outside
    it are dropped by `hist_bin_counts`)."""
    if bins is not None and not isinstance(bins, int):
        return [float(e) for e in to_list(bins)]
    if binrange is not None:
        lo, hi = float(binrange[0]), float(binrange[1])
    else:
        lo, hi = min(data), max(data)
    if lo == hi:
        hi = lo + 1
    if binwidth is not None:
        n = max(1, math.ceil((hi - lo) / binwidth - 1e-9))
        return [lo + i * binwidth for i in range(n + 1)]
    n = bins if isinstance(bins, int) else 10
    width = (hi - lo) / n
    # Last edge pinned to `hi` exactly — `lo + n * width` can drift a ULP.
    return [lo + i * width for i in range(n)] + [hi]


def hist_bin_counts(data, edges, weights=None):
    """Count `data` into `edges` bins (right-inclusive last bin, values
    outside `[edges[0], edges[-1]]` dropped — the mpl `range=` convention).
    `weights=` sums per-value weights instead of counting; pairs whose
    value or weight is None/NaN are skipped."""
    def bad(v):
        return v is None or (isinstance(v, float) and math.isnan(v))
    counts = [0.0] * (len(edges) - 1)
    lo, hi = edges[0], edges[-1]
    for k, v in enumerate(data):
        w = 1 if weights is None else weights[k]
        if bad(v) or bad(w) or v < lo or v > hi:
            continue
        i = len(counts) - 1 if v == hi else bisect.bisect_right(edges, v) - 1
        counts[i] += w
    return counts


def hist_transform(counts, edges, *, density=False, cumulative=False):
    """Apply the hist `density=` / `cumulative=` transforms to raw counts.

    density: count / (total × bin_width) — bars integrate to 1.
    cumulative: running sum; combined with density the result is the
    empirical CDF (last bin = 1), matching matplotlib."""
    if cumulative:
        total = sum(counts)
        out, run = [], 0.0
        for c in counts:
            run += c
            out.append(run / total if density and total else run)
        return out
    if density:
        total = sum(counts)
        return [c / (total * (e1 - e0)) if total and e1 != e0 else 0.0
                for c, e0, e1 in zip(counts, edges, edges[1:])]
    return list(counts)


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
    palette name (`"Set2"`, see `plotlet.list_palettes()`), a dict
    (category → color), or a sequence indexed by category-appearance
    order (wraps modulo length). Palette values pass through
    `resolve_color`, so the standard shortcuts (`"C0"`–`"C9"`, named
    colors, single-letter codes) work alongside hex / CSS strings."""
    if not palette:
        return None
    if isinstance(palette, str):
        palette = _named_palette(palette)
    if isinstance(palette, dict):
        return resolve_color(palette.get(value))
    return resolve_color(palette[index % len(palette)])


def group_color(groups, palette, j, fallback):
    """Per-group color for artists with column-driven grouping: ungrouped
    (`groups == [None]`) → fallback (the artist's cycle/literal color);
    grouped → palette lookup with TAB10 wraparound. Also the rule the
    render half applies when stamping `_color` on fan-out group records
    (`groups` + `_j` in the record) — see `_render_inner`."""
    if groups == [None]:
        return fallback
    return palette_color(palette, groups[j], j) or TAB10[j % 10]


# Dodge defaults shared by bar, hist, and errorbar's dodged grouping —
# one definition, so slot geometry across the three can't drift and
# dodged errorbars keep landing on bar slot centers.
DODGE_WIDTH = 0.8
DODGE_GAP = 0.1


def dodge_slot(center, band, n_groups, j, *, width, gap):
    """Centered-dodge slot `j` of `n_groups` within a pixel band of size
    `band` around `center` → `(slot_center, box_size)`. The geometry core
    of `dodge_positions`, usable directly when the band is an explicit
    pixel interval (hist bins) rather than a category on a band scale.
    `width` is the total dodge-group size as a fraction of the band;
    `gap` the fraction of each slot left as spacing between adjacent
    boxes (ignored when `n_groups == 1`)."""
    slot = band * width / n_groups
    box = slot * (1 - gap) if n_groups > 1 else slot
    return center + (j - (n_groups - 1) / 2) * slot, box


def dodge_positions(cat_scale, cat, n_groups, j, *, band_frac=0.6, gap=0.1):
    """Compute the centered-dodge position and box size for sub-box `j`
    of `n_groups` within category `cat`.

    `cat_scale` is the scale of whichever axis holds the categories
    (x_scale in vertical mode, y_scale in horizontal). Returns
    `(center, box_size)` in pixel coordinates along the categorical
    axis. See `dodge_slot` for the band/width/gap geometry."""
    band = getattr(cat_scale, "bandwidth", 1.0)
    return dodge_slot(cat_scale(cat), band, n_groups, j,
                      width=band_frac, gap=gap)


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


def t_ci_mean(vals, level):
    """Student-t confidence interval on the mean. Returns `(lo, hi)`;
    degenerate input (n < 2) collapses to the point value."""
    n = len(vals)
    if n < 2:
        m = vals[0] if vals else float("nan")
        return m, m
    m = sum(vals) / n
    var = sum((x - m) ** 2 for x in vals) / (n - 1)
    se = math.sqrt(var / n)
    crit = _t_dist.ppf((1 + level) / 2, n - 1)
    return m - crit * se, m + crit * se


def bootstrap_ci(vals, estimator_fn, level, n_boot, rng):
    """Percentile bootstrap CI for an arbitrary estimator. `rng` is a
    seeded `random.Random` — determinism is the caller's job."""
    if not vals:
        return float("nan"), float("nan")
    n = len(vals)
    boots = [estimator_fn([vals[rng.randrange(n)] for _ in range(n)])
             for _ in range(n_boot)]
    boots.sort()
    alpha = (1 - level) / 2
    return (boots[max(0, int(alpha * n_boot))],
            boots[min(n_boot - 1, int((1 - alpha) * n_boot))])


def validate_ci(artist, ci):
    """Reject an unknown `ci=` with the shared message. Every artist that
    aggregates with a CI (bar stat=, line estimator=, pointplot) calls
    this at record entry, so the vocabulary can't drift per artist."""
    if ci not in (None, "t", "boot"):
        raise ValueError(f"{artist}: ci={ci!r} — expected 't', 'boot', or None.")


def ci_bounds(cells, est_fn, estimator, ci, level, n_boot, rng):
    """Confidence bounds per cell of replicate samples — the one
    estimator → (t | bootstrap) dispatch behind bar `stat=`, line
    `estimator=`, and pointplot. `ci="t"` with the mean gets the
    analytic t interval; any other (ci, estimator) pair bootstraps
    `est_fn`. Returns `(los, his)` aligned with `cells`; empty cells
    (and `ci=None`) yield `(nan, nan)` bounds — how a bound-less cell
    presents (0-height bar, missing point) is the caller's decision.
    `rng` advances only on bootstrapped non-empty cells, in cell order."""
    nan = float("nan")
    los, his = [], []
    for cell in cells:
        if ci is None or not cell:
            lo, hi = nan, nan
        elif ci == "t" and estimator == "mean":
            lo, hi = t_ci_mean(cell, level)
        else:
            lo, hi = bootstrap_ci(cell, est_fn, level, n_boot, rng)
        los.append(lo)
        his.append(hi)
    return los, his


__all__ = ["to_list", "to_list_2d", "broadcast", "quantile",
           "hist_bin_edges", "hist_bin_counts", "hist_transform",
           "resolve_aes", "palette_color", "group_color",
           "dodge_positions", "dodge_slot",
           "categorical_groups", "collect_categories",
           "long_form_xy", "long_form_1d",
           "silverman_bw", "kde_1d", "t_ci_mean", "bootstrap_ci",
           "validate_ci", "ci_bounds"]
