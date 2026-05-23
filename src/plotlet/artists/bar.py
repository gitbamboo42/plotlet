"""Bar chart — single-series or multi-series with stack / dodge / fill.

Three input shapes, picked by which kwargs are present:

  Single-series (wide-form):
    c.bar(cats, vals)

  Multi-series (wide-form):
    c.bar(cats, [s_a, s_b, s_c], position="stack", labels=["A", "B", "C"])
    c.bar(cats, [...], position="dodge", labels=[...])
    c.bar(cats, [...], position="fill",  labels=[...])   # 100% stacked

  Long-form (seaborn / ggplot style):
    c.bar(data=df, x="cat", y="val", hue="series", position="stack")

`position` defaults to `"stack"` whenever there is more than one series
(matches ggplot's `geom_bar(position="stack")` default). Ignored for the
single-series case. Long-form sums duplicate (cat, hue) rows — ggplot's
`stat="identity"` behaviour for stacks.

Styling kwargs:
  orientation='v'     'h' for horizontal bars
  bottom=0            baseline value (single / dodge); stacks always start at 0
  alpha=<themed>      bar fill opacity
  edgecolor=None      edge stroke colour (None = no edge)
  linewidth=<themed>  edge stroke width (used only when edgecolor is set)
  width=0.8           dodged-group total width as a band fraction
  gap=0.1             slot-gap fraction between dodged bars
  palette=None        per-hue palette mapping (long-form / multi-series)
  labels=None         legend labels for wide-form multi-series
  label=None          legend label for single-series
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list, hue_color, dodge_positions
from .._spec import _D, _LEGSPEC
from ..draw import rect as draw_rect


_POSITIONS = ("stack", "dodge", "fill")


def _aggregate_long(data, x_col, y_col, hue_col):
    """Long-form table -> (cats, hues, series). series[j][i] sums y over
    rows where x == cats[i] and hue == hues[j]."""
    xs = to_list(data[x_col])
    ys = to_list(data[y_col])
    hs = to_list(data[hue_col]) if hue_col is not None else [None] * len(xs)
    cats, hues = [], []
    for c in xs:
        if c not in cats: cats.append(c)
    for h in hs:
        if h not in hues: hues.append(h)
    if not hues: hues = [None]
    series = [[0.0] * len(cats) for _ in hues]
    cat_idx = {c: i for i, c in enumerate(cats)}
    hue_idx = {h: j for j, h in enumerate(hues)}
    for x, y, h in zip(xs, ys, hs):
        series[hue_idx[h]][cat_idx[x]] += y
    return cats, hues, series


def _bar_record(args, kw):
    kw = dict(kw)
    if "data" in kw or "x" in kw or "y" in kw:
        data = kw.pop("data", None)
        x_col = kw.pop("x", None)
        y_col = kw.pop("y", None)
        hue_col = kw.pop("hue", None)
        if data is None or x_col is None or y_col is None:
            raise TypeError(
                "bar long-form requires data=, x=, y= (hue= optional)."
            )
        cats, hues, series = _aggregate_long(data, x_col, y_col, hue_col)
    else:
        cats = to_list(args[0])
        v = to_list(args[1])
        if v and hasattr(v[0], "__iter__") and not isinstance(v[0], str):
            series = [to_list(s) for s in v]
            labels = kw.pop("labels", None)
            hues = list(labels) if labels else [None] * len(series)
        else:
            series = [v]
            hues = [None]
    position = kw.pop("position", "stack" if len(series) > 1 else None)
    if position is not None and position not in _POSITIONS:
        raise ValueError(
            f"unknown position={position!r}; expected one of {_POSITIONS}."
        )
    return {"type": "bar", "cats": cats, "hues": hues, "series": series,
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


def _bar_draw(a, ctx):
    cats = a["cats"]
    hues = a["hues"]
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
    edgecolor = opts.get("edgecolor")
    lw = opts.get("linewidth", _D["linewidth"]) if edgecolor else 1
    sr = "crispEdges" if getattr(cat_scale, "padding", 0.2) == 0 else None
    multi = len(series) > 1

    if multi and position == "fill":
        totals = [sum(s[i] for s in series) or 1 for i in range(len(cats))]
        series = [[s[i] / totals[i] for i in range(len(cats))] for s in series]

    out = []
    def _emit(x, y, w, h, col):
        out.append(draw_rect(x, y, w, h, fill=col, stroke=edgecolor,
                             stroke_width=lw, dash=opts.get("linestyle"),
                             alpha=alpha, shape_rendering=sr))

    if multi and position in ("stack", "fill"):
        running = [0.0] * len(cats)
        for j, s in enumerate(series):
            col = hue_color(hues, palette, j, ctx.color)
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
            col = hue_color(hues, palette, j, ctx.color)
            for i, (cat, v) in enumerate(zip(cats, s)):
                cp, slot_w = dodge_positions(cat_scale, cat, len(hues), j,
                                             band_frac=width, gap=gap)
                vp = val_scale(v)
                if horizontal:
                    _emit(min(base_px, vp), cp - slot_w / 2,
                          abs(vp - base_px), slot_w, col)
                else:
                    _emit(cp - slot_w / 2, min(base_px, vp),
                          slot_w, abs(vp - base_px), col)
    else:
        col = ctx.color
        for cat, v in zip(cats, series[0]):
            cp = cat_scale(cat) - band / 2
            vp = val_scale(v)
            if horizontal:
                _emit(min(base_px, vp), cp, abs(vp - base_px), band, col)
            else:
                _emit(cp, min(base_px, vp), band, abs(vp - base_px), col)

    return "".join(out)


def _bar_legend_entries(a):
    hues = a["hues"]
    opts = a["opts"]
    alpha = opts.get("alpha", _D["bar_alpha"])
    sw = _LEGSPEC["swatch_width"]
    if hues == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(_a, _ctx, x0, y_mid):
            return draw_rect(x0, y_mid - 5, sw, 10,
                             fill=_a["_color"], alpha=alpha)
        return [{"label": label, "color": a.get("_color"), "paint": paint}]
    palette = opts.get("palette")
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col, _alpha=alpha):
            return draw_rect(x0, y_mid - 5, sw, 10, fill=_col, alpha=_alpha)
        entries.append({"label": str(h), "color": col, "paint": paint})
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
