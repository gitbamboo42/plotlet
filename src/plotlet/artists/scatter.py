"""Scatter — single-series xy.

  c.scatter(xs, ys)                                       # wide-form
  c.scatter(data=df, x="col_x", y="col_y")                # long-form
  c.scatter(data=df, x="col_x", y="col_y", color="g")     # one color per level
  c.scatter(data=df, ..., color="g", group="subject")     # invisible finer split
  c.scatter(data=df, ..., alpha="cohort",                 # opacity per level
            alphas=(0.3, 1.0))
  c.scatter(data=df, ..., size="mass", sizes=(10, 200))   # per-point area
  c.scatter(data=df, ..., style="group")                  # per-level marker glyph

Column-driven splitting (any of `color`/`group`/`alpha`) is handled at
the Chart layer — the artist itself always sees one series per record.
`size`/`style` are computed per-point and stay inside a single record.

The per-point `c=` (numeric → colormap) is wide-form-only — it conflicts
with column-driven `color=`.
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list, resolve_aes, palette_color
from ..draw import marker
from ..draw import TAB10
from ..draw import colormap_lut, ContinuousNorm
from .._spec import _D, _LEGSPEC
from ._shared import (_xy_minmax, expand_xy_long_form,
                       DEFAULT_ALPHA_RANGE, _alpha_for_level)


def _artist_scatter(a, xs_, ys_, col, xs, ys):
    opts = a["opts"]
    raw_s = opts.get("s", _D["scatter_s"])
    raw_mk = opts.get("marker", "o")
    alpha = opts.get("alpha", _D["scatter_alpha"])
    edgecolor = opts.get("edgecolor")
    linewidth = opts.get("linewidth")
    c_vals = opts.get("c")
    n = len(xs)
    sizes   = list(raw_s)  if isinstance(raw_s,  (list, tuple)) else [raw_s]  * n
    markers = list(raw_mk) if isinstance(raw_mk, (list, tuple)) else [raw_mk] * n

    if c_vals is not None:
        cmap_name = opts.get("cmap", _D["default_cmap"])
        lut = colormap_lut(cmap_name)
        numeric = [v for v in c_vals if isinstance(v, (int, float)) and v == v]
        vmin = opts.get("vmin")
        vmax = opts.get("vmax")
        if vmin is None: vmin = min(numeric) if numeric else 0.0
        if vmax is None: vmax = max(numeric) if numeric else 1.0
        normalizer = ContinuousNorm(vmin, vmax, kind=opts.get("norm", "linear"))
        point_colors = []
        for v in c_vals:
            if not (isinstance(v, (int, float)) and v == v):
                point_colors.append("rgb(0,0,0)")
            else:
                idx = int(normalizer.to_unit(v) * 255 + 0.5) * 3
                point_colors.append(f"rgb({lut[idx]},{lut[idx+1]},{lut[idx+2]})")
    else:
        point_colors = [col] * n

    out = []
    for i, (x, y) in enumerate(zip(xs, ys)):
        px, py = xs_(x), ys_(y)
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        sz = math.sqrt(sizes[i]) / 2
        out.append(marker(markers[i], px, py, sz, point_colors[i], alpha,
                          edgecolor=edgecolor, edgewidth=linewidth))
    return "".join(out)


_STYLE_CYCLE = ("o", "s", "^", "v", "x", "+")


def _compute_size_array(values, sizes):
    vals = to_list(values)
    nums = [v for v in vals if isinstance(v, (int, float)) and v == v]
    if not nums:
        return [sizes[0]] * len(vals)
    lo, hi = min(nums), max(nums)
    span = hi - lo
    s_lo, s_hi = float(sizes[0]), float(sizes[1])
    if span == 0:
        mid = (s_lo + s_hi) / 2
        return [mid if isinstance(v, (int, float)) and v == v else s_lo for v in vals]
    return [s_lo + (v - lo) / span * (s_hi - s_lo)
            if isinstance(v, (int, float)) and v == v else s_lo for v in vals]


def _compute_style_array(values):
    vals = to_list(values)
    seen: list = []
    for v in vals:
        if v not in seen:
            seen.append(v)
    mapping = {v: _STYLE_CYCLE[i % len(_STYLE_CYCLE)] for i, v in enumerate(seen)}
    return [mapping[v] for v in vals]


def _expand_with_aesthetics(data, x_col, y_col, color, group, alpha,
                             palette, size, style, sizes, alphas, base_opts):
    """Long-form scatter with `size=`/`style=` per-point arrays. Splits by
    `(color, group, alpha)` tuples; size/marker arrays are sliced per
    sub-record. Equivalent to `expand_xy_long_form` but carries the extra
    per-point payload that line/fill_between don't have."""
    xs_all = to_list(data[x_col])
    ys_all = to_list(data[y_col])
    n = len(xs_all)
    s_arr  = _compute_size_array(data[size], sizes) if size is not None else None
    mk_arr = _compute_style_array(data[style])      if style is not None else None

    def slice_for(idxs):
        out = dict(base_opts)
        if s_arr  is not None: out["s"]      = [s_arr[i]  for i in idxs]
        if mk_arr is not None: out["marker"] = [mk_arr[i] for i in idxs]
        return out

    color_kind, color_value = resolve_aes(data, color)
    group_kind, group_value = resolve_aes(data, group)
    alpha_kind, alpha_value = resolve_aes(data, alpha)

    if (color_kind == "literal" and group_kind == "literal"
            and alpha_kind == "literal"):
        opts = slice_for(range(n))
        if color_value is not None: opts["color"] = color_value
        if alpha_value is not None: opts["alpha"] = alpha_value
        return [{"type": "scatter", "xs": xs_all, "ys": ys_all, "opts": opts}]

    color_vec = color_value if color_kind == "column" else [None] * n
    group_vec = group_value if group_kind == "column" else [None] * n
    alpha_vec = alpha_value if alpha_kind == "column" else [None] * n
    color_levels = list(dict.fromkeys(color_vec))
    alpha_levels = list(dict.fromkeys(alpha_vec))
    triples = list(dict.fromkeys(zip(color_vec, group_vec, alpha_vec)))

    base_opts.pop("label", None)
    records = []
    labeled: set = set()
    for ck, gk, ak in triples:
        idxs = [j for j in range(n)
                if color_vec[j] == ck and group_vec[j] == gk
                and alpha_vec[j] == ak]
        xs_g = [xs_all[j] for j in idxs]
        ys_g = [ys_all[j] for j in idxs]
        opts = slice_for(idxs)
        opts.pop("label", None)
        if color_kind == "column":
            idx = color_levels.index(ck)
            opts["color"] = palette_color(palette, ck, idx) or TAB10[idx % 10]
            if ck not in labeled:
                opts["label"] = str(ck)
                labeled.add(ck)
        elif color_value is not None:
            opts["color"] = color_value
        if alpha_kind == "column":
            opts["alpha"] = _alpha_for_level(alpha_levels.index(ak),
                                              len(alpha_levels), alphas)
        elif alpha_value is not None:
            opts["alpha"] = alpha_value
        records.append({"type": "scatter", "xs": xs_g, "ys": ys_g, "opts": opts})
    return records


def _scatter_record(args, kw):
    kw = dict(kw)
    if "data" in kw or "x" in kw or "y" in kw:
        data  = kw.pop("data", None)
        x_col = kw.pop("x", None)
        y_col = kw.pop("y", None)
        if data is None or x_col is None or y_col is None:
            raise TypeError(
                "scatter long-form requires data=, x=, y= "
                "(color/group/alpha/c/size/style optional)."
            )
        color   = kw.pop("color", None)
        group   = kw.pop("group", None)
        alpha   = kw.pop("alpha", None)
        palette = kw.pop("palette", None)
        c       = kw.pop("c", None)
        size    = kw.pop("size", None)
        style   = kw.pop("style", None)
        sizes   = kw.pop("sizes", (20, 200))
        alphas  = kw.pop("alphas", DEFAULT_ALPHA_RANGE)
        # scatter has no line to dash; ignore inherited linetype/fill.
        kw.pop("linetype", None)
        kw.pop("fill", None)

        color_kind, _ = resolve_aes(data, color)
        if c is not None and color_kind == "column":
            raise ValueError(
                "scatter accepts either color=<col> (categorical) or "
                "c= (numeric), not both — they're alternative color sources."
            )

        if c is not None:
            # Numeric color via cmap. `c=` is per-point — no splitting; the
            # categorical color= and alpha= (if any) are dropped, matching
            # the previous Chart.scatter behavior. cmap/vmin/vmax/norm
            # flow through unchanged in kw.
            if isinstance(c, str):
                c = to_list(data[c])
            else:
                c = to_list(c)
            kw["c"] = c
            return {"type": "scatter",
                    "xs": to_list(data[x_col]),
                    "ys": to_list(data[y_col]),
                    "opts": kw}

        if size is not None or style is not None:
            return _expand_with_aesthetics(data, x_col, y_col, color, group, alpha,
                                            palette, size, style, sizes, alphas, kw)

        # Default long-form: split by (color, group, alpha). scatter has no
        # linetype splits (no line to dash).
        return expand_xy_long_form("scatter", data, x_col, y_col,
                                    color, group, None, alpha,
                                    palette, alphas, kw)
    # Wide-form. Strip inherited-but-inapplicable aes that __getattr__
    # may have injected (palette only matters for column-driven splits;
    # fill/group/linetype don't apply to a single-series scatter).
    kw.pop("fill", None)
    kw.pop("group", None)
    kw.pop("linetype", None)
    kw.pop("palette", None)
    return {"type": "scatter",
            "xs": to_list(args[0]), "ys": to_list(args[1]),
            "opts": kw}


def _scatter_xdomain(a): return a["xs"]
def _scatter_ydomain(a): return a["ys"]


def _scatter_data_attrs(a):
    xs, ys = a["xs"], a["ys"]
    out = {"n": len(xs)}
    out.update(_xy_minmax(xs, ys))
    out["marker"] = a["opts"].get("marker", "o")
    return out


def _scatter_draw(a, ctx):
    return _artist_scatter(a, ctx.x_scale, ctx.y_scale, ctx.color,
                           a["xs"], a["ys"])


def _scatter_legend_entries(a):
    opts = a["opts"]
    label = opts.get("label")
    if not label:
        return []
    sw = _LEGSPEC["swatch_width"]
    def paint(_a, _ctx, x0, y_mid):
        raw_s = opts.get("s", _ctx.defaults["scatter_s"])
        raw_mk = opts.get("marker", "o")
        s_val = (sorted(raw_s)[len(raw_s) // 2]
                 if isinstance(raw_s, (list, tuple)) and raw_s
                 else (raw_s if not isinstance(raw_s, (list, tuple))
                       else _ctx.defaults["scatter_s"]))
        mk_val = (raw_mk[0]
                  if isinstance(raw_mk, (list, tuple)) and raw_mk
                  else (raw_mk if not isinstance(raw_mk, (list, tuple)) else "o"))
        s_size = math.sqrt(s_val) / 2
        return marker(mk_val, x0 + sw / 2, y_mid, s_size, _a["_color"],
                      opts.get("alpha", _ctx.defaults["scatter_alpha"]))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


add_artist(ArtistSpec(
    name="scatter",
    record=_scatter_record,
    xdomain=_scatter_xdomain,
    ydomain=_scatter_ydomain,
    draw=_scatter_draw,
    legend_entries=_scatter_legend_entries,
    data_attrs=_scatter_data_attrs,
))
