"""Bar chart — long-form only.

  c.bar(data=df, x="cat", y="val")                                  # single
  c.bar(data=df, x="cat", y="val", fill="C0")                       # constant color
  c.bar(data=df, x="cat", y="val", fill="series", position="stack") # grouped
  c.bar(data=df, x="cat", y="val", fill="series", position="dodge")
  c.bar(data=df, x="cat", y="val", fill="series", position="fill")  # 100% stack

`position` defaults to `"stack"` whenever `fill=` is a column with more
than one unique value. Duplicate (cat, group) rows are summed.

Aesthetics:
  fill=         literal color OR column name → grouped multi-series
  color=        stroke color (constant, default None = no stroke)
  palette=      maps group levels → colors when `fill=` is a column

Other styling kwargs:
  orientation='v'     'h' for horizontal bars
  bottom=0            baseline value (single / dodge); stacks always start at 0
  alpha=<themed>      bar fill opacity
  linewidth=<themed>  stroke width (used only when color is set)
  width=0.8           dodged-group total width as a band fraction
  gap=0.1             slot-gap fraction between dodged bars
  label=None          legend label (overridden by column-driven grouping)
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list, resolve_aes, palette_color, dodge_positions
from ..draw import TAB10, resolve_color
from .._spec import _D, _LEGSPEC
from ..draw import rect as draw_rect


_POSITIONS = ("stack", "dodge", "fill")


def _aggregate_long(data, x_col, y_col, group_col):
    """Long-form table -> (cats, groups, series). series[j][i] sums y over
    rows where x == cats[i] and the grouping value == groups[j]."""
    xs = to_list(data[x_col])
    ys = to_list(data[y_col])
    gs = to_list(data[group_col]) if group_col is not None else [None] * len(xs)
    cats, groups = [], []
    for c in xs:
        if c not in cats: cats.append(c)
    for g in gs:
        if g not in groups: groups.append(g)
    if not groups: groups = [None]
    series = [[0] * len(cats) for _ in groups]
    cat_idx = {c: i for i, c in enumerate(cats)}
    group_idx = {g: j for j, g in enumerate(groups)}
    for x, y, g in zip(xs, ys, gs):
        series[group_idx[g]][cat_idx[x]] += y
    return cats, groups, series


def _bar_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "bar requires long-form input: "
            "c.bar(data=df, x='col', y='col', fill='col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    if data is None or x_col is None or y_col is None:
        raise TypeError(
            "bar requires data=, x=, y= (fill= optional)."
        )
    # `fill=` may be a literal color or a column name. Column → drives
    # grouping; literal → applied to every bar.
    fill = kw.pop("fill", None)
    fill_kind, fill_value = resolve_aes(data, fill)
    group_col = fill if fill_kind == "column" else None
    cats, groups, series = _aggregate_long(data, x_col, y_col, group_col)
    if fill_kind == "literal":
        kw["_fill_literal"] = fill_value
    bottom = kw.get("bottom", 0)
    if hasattr(bottom, "__iter__") and not isinstance(bottom, str):
        raise TypeError(
            "bar: bottom= must be a scalar baseline; for grouped bars "
            "pass fill='series_col' with position='stack'."
        )
    position = kw.pop("position", "stack" if len(series) > 1 else None)
    if position is not None and position not in _POSITIONS:
        raise ValueError(
            f"unknown position={position!r}; expected one of {_POSITIONS}."
        )
    return {"type": "bar", "cats": cats, "groups": groups, "series": series,
            "_position": position, "opts": kw}


def _bar_horizontal(a): return a["opts"].get("orientation") == "h"


def _bar_vals_for_domain(a):
    series = a["series"]
    position = a["_position"]
    bottom = a["opts"].get("bottom", 0)
    multi = len(series) > 1
    if multi and position == "fill":
        return [0, 1]
    if multi and position == "stack":
        sums = [sum(s[i] for s in series) for i in range(len(a["cats"]))]
        return sums + [0]
    flat = [v for s in series for v in s]
    return flat + [0, bottom]


def _bar_xdomain(a):
    return _bar_vals_for_domain(a) if _bar_horizontal(a) else a["cats"]


def _bar_ydomain(a):
    return a["cats"] if _bar_horizontal(a) else _bar_vals_for_domain(a)


def _bar_data_attrs(a):
    flat = [v for s in a["series"] for v in s
            if isinstance(v, (int, float)) and v == v]
    out = {"n": len(a["cats"])}
    if flat:
        out["y-min"] = min(flat)
        out["y-max"] = max(flat)
    return out


def _group_fill(groups, palette, j, fallback):
    """Per-group fill: ungrouped → fallback; grouped → palette lookup
    with TAB10 wraparound."""
    if groups == [None]:
        return fallback
    return palette_color(palette, groups[j], j) or TAB10[j % 10]


def _bar_draw(a, ctx):
    cats = a["cats"]
    groups = a["groups"]
    series = a["series"]
    position = a["_position"]
    opts = a["opts"]
    palette = opts.get("palette")
    horizontal = _bar_horizontal(a)
    cat_scale, val_scale = ((ctx.y_scale, ctx.x_scale) if horizontal
                            else (ctx.x_scale, ctx.y_scale))
    band = cat_scale.bandwidth
    bottom = opts.get("bottom", 0)
    base_px = val_scale(bottom)
    alpha = opts.get("alpha", _D["bar_alpha"])
    stroke = resolve_color(opts.get("color"))
    lw = opts.get("linewidth", _D["linewidth"]) if stroke else 1
    sr = "crispEdges" if getattr(cat_scale, "padding", 0.2) == 0 else None
    fill_literal = resolve_color(opts.get("_fill_literal"))
    fill_fallback = fill_literal if fill_literal is not None else ctx.color
    multi = len(series) > 1

    if multi and position == "fill":
        totals = [sum(s[i] for s in series) or 1 for i in range(len(cats))]
        series = [[s[i] / totals[i] for i in range(len(cats))] for s in series]

    out = []
    def _emit(x, y, w, h, col):
        out.append(draw_rect(x, y, w, h, fill=col, stroke=stroke,
                             stroke_width=lw, dash=opts.get("linestyle"),
                             alpha=alpha, shape_rendering=sr))

    if multi and position in ("stack", "fill"):
        running = [0.0] * len(cats)
        for j, s in enumerate(series):
            col = _group_fill(groups, palette, j, fill_fallback)
            for i, (cat, v) in enumerate(zip(cats, s)):
                cp = cat_scale(cat) - band / 2
                bot_px = val_scale(running[i])
                top_px = val_scale(running[i] + v)
                if horizontal:
                    _emit(min(bot_px, top_px), cp,
                          abs(top_px - bot_px), band, col)
                else:
                    _emit(cp, min(bot_px, top_px),
                          band, abs(top_px - bot_px), col)
                running[i] += v
    elif multi and position == "dodge":
        width = opts.get("width", 0.8)
        gap = opts.get("gap", 0.1)
        for j, s in enumerate(series):
            col = _group_fill(groups, palette, j, fill_fallback)
            for i, (cat, v) in enumerate(zip(cats, s)):
                cp, slot_w = dodge_positions(cat_scale, cat, len(groups), j,
                                             band_frac=width, gap=gap)
                vp = val_scale(v)
                if horizontal:
                    _emit(min(base_px, vp), cp - slot_w / 2,
                          abs(vp - base_px), slot_w, col)
                else:
                    _emit(cp - slot_w / 2, min(base_px, vp),
                          slot_w, abs(vp - base_px), col)
    else:
        col = fill_fallback
        for cat, v in zip(cats, series[0]):
            cp = cat_scale(cat) - band / 2
            vp = val_scale(v)
            if horizontal:
                _emit(min(base_px, vp), cp, abs(vp - base_px), band, col)
            else:
                _emit(cp, min(base_px, vp), band, abs(vp - base_px), col)

    return "".join(out)


def _bar_legend_entries(a):
    groups = a["groups"]
    opts = a["opts"]
    alpha = opts.get("alpha", _D["bar_alpha"])
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
        def paint(_a, _ctx, x0, y_mid, _col=col, _alpha=alpha):
            return draw_rect(x0, y_mid - 5, sw, 10, fill=_col, alpha=_alpha)
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="bar",
    record=_bar_record,
    xdomain=_bar_xdomain,
    ydomain=_bar_ydomain,
    draw=_bar_draw,
    legend_entries=_bar_legend_entries,
    data_attrs=_bar_data_attrs,
    force_zero_y=lambda a: not _bar_horizontal(a),
    force_zero_x=_bar_horizontal,
))
