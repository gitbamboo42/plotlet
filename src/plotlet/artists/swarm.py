"""Bee-swarm plot: categorical scatter with greedy non-overlapping point placement.

Long-form only:
  c.add_swarm(aes(x="cat", y="value"))
  c.add_swarm(aes(x="cat", y="value", color="group"), palette={...})

Mapping `aes(color="col")` dodges sub-swarms side-by-side within each cat
and emits one legend entry per group level.

Aesthetics — scatter's vocabulary:
  color=<literal>       point color (None = series cycle default);
                        aes(color="col") → column-driven grouping
  edgecolor=<literal>   outline color — setting it draws the outline
  palette=              maps group levels → colors when color is mapped

Other styling kwargs:
  orientation='v'   'h' for horizontal (cats on y axis)
  width=0.8         total dodge-group width as a band fraction
  gap=0.1           slot-gap fraction between dodged sub-swarms
  size=3            point radius in pixels
  alpha=0.9         point opacity
  linewidth=None    outline width in px; only drawn when edgecolor= is
                    set (defaults to the spec marker stroke width)
  rasterize=None    None = auto-raster to one <image> above the point
                    threshold; True/False forces it on/off
"""
from ..registry import ArtistSpec, add_artist
from ..draw import circle
from ..utils import (pack_opts, resolve_aes, dodge_positions,
                     categorical_groups, _drop_nan, check_option,
                     group_color as _group_fill)
from ..draw import raster_declined, should_rasterize, splat_disks_by_color
from .._spec import _FRAME
from ._shared import point_outline


def _resolve_color_kwarg(data, color):
    """See strip's `_resolve_color_kwarg` — scatter's vocabulary."""
    if color is None:
        return None, None
    kind, value = resolve_aes(data, color)
    if kind == "column":
        return None, color
    return value, None


def _swarm_record(data=None,
                  # input & grouping — consumed here at record
                  x=None, y=None, color=None,
                  # style — packed into opts for the draw/legend side
                  orientation=None, width=None, gap=None,
                  edgecolor=None, palette=None,
                  size=None, alpha=None, linewidth=None,
                  label=None, legend=None, rasterize=None):
    if data is None or x is None or y is None:
        raise TypeError(
            "swarm requires data=, x=, y= (color= optional)."
        )
    check_option("swarm", "orientation", orientation, ("v", "h"))
    color_literal, group_col = _resolve_color_kwarg(data, color)
    cats, groups, vals = categorical_groups(data, x, y, group_col)
    opts = pack_opts(orientation=orientation, width=width, gap=gap,
                     color=color_literal, edgecolor=edgecolor,
                     palette=palette, size=size, alpha=alpha,
                     linewidth=linewidth, label=label, legend=legend,
                     rasterize=rasterize)
    if group_col is not None and group_col == x:
        opts["_redundant_grouping"] = True
    return {"type": "swarm", "cats": cats, "groups": groups,
            "vals": vals, "opts": opts}


def _swarm_horizontal(a): return a["opts"].get("orientation") == "h"
def _swarm_values(a):
    # NaN dropped here and in draw — it has no position, and one NaN
    # poisons min/max domain resolution.
    return _drop_nan([v for row in a["vals"] for g in row for v in g])


def _swarm_xdomain(a):
    return _swarm_values(a) if _swarm_horizontal(a) else a["cats"]


def _swarm_ydomain(a):
    return a["cats"] if _swarm_horizontal(a) else _swarm_values(a)


def _place_swarm(val_pixels, r):
    """Return per-point cat-axis offset (pixels) so no two circles overlap.

    Greedy: process in value-axis order, try offset=0 first, then expand
    outward until a non-colliding slot is found."""
    diam = 2 * r + 0.5
    placed = []
    out = [None] * len(val_pixels)
    for idx in sorted(range(len(val_pixels)), key=lambda i: val_pixels[i]):
        v = val_pixels[idx]
        for k in range(200):
            for sign in (1, -1) if k > 0 else (1,):
                cand = sign * k * (diam / 2)
                ok = True
                for xo, vo in placed:
                    if abs(vo - v) >= diam:
                        continue
                    if (xo - cand) ** 2 + (vo - v) ** 2 < diam * diam:
                        ok = False; break
                if ok:
                    out[idx] = cand
                    placed.append((cand, v))
                    break
            if out[idx] is not None:
                break
        if out[idx] is None:
            out[idx] = 0
    return out


def _swarm_draw(a, ctx):
    cats, groups, vals = a["cats"], a["groups"], a["vals"]
    n_groups = len(groups)
    opts = a["opts"]
    palette   = opts.get("palette")
    w_frac    = opts.get("width", 0.8)
    gap       = opts.get("gap", 0.1)
    r         = opts.get("size", 3)
    alpha     = opts.get("alpha", 0.9)
    stroke, lw = point_outline(opts)
    horizontal = _swarm_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    redundant = opts.get("_redundant_grouping", False)
    marks = []  # (color, cx, cy) — computed once, drawn as vector or raster
    for i, cat in enumerate(cats):
        for j in range(n_groups):
            vs = _drop_nan(vals[i][j])
            if not vs:
                continue
            col = _group_fill(groups, palette, j, ctx.color)
            cp, _ = dodge_positions(cat_scale, cat,
                                    1 if redundant else n_groups,
                                    0 if redundant else j,
                                    band_frac=w_frac, gap=gap)
            val_px = [val_scale(v) for v in vs]
            offsets = _place_swarm(val_px, r)
            for vp, off in zip(val_px, offsets):
                cx, cy = (vp, cp + off) if horizontal else (cp + off, vp)
                marks.append((col, cx, cy))
    # Raster fast-path above the mark threshold; a style the splatter
    # can't reproduce declines loudly (raster_declined) before falling
    # back to vector marks.
    if should_rasterize(len(marks), opts.get("rasterize")):
        reason = None
        if ctx.warp is not None:
            reason = "the panel's coordinate system is not affine"
        elif stroke is not None:
            reason = "point outlines (edgecolor=) can't be splatted"
        if reason is None:
            img = splat_disks_by_color(marks, r, alpha, ctx.iw, ctx.ih)
            if img is not None:
                return img
            reason = "a group color is not a plain solid color"
        raster_declined("swarm", len(marks), reason, opts.get("rasterize"))
    out = [circle(cx, cy, r, fill=col, alpha=alpha,
                  stroke=stroke, stroke_width=lw, project=ctx.warp)
           for col, cx, cy in marks]
    return "".join(out)


def _swarm_legend_entries(a):
    groups = a["groups"]
    if groups == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    r = opts.get("size", 3)
    alpha = opts.get("alpha", 0.9)
    stroke, lw = point_outline(opts)
    entries = []
    for j, g in enumerate(groups):
        col = _group_fill(groups, palette, j, _FRAME["color"])
        def paint(_a, _ctx, _x0, _y_mid,
                  _col=col, _r=r, _al=alpha, _lw=lw, _ec=stroke):
            return circle(_x0 + 11, _y_mid, _r, fill=_col, alpha=_al,
                          stroke=_ec, stroke_width=_lw)
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="swarm",
    record=_swarm_record,
    xdomain=_swarm_xdomain,
    ydomain=_swarm_ydomain,
    draw=_swarm_draw,
    legend_entries=_swarm_legend_entries,
))
