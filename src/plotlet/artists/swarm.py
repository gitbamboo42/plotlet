"""Bee-swarm plot: categorical scatter with greedy non-overlapping point placement.

Long-form only:
  c.swarm(data=df, x="cat", y="value")
  c.swarm(data=df, x="cat", y="value", fill="group", palette={...})

Long-form with `fill="col"` dodges sub-swarms side-by-side within each cat
and emits one legend entry per group level.

Aesthetics:
  fill=<col>/<literal>  point color (col = column-driven grouping, literal
                        color string, or None for the cycle default)
  color=<literal>       point outline (defaults to frame color when used)
  palette=              maps group levels → fills when `fill=` is a column

Other styling kwargs:
  orientation='v'   'h' for horizontal (cats on y axis)
  width=0.8         total dodge-group width as a band fraction
  gap=0.1           slot-gap fraction between dodged sub-swarms
  size=3            point radius in pixels
  alpha=0.9         point opacity
  linewidth=0       outline stroke width (0 = no outline)
"""
from ..registry import ArtistSpec, add_artist
from ..draw import circle
from ..utils import (pack_opts, resolve_aes, dodge_positions,
                     categorical_groups, _drop_nan,
                     group_color as _group_fill)
from ..draw import resolve_color
from .._spec import _FRAME


def _resolve_fill_kwarg(data, fill):
    if fill is None:
        return None, None
    kind, value = resolve_aes(data, fill)
    if kind == "column":
        return None, fill
    return value, None


def _swarm_record(data=None,
                  # input & grouping — consumed here at record
                  x=None, y=None, fill=None,
                  # style — packed into opts for the draw/legend side
                  orientation=None, width=None, gap=None,
                  color=None, palette=None,
                  size=None, alpha=None, linewidth=None,
                  label=None, legend=None):
    if data is None or x is None or y is None:
        raise TypeError(
            "swarm requires data=, x=, y= (fill= optional)."
        )
    fill_literal, group_col = _resolve_fill_kwarg(data, fill)
    cats, groups, vals = categorical_groups(data, x, y, group_col)
    opts = pack_opts(orientation=orientation, width=width, gap=gap,
                     color=color, palette=palette,
                     size=size, alpha=alpha, linewidth=linewidth,
                     label=label, legend=legend)
    if fill_literal is not None:
        opts["_fill_literal"] = fill_literal
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
    lw        = opts.get("linewidth", 0)
    stroke    = resolve_color(opts.get("color")) or _FRAME["color"]
    fill_literal = resolve_color(opts.get("_fill_literal"))
    fill_fallback = fill_literal if fill_literal is not None else ctx.color
    horizontal = _swarm_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    redundant = opts.get("_redundant_grouping", False)
    out = []
    for i, cat in enumerate(cats):
        for j in range(n_groups):
            vs = _drop_nan(vals[i][j])
            if not vs:
                continue
            col = _group_fill(groups, palette, j, fill_fallback)
            cp, _ = dodge_positions(cat_scale, cat,
                                    1 if redundant else n_groups,
                                    0 if redundant else j,
                                    band_frac=w_frac, gap=gap)
            val_px = [val_scale(v) for v in vs]
            offsets = _place_swarm(val_px, r)
            for vp, off in zip(val_px, offsets):
                cx, cy = (vp, cp + off) if horizontal else (cp + off, vp)
                out.append(circle(cx, cy, r, fill=col, alpha=alpha,
                                  stroke=stroke if lw > 0 else None,
                                  stroke_width=lw, project=ctx.warp))
    return "".join(out)


def _swarm_legend_entries(a):
    groups = a["groups"]
    if groups == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    r = opts.get("size", 3)
    alpha = opts.get("alpha", 0.9)
    lw = opts.get("linewidth", 0)
    stroke = resolve_color(opts.get("color")) or _FRAME["color"]
    entries = []
    for j, g in enumerate(groups):
        col = _group_fill(groups, palette, j, _FRAME["color"])
        def paint(_a, _ctx, _x0, _y_mid,
                  _col=col, _r=r, _al=alpha, _lw=lw, _ec=stroke):
            return circle(_x0 + 11, _y_mid, _r, fill=_col, alpha=_al,
                          stroke=_ec if _lw > 0 else None, stroke_width=_lw)
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
