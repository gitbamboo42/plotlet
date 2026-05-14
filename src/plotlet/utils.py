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


def histogram(data, bins):
    """Equal-width binning. Returns list of {'x0', 'x1', 'count'} dicts."""
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
    return [{"x0": lo + i * width, "x1": lo + (i + 1) * width, "count": counts[i]}
            for i in range(n)]


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


__all__ = ["to_list", "to_list_2d", "broadcast", "histogram", "collect_categories"]
