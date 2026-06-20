"""Histogram — binned counts of a 1-D distribution.

  c.hist(data=df, x="col")                      # long-form
  c.hist(data=df, x="col", fill="group")        # overlaid by group

Multi-group overlays share bin edges so the bars are comparable.

Aesthetics:
  fill=         constant color OR column name → grouped multi-series
  color=        stroke color (constant, default None = no stroke)
  palette=      maps group levels → colors when `fill=` is a column

Other styling kwargs:
  bins=10             number of bins
  density=False       True normalises so area under each set of bars is 1
  histtype='bar'      'bar', 'step' (outline-only), or 'stepfilled'
  orientation='v'     'h' for horizontal bars
  alpha=<themed>      bar fill opacity
  linewidth=<themed>  stroke width (used only when color is set)
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list, long_form_1d, resolve_aes, palette_color
from ..draw import TAB10, resolve_color
from .._spec import _D, _LEGSPEC
from ..draw import coord, path as draw_path, polygon as draw_polygon, rect as draw_rect


def _artist_hist(a, xs_, ys_, col, bins, warp=None):
    out = []
    opts = a["opts"]
    horizontal = opts.get("orientation") == "h"
    bin_scale, count_scale = (ys_, xs_) if horizontal else (xs_, ys_)
    base = count_scale(0)
    alpha = opts.get("alpha", _D["hist_alpha"])
    stroke = resolve_color(opts.get("color"))
    lw = opts.get("linewidth", _D["linewidth"]) if stroke else 1
    histtype = opts.get("histtype", "bar")
    if histtype not in ("bar", "step", "stepfilled"):
        raise ValueError(
            f"hist histtype={histtype!r} — must be 'bar', 'step', or 'stepfilled'."
        )

    if histtype == "bar":
        half_gap = _D["hist_gap"] / 2
        for b in bins:
            bp0 = bin_scale(b["x0"]); bp1 = bin_scale(b["x1"])
            bp_lo, bp_hi = min(bp0, bp1), max(bp0, bp1)
            bp_lo += half_gap; bp_hi -= half_gap
            bin_size = max(0, bp_hi - bp_lo)
            cp = count_scale(b["count"])
            count_lo, count_hi = min(base, cp), max(base, cp)
            count_size = count_hi - count_lo
            if horizontal:
                x, y, w, h = count_lo, bp_lo, count_size, bin_size
            else:
                x, y, w, h = bp_lo, count_lo, bin_size, count_size
            out.append(draw_rect(x, y, w, h, fill=col,
                                 stroke=stroke, stroke_width=lw,
                                 dash=opts.get("linestyle"), alpha=alpha,
                                 project=warp))
        return "".join(out)

    if not bins:
        return ""
    pts = [(bin_scale(bins[0]["x0"]), base)]
    for b in bins:
        cp = count_scale(b["count"])
        pts.append((bin_scale(b["x0"]), cp))
        pts.append((bin_scale(b["x1"]), cp))
    pts.append((bin_scale(bins[-1]["x1"]), base))
    if horizontal:
        pts = [(p, q) for q, p in pts]
    edge = stroke or col
    edge_w = lw if stroke else _D["linewidth"]
    fill = col if histtype == "stepfilled" else None
    if warp is None:
        d = "M" + " L".join(f"{coord(x)},{coord(y)}" for x, y in pts)
        out.append(draw_path(d + " Z", fill=fill,
                             stroke=edge, stroke_width=edge_w,
                             dash=opts.get("linestyle"), alpha=alpha))
    else:
        out.append(draw_polygon(pts, fill=fill, stroke=edge,
                                stroke_width=edge_w, alpha=alpha,
                                project=warp))
    return "".join(out)


def _hist_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "hist requires long-form input: "
            "c.hist(data=df, x='col')."
        )
    data_df = kw.pop("data", None)
    x_col = kw.pop("x", None)
    if data_df is None or x_col is None:
        raise TypeError(
            "hist requires data=, x= (fill= optional)."
        )
    fill = kw.pop("fill", None)
    fill_kind, fill_value = resolve_aes(data_df, fill)
    group_col = fill if fill_kind == "column" else None
    groups, vals = long_form_1d(data_df, x_col, group_col)
    if fill_kind == "literal" and fill_value is not None:
        kw["_fill_literal"] = fill_value
    return {"type": "hist", "groups": groups, "vals": vals, "opts": kw}


def _bin_xs(bin_groups):
    return [v for bins in bin_groups for b in bins for v in (b["x0"], b["x1"])]


def _bin_ys(bin_groups):
    return [b["count"] for bins in bin_groups for b in bins] + [0]


def _hist_data_attrs(a):
    vals = a["vals"]
    bin_groups = a.get("_bin_groups", [])
    n = sum(len(g) for g in vals)
    out = {"n": n, "bins": (len(bin_groups[0]) if bin_groups else
                            a["opts"].get("bins", 10))}
    flat_bins = [b for bins in bin_groups for b in bins]
    if flat_bins:
        out["x-min"] = min(b["x0"] for b in flat_bins)
        out["x-max"] = max(b["x1"] for b in flat_bins)
        out["count-max"] = max(b["count"] for b in flat_bins)
    return out


def _hist_horizontal(a): return a["opts"].get("orientation") == "h"


def _hist_xdomain(a):
    bin_groups = a.get("_bin_groups", [])
    return _bin_ys(bin_groups) if _hist_horizontal(a) else _bin_xs(bin_groups)


def _hist_ydomain(a):
    bin_groups = a.get("_bin_groups", [])
    return _bin_xs(bin_groups) if _hist_horizontal(a) else _bin_ys(bin_groups)


def _group_fill(groups, palette, j, fallback):
    if groups == [None]:
        return fallback
    return palette_color(palette, groups[j], j) or TAB10[j % 10]


def _hist_draw(a, ctx):
    palette = a["opts"].get("palette")
    bin_groups = a.get("_bin_groups", [])
    fill_literal = resolve_color(a["opts"].get("_fill_literal"))
    fill_fallback = fill_literal if fill_literal is not None else ctx.color
    out = []
    for j, bins in enumerate(bin_groups):
        col = _group_fill(a["groups"], palette, j, fill_fallback)
        out.append(_artist_hist(a, ctx.x_scale, ctx.y_scale, col, bins,
                                 warp=ctx.warp))
    return "".join(out)


def _hist_legend_entries(a):
    groups = a["groups"]
    opts = a["opts"]
    alpha = opts.get("alpha", _D["hist_alpha"])
    sw = _LEGSPEC["swatch_width"]
    if groups == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(_a, _ctx, x0, y_mid):
            return draw_rect(x0, y_mid - 5, sw, 10,
                             fill=_a["_color"], alpha=alpha)
        return [{"label": label, "color": a.get("_color"), "paint": paint}]
    palette = opts.get("palette")
    entries = []
    for j, g in enumerate(groups):
        col = _group_fill(groups, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return draw_rect(x0, y_mid - 5, sw, 10, fill=_col, alpha=alpha)
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="hist",
    record=_hist_record,
    xdomain=_hist_xdomain,
    ydomain=_hist_ydomain,
    draw=_hist_draw,
    legend_entries=_hist_legend_entries,
    data_attrs=_hist_data_attrs,
    force_zero_y=lambda a: not _hist_horizontal(a),
    force_zero_x=_hist_horizontal,
    coord_native=True,
))
