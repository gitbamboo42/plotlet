from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._spec import _D
from ..draw import rect as draw_rect, path as draw_path
from ._shared import _bar_legend_entries


def _artist_hist(a, xs_, ys_, col):
    out = []
    opts = a["opts"]
    horizontal = opts.get("orientation") == "h"
    bin_scale, count_scale = (ys_, xs_) if horizontal else (xs_, ys_)
    base = count_scale(0)
    alpha = opts.get("alpha", _D["hist_alpha"])
    edgecolor = opts.get("edgecolor")
    lw = opts.get("linewidth", _D["linewidth"]) if edgecolor else 1
    histtype = opts.get("histtype", "bar")
    if histtype not in ("bar", "step", "stepfilled"):
        raise ValueError(
            f"hist histtype={histtype!r} — must be 'bar', 'step', or 'stepfilled'."
        )
    bins = a["_bins"]

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
                                 stroke=edgecolor, stroke_width=lw,
                                 dash=opts.get("linestyle"), alpha=alpha))
        return "".join(out)

    # step / stepfilled — walk bin tops as one connected path.
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
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    stroke = edgecolor or col
    stroke_w = lw if edgecolor else _D["linewidth"]
    fill = col if histtype == "stepfilled" else None
    out.append(draw_path(d + " Z", fill=fill,
                         stroke=stroke, stroke_width=stroke_w,
                         dash=opts.get("linestyle"), alpha=alpha))
    return "".join(out)


def _bin_xs(a): return [b["x0"] for b in a["_bins"]] + [b["x1"] for b in a["_bins"]]
def _bin_ys(a): return [b["count"] for b in a["_bins"]] + [0]


def _hist_data_attrs(a):
    raw = a["data"]
    out = {"n": len(raw), "bins": len(a.get("_bins", [])) or a["opts"].get("bins", 10)}
    bins = a.get("_bins") or []
    if bins:
        out["x-min"] = bins[0]["x0"]
        out["x-max"] = bins[-1]["x1"]
        out["count-max"] = max(b["count"] for b in bins)
    return out


def _hist_horizontal(a): return a["opts"].get("orientation") == "h"
def _hist_xdomain(a): return _bin_ys(a) if _hist_horizontal(a) else _bin_xs(a)
def _hist_ydomain(a): return _bin_xs(a) if _hist_horizontal(a) else _bin_ys(a)


add_artist(ArtistSpec(
    name="hist",
    record=lambda args, kw: {"type": "hist", "data": to_list(args[0]), "opts": kw},
    xdomain=_hist_xdomain,
    ydomain=_hist_ydomain,
    draw=lambda a, ctx: _artist_hist(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_bar_legend_entries,
    data_attrs=_hist_data_attrs,
    force_zero_y=lambda a: not _hist_horizontal(a),
    force_zero_x=_hist_horizontal,
))
