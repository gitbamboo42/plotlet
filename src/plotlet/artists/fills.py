"""Filled-region artists over x/y series.

`fill_between(xs, y1, y2)` fills between two curves (wide-form). `area`
is long-form only: each row contributes y at x, optionally grouped by
the `fill=` column for stacked areas.

  c.fill_between(xs, y1, y2, fill="C0")                       # wide-form
  c.area(data=df, x="x", y="y")                               # single
  c.area(data=df, x="x", y="y", fill="series")                # stacked
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list, resolve_aes, palette_color
from ..draw import TAB10, resolve_color
from .._spec import _D, _LEGSPEC
from ..draw import polygon as draw_polygon, rect as draw_rect
from ._shared import (_xy_minmax, _line_legend_entries,
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


def _fill_between_record(args, kw):
    kw = dict(kw)
    if "color" in kw:
        raise TypeError(
            "fill_between: use `fill=` for the interior color, not `color=`."
        )
    if "fill" in kw:
        kw["_fill_literal"] = kw.pop("fill")
    if "data" in kw or "x" in kw or "y1" in kw or "y2" in kw:
        data = kw.pop("data", None)
        x = kw.pop("x", None)
        y1 = kw.pop("y1", None)
        y2 = kw.pop("y2", None)
        if data is None or x is None or y1 is None or y2 is None:
            raise TypeError(
                "fill_between long-form requires data=, x=, y1=, y2= "
                "(or pass positional xs, y1s, y2s)."
            )
        return {"type": "fill_between",
                "xs": to_list(data[x]), "y1": to_list(data[y1]),
                "y2": to_list(data[y2]), "opts": kw}
    return {"type": "fill_between",
            "xs": to_list(args[0]), "y1": to_list(args[1]),
            "y2": to_list(args[2]), "opts": kw}


add_artist(ArtistSpec(
    name="fill_between",
    record=_fill_between_record,
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: list(a["y1"]) + list(a["y2"]),
    draw=lambda a, ctx: _artist_fill_between(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_line_legend_entries,
    data_attrs=_fill_between_data_attrs,
))


# --- area ---

def _aggregate_long_xy(data, x_col, y_col, group_col):
    """Long-form table -> (xs, groups, series). series[j][i] sums y over
    rows where x == xs[i] and the grouping value == groups[j]."""
    xs_all = to_list(data[x_col])
    ys_all = to_list(data[y_col])
    gs = to_list(data[group_col]) if group_col is not None else [None] * len(xs_all)
    xs, groups = [], []
    for x in xs_all:
        if x not in xs: xs.append(x)
    for g in gs:
        if g not in groups: groups.append(g)
    if not groups: groups = [None]
    series = [[0] * len(xs) for _ in groups]
    x_idx = {x: i for i, x in enumerate(xs)}
    group_idx = {g: j for j, g in enumerate(groups)}
    for x, y, g in zip(xs_all, ys_all, gs):
        series[group_idx[g]][x_idx[x]] += y
    return xs, groups, series


def _area_record(args, kw):
    kw = dict(kw)
    base = kw.pop("base", 0)
    if args:
        raise TypeError(
            "area requires long-form input: "
            "c.area(data=df, x='col', y='col', fill='col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    if data is None or x_col is None or y_col is None:
        raise TypeError(
            "area requires data=, x=, y= (fill= optional)."
        )
    fill = kw.pop("fill", None)
    fill_kind, fill_value = resolve_aes(data, fill)
    group_col = fill if fill_kind == "column" else None
    xs, groups, series = _aggregate_long_xy(data, x_col, y_col, group_col)
    if fill_kind == "literal" and fill_value is not None:
        kw["_fill_literal"] = fill_value
    return {"type": "area", "xs": xs, "groups": groups, "series": series,
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


def _group_fill(groups, palette, j, fallback):
    if groups == [None]:
        return fallback
    return palette_color(palette, groups[j], j) or TAB10[j % 10]


def _area_draw(a, ctx):
    xs = a["xs"]
    groups = a["groups"]
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
    fill_literal = resolve_color(opts.get("_fill_literal"))
    fill_fallback = fill_literal if fill_literal is not None else ctx.color
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
        col = _group_fill(groups, palette, j, fill_fallback) if multi else fill_fallback
        out.append(draw_polygon(pts, fill=col, alpha=alpha))
        running = upper
    return "".join(out)


def _area_legend_entries(a):
    groups = a["groups"]
    opts = a["opts"]
    alpha = opts.get("alpha", _D["fill_alpha"])
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
    name="area",
    record=_area_record,
    xdomain=lambda a: a["xs"],
    ydomain=_area_ydomain,
    draw=_area_draw,
    legend_entries=_area_legend_entries,
    data_attrs=_area_data_attrs,
))
