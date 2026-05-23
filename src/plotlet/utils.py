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

from .registry import get_artist
from .draw.colors import TAB10


def to_list(obj):
    """Convert numpy / pandas / arbitrary iterables to plain Python lists."""
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, (list, tuple)):
        return list(obj)
    return list(obj)


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
    by `total × bin_width`) so the integral over bins equals 1 — matches
    matplotlib `hist(density=True)` / numpy `histogram(density=True)`."""
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


def palette_color(palette, value, index):
    """Resolve a hue-category value to a color via `palette`. Returns
    `None` when `palette` is `None`/empty or doesn't cover `value`, in
    which case the caller falls through to its own cycle. Accepts a
    dict (category → color) or a sequence indexed by category-appearance
    order (wraps modulo length)."""
    if not palette:
        return None
    if isinstance(palette, dict):
        return palette.get(value)
    return palette[index % len(palette)]


def hue_color(hues, palette, j, fallback):
    """Pick a color for hue index `j` in a dodged categorical artist.

    With no hue (`hues == [None]`) returns `fallback` — the artist's
    chart-level cycle color. With hue, resolves via `palette_color` and
    falls through to `TAB10[j % 10]` so categories beyond the palette
    still get a deterministic color."""
    if hues == [None]:
        return fallback
    return palette_color(palette, hues[j], j) or TAB10[j % 10]


def dodge_positions(cat_scale, cat, n_hues, j, *, band_frac=0.6, gap=0.1):
    """Compute the centered-dodge position and box size for sub-box `j`
    of `n_hues` within category `cat`.

    `cat_scale` is the scale of whichever axis holds the categories
    (x_scale in vertical mode, y_scale in horizontal). `band_frac` is
    the total dodge-group size as a fraction of the category band; `gap`
    is the fraction of each slot left as spacing between adjacent boxes
    (ignored when `n_hues == 1`). Returns `(center, box_size)` in pixel
    coordinates along the categorical axis."""
    band = getattr(cat_scale, "bandwidth", 1.0)
    slot_w = band * band_frac / n_hues
    box_w = slot_w * (1 - gap) if n_hues > 1 else slot_w
    center = cat_scale(cat) + (j - (n_hues - 1) / 2) * slot_w
    return center, box_w


def categorical_groups(data, x_col, y_col, hue_col=None):
    """Bin a long-form table into per-(x, hue) value lists.

    Returns `(cats, hues, groups)`:
      `cats`   — unique x values in appearance order.
      `hues`   — unique hue values in appearance order, or `[None]` when
                 `hue_col is None`.
      `groups` — nested list with `groups[i][j]` = y values where
                 `x == cats[i]` and (`hue == hues[j]` or hue is absent).

    Used by recipe artists that accept seaborn-style
    `(data=df, x=col, y=col, hue=col)` input."""
    if data is None:
        raise ValueError("categorical_groups: data= is required.")
    xs = to_list(data[x_col])
    ys = to_list(data[y_col])
    hs = to_list(data[hue_col]) if hue_col is not None else [None] * len(xs)
    cats, hues = [], []
    for v in xs:
        if v not in cats: cats.append(v)
    for v in hs:
        if v not in hues: hues.append(v)
    groups = [[[] for _ in hues] for _ in cats]
    cat_idx = {c: i for i, c in enumerate(cats)}
    hue_idx = {h: j for j, h in enumerate(hues)}
    for x, y, h in zip(xs, ys, hs):
        groups[cat_idx[x]][hue_idx[h]].append(y)
    return cats, hues, groups


def collect_categories(artists, axis):
    """Unique values an artist contributes on `axis`, alphabetically sorted."""
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
    return sorted(out, key=str)


def long_form_xy(data, x_col, y_col, hue_col=None):
    """Long-form xy table -> (hues, groups). `groups[j]` is the `(xs, ys)`
    pair where `hue == hues[j]`. With `hue_col=None`, returns
    `([None], [(xs, ys)])` so callers can handle both cases uniformly.

    Used by xy artists (scatter, line, regression, ...) that accept
    seaborn-style `(data=df, x=col, y=col, hue=col)` input."""
    if data is None:
        raise ValueError("long_form_xy: data= is required.")
    xs_all = to_list(data[x_col])
    ys_all = to_list(data[y_col])
    if hue_col is None:
        return [None], [(xs_all, ys_all)]
    hs = to_list(data[hue_col])
    hues = []
    for h in hs:
        if h not in hues: hues.append(h)
    groups = [([], []) for _ in hues]
    hue_idx = {h: j for j, h in enumerate(hues)}
    for x, y, h in zip(xs_all, ys_all, hs):
        j = hue_idx[h]
        groups[j][0].append(x)
        groups[j][1].append(y)
    return hues, groups


def long_form_1d(data, x_col, hue_col=None):
    """Long-form 1-D table -> (hues, groups). `groups[j]` is the list of
    values where `hue == hues[j]`. With `hue_col=None`, returns
    `([None], [values])`.

    Used by 1-D distribution artists (hist, density_1d, ecdf, ...) that
    accept seaborn-style `(data=df, x=col, hue=col)` input."""
    if data is None:
        raise ValueError("long_form_1d: data= is required.")
    xs_all = to_list(data[x_col])
    if hue_col is None:
        return [None], [xs_all]
    hs = to_list(data[hue_col])
    hues = []
    for h in hs:
        if h not in hues: hues.append(h)
    groups = [[] for _ in hues]
    hue_idx = {h: j for j, h in enumerate(hues)}
    for x, h in zip(xs_all, hs):
        groups[hue_idx[h]].append(x)
    return hues, groups


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
           "palette_color", "hue_color", "dodge_positions",
           "categorical_groups", "collect_categories",
           "long_form_xy", "long_form_1d",
           "silverman_bw", "kde_1d"]
