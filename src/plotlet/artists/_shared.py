"""Helpers shared across 2+ per-artist files.

Each built-in artist registers one of the `*_legend_entries` functions so
the legend dispatch in `_render` can stay generic — no type-string matching.
Paint logic is a nested closure; there are no shared swatch helpers.
"""
from .._spec import _LEGSPEC
from ..draw import marker, segment, rect
from ..draw.colors import TAB10
from ..utils import to_list, resolve_aes, palette_color


# Used by long-form expansion for `linetype=` and `alpha=` column splits.
LINETYPE_CYCLE = (None, "--", ":", "-.")
DEFAULT_ALPHA_RANGE = (0.3, 1.0)


def _alpha_for_level(idx, n_levels, alphas):
    """Map a discrete level index to an alpha within `alphas` (a `(lo, hi)`
    tuple). One level → high end; otherwise linearly spaced."""
    lo, hi = alphas
    if n_levels <= 1:
        return hi
    return lo + (hi - lo) * idx / (n_levels - 1)


def expand_xy_long_form(kind, data, x_col, y_col,
                        color, group, linetype, alpha,
                        palette, alphas, base_opts):
    """Long-form xy table → list of artist record dicts split by
    `(color, group, linetype, alpha)` tuples. One record per unique tuple,
    each carrying its own `color`/`linestyle`/`alpha`/`label`. Shared by
    artists that draw one series per record (line, scatter).

    Returns a list of dicts shaped `{"type": kind, "xs": [...], "ys": [...],
    "opts": {...}}`. Single-record fast path when all four aesthetics are
    literal (or absent). `base_opts` is the leftover kwargs after popping
    the long-form aesthetic keys."""
    color_kind, color_value = resolve_aes(data, color)
    group_kind, group_value = resolve_aes(data, group)
    ltype_kind, ltype_value = resolve_aes(data, linetype)
    alpha_kind, alpha_value = resolve_aes(data, alpha)
    xs_all = to_list(data[x_col])
    ys_all = to_list(data[y_col])
    n = len(xs_all)

    if (color_kind == "literal" and group_kind == "literal"
            and ltype_kind == "literal" and alpha_kind == "literal"):
        opts = dict(base_opts)
        if color_value is not None: opts["color"] = color_value
        if ltype_value is not None: opts["linestyle"] = ltype_value
        if alpha_value is not None: opts["alpha"] = alpha_value
        return [{"type": kind, "xs": xs_all, "ys": ys_all, "opts": opts}]

    color_vec = color_value if color_kind == "column" else [None] * n
    group_vec = group_value if group_kind == "column" else [None] * n
    ltype_vec = ltype_value if ltype_kind == "column" else [None] * n
    alpha_vec = alpha_value if alpha_kind == "column" else [None] * n
    color_levels = list(dict.fromkeys(color_vec))
    ltype_levels = list(dict.fromkeys(ltype_vec))
    alpha_levels = list(dict.fromkeys(alpha_vec))
    quads = list(dict.fromkeys(zip(color_vec, group_vec, ltype_vec, alpha_vec)))

    base_opts.pop("label", None)  # column-driven grouping overrides any user label
    records = []
    labeled: set = set()
    for ck, gk, lk, ak in quads:
        idxs = [j for j in range(n)
                if color_vec[j] == ck and group_vec[j] == gk
                and ltype_vec[j] == lk and alpha_vec[j] == ak]
        xs_g = [xs_all[j] for j in idxs]
        ys_g = [ys_all[j] for j in idxs]
        opts = dict(base_opts)
        if color_kind == "column":
            idx = color_levels.index(ck)
            opts["color"] = palette_color(palette, ck, idx) or TAB10[idx % 10]
            if ck not in labeled:
                opts["label"] = str(ck)
                labeled.add(ck)
        elif color_value is not None:
            opts["color"] = color_value
        if ltype_kind == "column":
            ls = LINETYPE_CYCLE[ltype_levels.index(lk) % len(LINETYPE_CYCLE)]
            if ls is not None:
                opts["linestyle"] = ls
        elif ltype_value is not None:
            opts["linestyle"] = ltype_value
        if alpha_kind == "column":
            opts["alpha"] = _alpha_for_level(alpha_levels.index(ak),
                                              len(alpha_levels), alphas)
        elif alpha_value is not None:
            opts["alpha"] = alpha_value
        records.append({"type": kind, "xs": xs_g, "ys": ys_g, "opts": opts})
    return records


_CURVE_VALUES = ("linear", "step-before", "step-after", "step-mid")


def _step_coords(xs, ys, mode):
    """Interleave (xs, ys) into step-shaped coordinates.

    `mode` is one of 'before' | 'after' | 'mid'. NaN values pass through
    unchanged — the path-building stage breaks the stroke at them, so
    gaps don't get bridged by a phantom step."""
    n = len(xs)
    if n < 2:
        return list(xs), list(ys)
    out_x = [xs[0]]
    out_y = [ys[0]]
    for i in range(1, n):
        x0, x1 = xs[i - 1], xs[i]
        y0, y1 = ys[i - 1], ys[i]
        if mode == "before":
            out_x.append(x0); out_y.append(y1)
        elif mode == "after":
            out_x.append(x1); out_y.append(y0)
        else:  # mid
            mid = (x0 + x1) / 2
            out_x.append(mid); out_y.append(y0)
            out_x.append(mid); out_y.append(y1)
        out_x.append(x1); out_y.append(y1)
    return out_x, out_y


def _xy_minmax(xs, ys):
    """Min/max for an x/y series, ignoring NaN. Returns dict ready to merge
    into a data_attrs result."""
    fxs = [x for x in xs if isinstance(x, (int, float)) and x == x]
    fys = [y for y in ys if isinstance(y, (int, float)) and y == y]
    out = {}
    if fxs:
        out["x-min"] = min(fxs)
        out["x-max"] = max(fxs)
    if fys:
        out["y-min"] = min(fys)
        out["y-max"] = max(fys)
    return out


def _line_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        out = segment(x0, y_mid, x0 + sw, y_mid,
                      color=a["_color"],
                      width=a["opts"].get("linewidth", ctx.defaults["linewidth"]),
                      dash=a["opts"].get("linestyle"))
        if a["opts"].get("marker"):
            out += marker(a["opts"]["marker"], x0 + sw / 2, y_mid,
                          a["opts"].get("markersize", ctx.defaults["markersize"]),
                          a["_color"], 1)
        return out
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


def _refline_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        return segment(x0, y_mid, x0 + sw, y_mid,
                       color=a["_color"],
                       width=a["opts"].get("linewidth", ctx.defaults["refline_width"]),
                       dash=a["opts"].get("linestyle"))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


def _bar_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        return rect(x0, y_mid - 5, sw, 10, fill=a["_color"],
                    alpha=a["opts"].get("alpha", 1))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


def _refspan_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        return rect(x0, y_mid - 5, sw, 10, fill=a["_color"],
                    alpha=a["opts"].get("alpha", ctx.defaults["refspan_alpha"]))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]
