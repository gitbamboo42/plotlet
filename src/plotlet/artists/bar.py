"""Bar contributes its categories on x; the descriptor's auto-categorical
detection picks them up the same way it would for any string-valued x."""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._spec import _D
from ..draw import rect as draw_rect
from ._shared import _bar_legend_entries


def _artist_bar(a, xs_, ys_, col):
    out = []
    opts = a["opts"]
    horizontal = opts.get("orientation") == "h"
    cat_scale, val_scale = (ys_, xs_) if horizontal else (xs_, ys_)
    band = cat_scale.bandwidth
    base = val_scale(opts.get("bottom", 0))
    alpha = opts.get("alpha", _D["bar_alpha"])
    edgecolor = opts.get("edgecolor")
    lw = opts.get("linewidth", _D["linewidth"]) if edgecolor else 1
    # padding=0 produces contiguous bands (heatmap track look). Adjacent
    # rects anti-alias their shared edge into a hairline gap;
    # shape-rendering="crispEdges" pixel-aligns the borders so the cells
    # really butt up. Skip it for normal bars where the visible inner
    # padding makes anti-aliased edges look smoother.
    sr = "crispEdges" if getattr(cat_scale, "padding", 0.2) == 0 else None
    for c, v in zip(a["cats"], a["vals"]):
        cp = cat_scale(c) - band / 2  # left edge (vert) or top edge (horiz)
        vp = val_scale(v)
        if horizontal:
            x, y, w, h = min(base, vp), cp, abs(vp - base), band
        else:
            x, y, w, h = cp, min(base, vp), band, abs(vp - base)
        out.append(draw_rect(x, y, w, h,
                             fill=col, stroke=edgecolor, stroke_width=lw,
                             dash=opts.get("linestyle"),
                             alpha=alpha, shape_rendering=sr))
    return "".join(out)


def _bar_data_attrs(a):
    fvals = [v for v in a["vals"] if isinstance(v, (int, float)) and v == v]
    out = {"n": len(a["cats"])}
    if fvals:
        out["y-min"] = min(fvals)
        out["y-max"] = max(fvals)
    return out


def _bar_horizontal(a): return a["opts"].get("orientation") == "h"
def _bar_vals_domain(a):
    return list(a["vals"]) + [0, a["opts"].get("bottom", 0)]
def _bar_xdomain(a): return _bar_vals_domain(a) if _bar_horizontal(a) else a["cats"]
def _bar_ydomain(a): return a["cats"] if _bar_horizontal(a) else _bar_vals_domain(a)


add_artist(ArtistSpec(
    name="bar",
    record=lambda args, kw: {"type": "bar", "cats": to_list(args[0]),
                              "vals": to_list(args[1]), "opts": kw},
    xdomain=_bar_xdomain,
    ydomain=_bar_ydomain,
    draw=lambda a, ctx: _artist_bar(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_bar_legend_entries,
    data_attrs=_bar_data_attrs,
    force_zero_y=lambda a: not _bar_horizontal(a),
    force_zero_x=_bar_horizontal,
))
