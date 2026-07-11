"""Reference-line / span artists — decorate the frame.

`axhline` / `axvline` / `axhspan` / `axvspan` ignore autoscaling and span
the full frame regardless of the data scale. `axline` is the arbitrary-
direction sibling (matplotlib `axline` / ggplot `geom_abline`):

  c.axline((0, 0), (1, 1))          # infinite line through two points
  c.axline((0, 0), slope=1)         # point + slope (linear scales only)

`hlines` / `vlines` are the bounded, data-coordinate counterparts that
participate in autoscaling and use the color cycle so a labeled call acts
like a series.
"""
import math

from ..registry import ArtistSpec, add_artist
from ..scales import _LinearScale
from ..utils import broadcast
from .._spec import _D
from ..draw import segment, rect as draw_rect
from ._shared import _refline_legend_entries, _refspan_legend_entries


def _artist_axhline(a, xs_, ys_, iw, ih, col, warp=None):
    opts = a["opts"]
    y = ys_(a["y"])
    if not math.isfinite(y) or y < 0 or y > ih:
        return ""
    x0 = iw * opts.get("xmin", 0.0)
    x1 = iw * opts.get("xmax", 1.0)
    return segment(x0, y, x1, y,
                   color=col,
                   width=opts.get("linewidth", _D["refline_width"]),
                   dash=opts.get("linestyle"),
                   alpha=opts.get("alpha", 1),
                   project=warp)


def _artist_axvline(a, xs_, ys_, iw, ih, col, warp=None):
    opts = a["opts"]
    x = xs_(a["x"])
    if not math.isfinite(x) or x < 0 or x > iw:
        return ""
    y0 = ih * (1 - opts.get("ymax", 1.0))
    y1 = ih * (1 - opts.get("ymin", 0.0))
    return segment(x, y0, x, y1,
                   color=col,
                   width=opts.get("linewidth", _D["refline_width"]),
                   dash=opts.get("linestyle"),
                   alpha=opts.get("alpha", 1),
                   project=warp)


def _clip_infinite_line(px1, py1, px2, py2, w, h):
    """Clip the infinite line through two pixel points to the frame rect
    [0, w] x [0, h]. Returns `(x0, y0, x1, y1)` or None when the line
    misses the frame (or the two points coincide)."""
    dx = px2 - px1
    dy = py2 - py1
    if dx == 0 and dy == 0:
        return None
    t0, t1 = -math.inf, math.inf
    for d, q_lo, q_hi in ((dx, -px1, w - px1), (dy, -py1, h - py1)):
        if d == 0:
            if q_lo > 0 or q_hi < 0:
                return None
        else:
            ta, tb = q_lo / d, q_hi / d
            if ta > tb:
                ta, tb = tb, ta
            t0 = max(t0, ta)
            t1 = min(t1, tb)
    if t0 >= t1:
        return None
    return (px1 + t0 * dx, py1 + t0 * dy, px1 + t1 * dx, py1 + t1 * dy)


def _artist_axline(a, ctx):
    opts = a["opts"]
    xs_, ys_ = ctx.x_scale, ctx.y_scale
    if a["slope"] is not None:
        if not (isinstance(xs_, _LinearScale) and isinstance(ys_, _LinearScale)):
            raise ValueError(
                "axline: slope= is only meaningful on linear x and y scales. "
                "Pass a second point instead: c.axline((x1, y1), (x2, y2))."
            )
        x2, y2 = a["x1"] + 1.0, a["y1"] + a["slope"]
    else:
        x2, y2 = a["x2"], a["y2"]
    px1, py1 = xs_(a["x1"]), ys_(a["y1"])
    px2, py2 = xs_(x2), ys_(y2)
    if not all(math.isfinite(v) for v in (px1, py1, px2, py2)):
        return ""
    seg = _clip_infinite_line(px1, py1, px2, py2, ctx.iw, ctx.ih)
    if seg is None:
        return ""
    return segment(*seg,
                   color=ctx.color,
                   width=opts.get("linewidth", _D["refline_width"]),
                   dash=opts.get("linestyle"),
                   alpha=opts.get("alpha", 1),
                   project=ctx.warp)


def _artist_hlines(a, xs_, ys_, col, warp=None):
    opts = a["opts"]
    lw = opts.get("linewidth", _D["refline_width"])
    ls = opts.get("linestyle")
    alpha = opts.get("alpha", 1)
    out = []
    for y, x0, x1 in zip(a["ys"], a["xmins"], a["xmaxs"]):
        py = ys_(y); px0 = xs_(x0); px1 = xs_(x1)
        if not (math.isfinite(py) and math.isfinite(px0) and math.isfinite(px1)):
            continue
        out.append(segment(px0, py, px1, py, color=col, width=lw,
                           dash=ls, alpha=alpha, project=warp))
    return "".join(out)


def _artist_vlines(a, xs_, ys_, col, warp=None):
    opts = a["opts"]
    lw = opts.get("linewidth", _D["refline_width"])
    ls = opts.get("linestyle")
    alpha = opts.get("alpha", 1)
    out = []
    for x, y0, y1 in zip(a["xs"], a["ymins"], a["ymaxs"]):
        px = xs_(x); py0 = ys_(y0); py1 = ys_(y1)
        if not (math.isfinite(px) and math.isfinite(py0) and math.isfinite(py1)):
            continue
        out.append(segment(px, py0, px, py1, color=col, width=lw,
                           dash=ls, alpha=alpha, project=warp))
    return "".join(out)


def _artist_axhspan(a, xs_, ys_, iw, ih, col, warp=None):
    opts = a["opts"]
    y_a = ys_(a["ymin"]); y_b = ys_(a["ymax"])
    y0 = max(0.0, min(ih, min(y_a, y_b)))
    y1 = max(0.0, min(ih, max(y_a, y_b)))
    if y1 - y0 <= 0:
        return ""
    x0 = iw * opts.get("xmin", 0.0)
    x1 = iw * opts.get("xmax", 1.0)
    return draw_rect(x0, y0, x1 - x0, y1 - y0, fill=col,
                     alpha=opts.get("alpha", _D["refspan_alpha"]),
                     project=warp)


def _artist_axvspan(a, xs_, ys_, iw, ih, col, warp=None):
    opts = a["opts"]
    x_a = xs_(a["xmin"]); x_b = xs_(a["xmax"])
    x0 = max(0.0, min(iw, min(x_a, x_b)))
    x1 = max(0.0, min(iw, max(x_a, x_b)))
    if x1 - x0 <= 0:
        return ""
    y0 = ih * (1 - opts.get("ymax", 1.0))
    y1 = ih * (1 - opts.get("ymin", 0.0))
    return draw_rect(x0, y0, x1 - x0, y1 - y0, fill=col,
                     alpha=opts.get("alpha", _D["refspan_alpha"]),
                     project=warp)


# --- axhline ---

def _axhline_data_attrs(a):  return {"y": a["y"]}


add_artist(ArtistSpec(
    name="axhline",
    accepts_data_positional=False,
    record=lambda args, kw: {"type": "axhline", "y": args[0], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axhline(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color, ctx.warp),
    layer="foreground",
    uses_color_cycle=False,
    default_color=_D["refline_color"],
    legend_entries=_refline_legend_entries,
    data_attrs=_axhline_data_attrs,
))


# --- axvline ---

def _axvline_data_attrs(a):  return {"x": a["x"]}


add_artist(ArtistSpec(
    name="axvline",
    accepts_data_positional=False,
    record=lambda args, kw: {"type": "axvline", "x": args[0], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axvline(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color, ctx.warp),
    layer="foreground",
    uses_color_cycle=False,
    default_color=_D["refline_color"],
    legend_entries=_refline_legend_entries,
    data_attrs=_axvline_data_attrs,
))


# --- axline ---

def _axline_record(args, kw):
    if not args or len(args) > 2:
        raise TypeError(
            "axline takes a point and either a second point or slope=: "
            "c.axline((x1, y1), (x2, y2)) or c.axline((x1, y1), slope=2)."
        )
    xy1 = args[0]
    xy2 = args[1] if len(args) == 2 else None
    slope = kw.pop("slope", None)
    if (xy2 is None) == (slope is None):
        raise TypeError(
            "axline needs exactly one of a second point or slope=."
        )
    rec = {"type": "axline",
           "x1": xy1[0], "y1": xy1[1],
           "slope": None if slope is None else float(slope),
           "x2": None, "y2": None, "opts": kw}
    if xy2 is not None:
        rec["x2"] = xy2[0]
        rec["y2"] = xy2[1]
    return rec


def _axline_data_attrs(a):
    if a["slope"] is not None:
        return {"x1": a["x1"], "y1": a["y1"], "slope": a["slope"]}
    return {"x1": a["x1"], "y1": a["y1"], "x2": a["x2"], "y2": a["y2"]}


add_artist(ArtistSpec(
    name="axline",
    accepts_data_positional=False,
    record=_axline_record,
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=_artist_axline,
    layer="foreground",
    uses_color_cycle=False,
    default_color=_D["refline_color"],
    legend_entries=_refline_legend_entries,
    data_attrs=_axline_data_attrs,
))


# --- axhspan ---

def _axhspan_data_attrs(a):  return {"ymin": a["ymin"], "ymax": a["ymax"]}


add_artist(ArtistSpec(
    name="axhspan",
    record=lambda args, kw: {"type": "axhspan", "ymin": args[0], "ymax": args[1], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axhspan(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color, ctx.warp),
    layer="background",
    uses_color_cycle=False,
    default_color=_D["refspan_color"],
    legend_entries=_refspan_legend_entries,
    data_attrs=_axhspan_data_attrs,
))


# --- axvspan ---

def _axvspan_data_attrs(a):  return {"xmin": a["xmin"], "xmax": a["xmax"]}


add_artist(ArtistSpec(
    name="axvspan",
    record=lambda args, kw: {"type": "axvspan", "xmin": args[0], "xmax": args[1], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axvspan(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color, ctx.warp),
    layer="background",
    uses_color_cycle=False,
    default_color=_D["refspan_color"],
    legend_entries=_refspan_legend_entries,
    data_attrs=_axvspan_data_attrs,
))


# --- hlines ---

def _hlines_data_attrs(a):
    out = {"n": len(a["ys"])}
    if a["ys"]:
        out["y-min"] = min(a["ys"]); out["y-max"] = max(a["ys"])
    if a["xmins"] and a["xmaxs"]:
        out["x-min"] = min(a["xmins"]); out["x-max"] = max(a["xmaxs"])
    return out


def _hlines_record(args, kw):
    ys, xmins, xmaxs = broadcast(args[0], args[1], args[2])
    return {"type": "hlines", "ys": ys, "xmins": xmins, "xmaxs": xmaxs, "opts": kw}


add_artist(ArtistSpec(
    name="hlines",
    record=_hlines_record,
    xdomain=lambda a: a["xmins"] + a["xmaxs"],
    ydomain=lambda a: a["ys"],
    draw=lambda a, ctx: _artist_hlines(a, ctx.x_scale, ctx.y_scale, ctx.color, ctx.warp),
    legend_entries=_refline_legend_entries,
    data_attrs=_hlines_data_attrs,
))


# --- vlines ---

def _vlines_data_attrs(a):
    out = {"n": len(a["xs"])}
    if a["xs"]:
        out["x-min"] = min(a["xs"]); out["x-max"] = max(a["xs"])
    if a["ymins"] and a["ymaxs"]:
        out["y-min"] = min(a["ymins"]); out["y-max"] = max(a["ymaxs"])
    return out


def _vlines_record(args, kw):
    xs, ymins, ymaxs = broadcast(args[0], args[1], args[2])
    return {"type": "vlines", "xs": xs, "ymins": ymins, "ymaxs": ymaxs, "opts": kw}


add_artist(ArtistSpec(
    name="vlines",
    record=_vlines_record,
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: a["ymins"] + a["ymaxs"],
    draw=lambda a, ctx: _artist_vlines(a, ctx.x_scale, ctx.y_scale, ctx.color, ctx.warp),
    legend_entries=_refline_legend_entries,
    data_attrs=_vlines_data_attrs,
))
