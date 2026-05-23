"""Filled-region artists over x/y series.

`fill_between(xs, y1, y2)` fills between two curves. `area(xs, ys)`
is the single-series shorthand. Passing a list-of-series turns it into a
stacked area chart (ggplot's `geom_area(position="stack")`), and `data=`
+ `hue=` accepts a long-form table.

  c.area(xs, ys)                                              # single
  c.area(xs, [s_a, s_b, s_c], labels=["A", "B", "C"])         # stacked
  c.area(data=df, x="x", y="y", hue="series")                 # long-form
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list, hue_color
from .._spec import _D, _LEGSPEC
from ..draw import polygon as draw_polygon, rect as draw_rect
from ._shared import (_xy_minmax, _line_legend_entries, _bar_legend_entries,
                       _CURVE_VALUES, _step_coords)


# --- fill_between ---

def _artist_fill_between(a, xs_, ys_, col):
    opts = a["opts"]
    curve = opts.get("curve", "linear")
    if curve not in _CURVE_VALUES:
        raise ValueError(
            f"unknown curve={curve!r}; expected one of {_CURVE_VALUES}"
        )
    # Apply step interleaving to both edges so the polygon zips correctly
    # — for constant baselines (area) this still interleaves x-coords,
    # which the upper edge needs to pair with.
    if curve == "linear":
        upper_xs, upper_ys = a["xs"], a["y1"]
        lower_xs, lower_ys = a["xs"], a["y2"]
    else:
        mode = curve[5:]
        upper_xs, upper_ys = _step_coords(a["xs"], a["y1"], mode)
        lower_xs, lower_ys = _step_coords(a["xs"], a["y2"], mode)
    upper = [(xs_(x), ys_(y)) for x, y in zip(upper_xs, upper_ys)]
    lower = [(xs_(x), ys_(y)) for x, y in zip(lower_xs, lower_ys)]
    pts = upper + list(reversed(lower))
    return draw_polygon(pts, fill=col,
                        alpha=opts.get("alpha", _D["fill_alpha"]))


def _fill_between_data_attrs(a):
    ys_all = list(a["y1"]) + list(a["y2"])
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], ys_all))
    curve = a["opts"].get("curve")
    if curve and curve != "linear":
        out["curve"] = curve
    return out


add_artist(ArtistSpec(
    name="fill_between",
    record=lambda args, kw: {"type": "fill_between",
                              "xs": to_list(args[0]),
                              "y1": to_list(args[1]),
                              "y2": to_list(args[2]),
                              "opts": kw},
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: list(a["y1"]) + list(a["y2"]),
    draw=lambda a, ctx: _artist_fill_between(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_line_legend_entries,
    data_attrs=_fill_between_data_attrs,
))


# --- area ---

def _aggregate_long_xy(data, x_col, y_col, hue_col):
    """Long-form table -> (xs, hues, series). series[j][i] sums y over
    rows where x == xs[i] and hue == hues[j]."""
    xs_all = to_list(data[x_col])
    ys_all = to_list(data[y_col])
    hs = to_list(data[hue_col]) if hue_col is not None else [None] * len(xs_all)
    xs, hues = [], []
    for x in xs_all:
        if x not in xs: xs.append(x)
    for h in hs:
        if h not in hues: hues.append(h)
    if not hues: hues = [None]
    series = [[0.0] * len(xs) for _ in hues]
    x_idx = {x: i for i, x in enumerate(xs)}
    hue_idx = {h: j for j, h in enumerate(hues)}
    for x, y, h in zip(xs_all, ys_all, hs):
        series[hue_idx[h]][x_idx[x]] += y
    return xs, hues, series


def _area_record(args, kw):
    kw = dict(kw)
    base = kw.pop("base", 0)
    if "data" in kw or "x" in kw or "y" in kw:
        data = kw.pop("data", None)
        x_col = kw.pop("x", None)
        y_col = kw.pop("y", None)
        hue_col = kw.pop("hue", None)
        if data is None or x_col is None or y_col is None:
            raise TypeError(
                "area long-form requires data=, x=, y= (hue= optional)."
            )
        xs, hues, series = _aggregate_long_xy(data, x_col, y_col, hue_col)
    else:
        xs = to_list(args[0])
        v = to_list(args[1])
        if v and hasattr(v[0], "__iter__") and not isinstance(v[0], str):
            series = [to_list(s) for s in v]
            labels = kw.pop("labels", None)
            hues = list(labels) if labels else [None] * len(series)
        else:
            series = [v]
            hues = [None]
    return {"type": "area", "xs": xs, "hues": hues, "series": series,
            "base": base, "opts": kw}


def _area_ydomain(a):
    series = a["series"]
    base = a["base"]
    if len(series) > 1:
        sums = [sum(s[i] for s in series) for i in range(len(a["xs"]))]
        return [base + s for s in sums] + [base]
    return list(series[0]) + [base]


def _area_data_attrs(a):
    flat = [v for s in a["series"] for v in s]
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], flat))
    out["base"] = a["base"]
    curve = a["opts"].get("curve")
    if curve and curve != "linear":
        out["curve"] = curve
    return out


def _area_draw(a, ctx):
    xs = a["xs"]
    hues = a["hues"]
    series = a["series"]
    opts = a["opts"]
    palette = opts.get("palette")
    base = a["base"]
    alpha = opts.get("alpha", _D["fill_alpha"])
    curve = opts.get("curve", "linear")
    if curve not in _CURVE_VALUES:
        raise ValueError(
            f"unknown curve={curve!r}; expected one of {_CURVE_VALUES}"
        )
    multi = len(series) > 1
    out = []
    running = [base] * len(xs)
    for j, ys in enumerate(series):
        # Single-series y are absolute values; multi-series y are band heights.
        upper = [r + y for r, y in zip(running, ys)] if multi else list(ys)
        lower = list(running) if multi else [base] * len(xs)
        if curve == "linear":
            up_x, up_y = xs, upper
            lo_x, lo_y = xs, lower
        else:
            mode = curve[5:]
            up_x, up_y = _step_coords(xs, upper, mode)
            lo_x, lo_y = _step_coords(xs, lower, mode)
        pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(up_x, up_y)]
        pts += [(ctx.x_scale(x), ctx.y_scale(y))
                for x, y in zip(reversed(lo_x), reversed(lo_y))]
        col = hue_color(hues, palette, j, ctx.color) if multi else ctx.color
        out.append(draw_polygon(pts, fill=col, alpha=alpha))
        running = upper
    return "".join(out)


def _area_legend_entries(a):
    hues = a["hues"]
    opts = a["opts"]
    alpha = opts.get("alpha", _D["fill_alpha"])
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
    name="area",
    record=_area_record,
    xdomain=lambda a: a["xs"],
    ydomain=_area_ydomain,
    draw=_area_draw,
    legend_entries=_area_legend_entries,
    data_attrs=_area_data_attrs,
))
