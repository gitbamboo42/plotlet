"""Bee-swarm plot: categorical scatter with greedy non-overlapping point placement.

Wide-form: c.swarm(cats, values_per_cat)
Long-form:  c.swarm(data=df, x="cat", y="value", hue="group", palette={...})

Long-form with `hue=` dodges sub-swarms side-by-side within each cat and emits
one legend entry per hue category.

Styling kwargs:
  orientation='v'   'h' for horizontal (cats on y axis)
  width=0.8         total dodge-group width as a band fraction
  gap=0.1           slot-gap fraction between dodged sub-swarms
  size=3            point radius in pixels
  alpha=0.9         point opacity
  linewidth=0       outline stroke width (0 = no outline)
  edgecolor=<line>  outline color when linewidth > 0
"""
from ..registry import ArtistSpec, add_artist
from ..draw import circle
from ..utils import to_list, hue_color, dodge_positions, categorical_groups
from .._spec import _FRAME


def _swarm_record(args, kw):
    if "data" in kw or "x" in kw or "y" in kw:
        data = kw.pop("data", None)
        x = kw.pop("x", None)
        y = kw.pop("y", None)
        hue = kw.pop("hue", None)
        if data is None or x is None or y is None:
            raise TypeError(
                "swarm long-form requires data=, x=, y= (hue= optional)."
            )
        cats, hues, groups = categorical_groups(data, x, y, hue)
    elif len(args) >= 2:
        cats = to_list(args[0])
        groups_1d = [list(to_list(g)) for g in args[1]]
        hues = [None]
        groups = [[g] for g in groups_1d]
    else:
        raise TypeError(
            "swarm requires either positional (cats, values_per_cat) "
            "or keyword (data=, x=, y=)."
        )
    return {"type": "swarm", "cats": cats, "hues": hues,
            "groups": groups, "opts": kw}


def _swarm_horizontal(a): return a["opts"].get("orientation") == "h"
def _swarm_values(a):
    return [v for row in a["groups"] for g in row for v in g]


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
    cats, hues, groups = a["cats"], a["hues"], a["groups"]
    n_hues = len(hues)
    opts = a["opts"]
    palette   = opts.get("palette")
    w_frac    = opts.get("width", 0.8)
    gap       = opts.get("gap", 0.1)
    r         = opts.get("size", 3)
    alpha     = opts.get("alpha", 0.9)
    lw        = opts.get("linewidth", 0)
    edgecolor = opts.get("edgecolor", _FRAME["color"])
    horizontal = _swarm_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    out = []
    for i, cat in enumerate(cats):
        for j in range(n_hues):
            vals = groups[i][j]
            if not vals:
                continue
            col = hue_color(hues, palette, j, ctx.color)
            cp, _ = dodge_positions(cat_scale, cat, n_hues, j,
                                    band_frac=w_frac, gap=gap)
            val_px = [val_scale(v) for v in vals]
            offsets = _place_swarm(val_px, r)
            for vp, off in zip(val_px, offsets):
                cx, cy = (vp, cp + off) if horizontal else (cp + off, vp)
                out.append(circle(cx, cy, r, fill=col, alpha=alpha,
                                  stroke=edgecolor if lw > 0 else None,
                                  stroke_width=lw))
    return "".join(out)


def _swarm_legend_entries(a):
    hues = a["hues"]
    if hues == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    r = opts.get("size", 3)
    alpha = opts.get("alpha", 0.9)
    lw = opts.get("linewidth", 0)
    edgecolor = opts.get("edgecolor", _FRAME["color"])
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, _FRAME["color"])
        def paint(_a, _ctx, _x0, _y_mid,
                  _col=col, _r=r, _al=alpha, _lw=lw, _ec=edgecolor):
            return circle(_x0 + 11, _y_mid, _r, fill=_col, alpha=_al,
                          stroke=_ec if _lw > 0 else None, stroke_width=_lw)
        entries.append({"label": str(h), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="swarm",
    record=_swarm_record,
    xdomain=_swarm_xdomain,
    ydomain=_swarm_ydomain,
    draw=_swarm_draw,
    legend_entries=_swarm_legend_entries,
))
