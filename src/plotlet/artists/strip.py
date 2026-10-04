"""Strip / jitter plot: categorical scatter with deterministic per-point jitter.

No per-render RNG — jitter offsets are derived from a splitmix64 hash of each
point's indices so the SVG is byte-identical across runs.

Long-form only:
  c.add_strip(aes(x="cat", y="value"))              # vertical
  c.add_strip(aes(x="value", y="cat"))              # horizontal
  c.add_strip(aes(x="cat", y="value", color="group"), palette={...})

Mapping `aes(color="col")` dodges sub-strips side-by-side within each cat
and emits one legend entry per group level.

Aesthetics — scatter's vocabulary:
  color=<literal>       point color (None = series cycle default);
                        aes(color="col") → column-driven grouping
  edgecolor=<literal>   outline color — setting it draws the outline
  palette=              maps group levels → colors when color is mapped

Other styling kwargs:
  orientation=None      which axis holds the categories: 'x' (the upright
                        layout) or 'y'. Unset guesses it — whichever of
                        x/y is the discrete column becomes the category
                        axis, so aes(x="value", y="cat") reads as
                        horizontal on its own.
  width=0.8         total dodge-group width as a band fraction
  gap=0.1           slot-gap fraction between dodged sub-strips
  jitter=0.2        spread within each slot as a slot-width fraction
                    (points land in ±jitter/2 * slot_w from the slot center)
  size=3            point radius in pixels
  alpha=0.7         point opacity
  linewidth=None    outline width in px; only drawn when edgecolor= is
                    set (defaults to the spec marker stroke width)
  rasterize=None    None = auto-raster to one <image> above the point
                    threshold; True/False forces it on/off
"""
from ..registry import ArtistSpec, add_artist
from ..utils import (pack_opts, resolve_aes, dodge_positions,
                     categorical_groups, check_option,
                     group_color as _group_fill,
                     resolve_orientation)
from ..draw import circle
from ..draw import raster_declined, should_rasterize, splat_disks_by_color
from .._spec import _FRAME
from ._shared import point_outline


_M64 = 0xFFFFFFFFFFFFFFFF


def _jitter_hash(*ints):
    """Splitmix64-style avalanche — deterministic pseudo-random in [-0.5, 0.5]."""
    z = 0
    for a in ints:
        z = (z * 0x9E3779B97F4A7C15 + (a & _M64)) & _M64
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M64
    z ^= z >> 31
    return ((z & 0xFFFFFFFF) / 0xFFFFFFFF) - 0.5


def _resolve_color_kwarg(data, color):
    """For strip/swarm: `color` is None, a bare literal color, or an
    aes-mapped column (scatter's vocabulary). Returns
    `(color_literal, group_col)`."""
    if color is None:
        return None, None
    kind, value = resolve_aes(data, color)
    if kind == "column":
        return None, color
    return value, None


def _strip_record(data=None,
                  # input & grouping — consumed here at record
                  x=None, y=None, color=None,
                  # style — packed into opts for the draw/legend side
                  orientation=None, width=None, gap=None,
                  edgecolor=None, palette=None,
                  jitter=None, size=None, alpha=None, linewidth=None,
                  label=None, legend=None, rasterize=None):
    if data is None or x is None or y is None:
        raise TypeError(
            "strip requires data=, x=, y= (color= optional)."
        )
    check_option("strip", "orientation", orientation, ("x", "y"))
    color_literal, group_col = _resolve_color_kwarg(data, color)
    orientation, cat_col, val_col = resolve_orientation(
        "strip", data, x, y, orientation, require_numeric=False)
    cats, groups, vals = categorical_groups(data, cat_col, val_col, group_col)
    opts = pack_opts(orientation=orientation, width=width, gap=gap,
                     color=color_literal, edgecolor=edgecolor,
                     palette=palette, jitter=jitter, size=size,
                     alpha=alpha, linewidth=linewidth, label=label,
                     legend=legend, rasterize=rasterize)
    if group_col is not None and group_col == cat_col:
        opts["_redundant_grouping"] = True
    return {"type": "strip", "cats": cats, "groups": groups,
            "vals": vals, "opts": opts}


def _strip_horizontal(a): return a["opts"].get("orientation") == "y"
def _strip_values(a):
    return [v for row in a["vals"] for g in row for v in g]


def _strip_xdomain(a):
    return _strip_values(a) if _strip_horizontal(a) else a["cats"]


def _strip_ydomain(a):
    return a["cats"] if _strip_horizontal(a) else _strip_values(a)


def _strip_draw(a, ctx):
    cats, groups, vals = a["cats"], a["groups"], a["vals"]
    n_groups = len(groups)
    opts = a["opts"]
    palette   = opts.get("palette")
    w_frac    = opts.get("width", 0.8)
    gap       = opts.get("gap", 0.1)
    jitter    = opts.get("jitter", 0.2)
    r         = opts.get("size", 3)
    alpha     = opts.get("alpha", 0.7)
    stroke, lw = point_outline(opts)
    horizontal = _strip_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    redundant = opts.get("_redundant_grouping", False)
    marks = []  # (color, cx, cy) — computed once, drawn as vector or raster
    for i, cat in enumerate(cats):
        for j in range(n_groups):
            vs = vals[i][j]
            if not vs:
                continue
            col = _group_fill(groups, palette, j, ctx.color)
            cp, slot_w = dodge_positions(cat_scale, cat,
                                         1 if redundant else n_groups,
                                         0 if redundant else j,
                                          band_frac=w_frac, gap=gap)
            for k, v in enumerate(vs):
                if v != v:  # NaN
                    continue
                off = _jitter_hash(i, j, k) * slot_w * jitter
                vp = val_scale(v)
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
        raster_declined("strip", len(marks), reason, opts.get("rasterize"))
    out = [circle(cx, cy, r, fill=col, alpha=alpha,
                  stroke=stroke, stroke_width=lw, project=ctx.warp)
           for col, cx, cy in marks]
    return "".join(out)


def _strip_legend_entries(a):
    groups = a["groups"]
    if groups == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    r = opts.get("size", 3)
    alpha = opts.get("alpha", 0.7)
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
    name="strip",
    record=_strip_record,
    xdomain=_strip_xdomain,
    ydomain=_strip_ydomain,
    draw=_strip_draw,
    legend_entries=_strip_legend_entries,
))
