"""Strip / jitter plot: categorical scatter with deterministic per-point jitter.

No per-render RNG — jitter offsets are derived from a splitmix64 hash of each
point's indices so the SVG is byte-identical across runs.

Long-form only:
  c.strip(data=df, x="cat", y="value")
  c.strip(data=df, x="cat", y="value", fill="group", palette={...})

Long-form with `fill="col"` dodges sub-strips side-by-side within each cat and
emits one legend entry per group level.

Aesthetics:
  fill=<col>/<literal>  point color (col = column-driven grouping, literal
                        color string, or None for the cycle default)
  color=<literal>       point outline (defaults to frame color when used)
  palette=              maps group levels → fills when `fill=` is a column

Other styling kwargs:
  orientation='v'   'h' for horizontal (cats on y axis)
  width=0.8         total dodge-group width as a band fraction
  gap=0.1           slot-gap fraction between dodged sub-strips
  jitter=0.2        spread within each slot as a slot-width fraction
                    (points land in ±jitter/2 * slot_w from the slot center)
  size=3            point radius in pixels
  alpha=0.7         point opacity
  linewidth=0       outline stroke width (0 = no outline)
"""
from ..registry import ArtistSpec, add_artist
from ..utils import (pack_opts, resolve_aes, dodge_positions,
                     categorical_groups, group_color as _group_fill)
from ..draw import resolve_color
from ..draw import circle
from .._spec import _FRAME


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


def _resolve_fill_kwarg(data, fill):
    """For strip/swarm: `fill=` accepts None, literal color, or column name.
    Returns `(fill_literal, group_col)`."""
    if fill is None:
        return None, None
    kind, value = resolve_aes(data, fill)
    if kind == "column":
        return None, fill
    return value, None


def _strip_record(data=None,
                  # input & grouping — consumed here at record
                  x=None, y=None, fill=None,
                  # style — packed into opts for the draw/legend side
                  orientation=None, width=None, gap=None,
                  color=None, palette=None,
                  jitter=None, size=None, alpha=None, linewidth=None,
                  label=None, legend=None):
    if data is None or x is None or y is None:
        raise TypeError(
            "strip requires data=, x=, y= (fill= optional)."
        )
    fill_literal, group_col = _resolve_fill_kwarg(data, fill)
    cats, groups, vals = categorical_groups(data, x, y, group_col)
    opts = pack_opts(orientation=orientation, width=width, gap=gap,
                     color=color, palette=palette, jitter=jitter,
                     size=size, alpha=alpha, linewidth=linewidth,
                     label=label, legend=legend)
    if fill_literal is not None:
        opts["_fill_literal"] = fill_literal
    if group_col is not None and group_col == x:
        opts["_redundant_grouping"] = True
    return {"type": "strip", "cats": cats, "groups": groups,
            "vals": vals, "opts": opts}


def _strip_horizontal(a): return a["opts"].get("orientation") == "h"
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
    lw        = opts.get("linewidth", 0)
    stroke    = resolve_color(opts.get("color")) or _FRAME["color"]
    fill_literal = resolve_color(opts.get("_fill_literal"))
    fill_fallback = fill_literal if fill_literal is not None else ctx.color
    horizontal = _strip_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    redundant = opts.get("_redundant_grouping", False)
    out = []
    for i, cat in enumerate(cats):
        for j in range(n_groups):
            vs = vals[i][j]
            if not vs:
                continue
            col = _group_fill(groups, palette, j, fill_fallback)
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
                out.append(circle(cx, cy, r, fill=col, alpha=alpha,
                                  stroke=stroke if lw > 0 else None,
                                  stroke_width=lw, project=ctx.warp))
    return "".join(out)


def _strip_legend_entries(a):
    groups = a["groups"]
    if groups == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    r = opts.get("size", 3)
    alpha = opts.get("alpha", 0.7)
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
    name="strip",
    record=_strip_record,
    xdomain=_strip_xdomain,
    ydomain=_strip_ydomain,
    draw=_strip_draw,
    legend_entries=_strip_legend_entries,
))
