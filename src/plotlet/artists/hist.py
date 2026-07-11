"""Histogram — binned counts of a 1-D distribution.

  c.hist(data=df, x="col")                          # long-form
  c.hist(data=df, x="col", fill="group")            # overlaid by group
  c.hist(data=df, x="col", fill="group", position="stack")

Multi-group calls share bin edges so the bars are comparable and the
positions line up.

Aesthetics:
  fill=         constant color OR column name → grouped multi-series
  color=        stroke color (constant, default None = no stroke)
  palette=      maps group levels → colors when `fill=` is a column

Binning:
  bins=10             number of bins, or an explicit edge sequence
  binwidth=           fixed bin width (instead of a count)
  binrange=(lo, hi)   span to bin over; values outside are dropped
  weights=            column name or sequence — sums weights per bin
                      instead of counting rows

Stats:
  density=False       True normalises so area under each set of bars is 1
  cumulative=False    running totals; with density=True the empirical CDF

Multi-group layout:
  position='overlay'  'stack' (bars pile up), 'fill' (100% stack), or
                      'dodge' (side-by-side within each bin);
                      histtype='bar' only

Other styling kwargs:
  histtype='bar'      'bar', 'step' (outline-only), or 'stepfilled'
  orientation='v'     'h' for horizontal bars
  alpha=<themed>      bar fill opacity
  linewidth=<themed>  stroke width (used only when color is set)
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list, resolve_aes
from ..draw import resolve_color
from .._spec import _D, _LEGSPEC
from ..draw import coord, path as draw_path, polygon as draw_polygon, rect as draw_rect
from ..utils import group_color as _group_fill


_POSITIONS = ("overlay", "stack", "fill", "dodge")


def _artist_hist(a, xs_, ys_, col, bins, warp=None):
    out = []
    opts = a["opts"]
    horizontal = opts.get("orientation") == "h"
    bin_scale, count_scale = (ys_, xs_) if horizontal else (xs_, ys_)
    base = count_scale(0)
    alpha = opts.get("alpha", _D["hist_alpha"])
    stroke = resolve_color(opts.get("color"))
    lw = opts.get("linewidth", _D["linewidth"]) if stroke else 1
    histtype = opts.get("histtype", "bar")

    if histtype == "bar":
        half_gap = _D["hist_gap"] / 2
        for b in bins:
            bp0 = bin_scale(b["x0"]); bp1 = bin_scale(b["x1"])
            bp_lo, bp_hi = min(bp0, bp1), max(bp0, bp1)
            bp_lo += half_gap; bp_hi -= half_gap
            bin_size = max(0, bp_hi - bp_lo)
            cp = count_scale(b["count"])
            count_lo, count_hi = min(base, cp), max(base, cp)
            count_size = count_hi - count_lo
            if horizontal:
                x, y, w, h = count_lo, bp_lo, count_size, bin_size
            else:
                x, y, w, h = bp_lo, count_lo, bin_size, count_size
            out.append(draw_rect(x, y, w, h, fill=col,
                                 stroke=stroke, stroke_width=lw,
                                 dash=opts.get("linestyle"), alpha=alpha,
                                 project=warp))
        return "".join(out)

    if not bins:
        return ""
    pts = [(bin_scale(bins[0]["x0"]), base)]
    for b in bins:
        cp = count_scale(b["count"])
        pts.append((bin_scale(b["x0"]), cp))
        pts.append((bin_scale(b["x1"]), cp))
    pts.append((bin_scale(bins[-1]["x1"]), base))
    if horizontal:
        pts = [(p, q) for q, p in pts]
    edge = stroke or col
    edge_w = lw if stroke else _D["linewidth"]
    fill = col if histtype == "stepfilled" else None
    if warp is None:
        d = "M" + " L".join(f"{coord(x)},{coord(y)}" for x, y in pts)
        out.append(draw_path(d + " Z", fill=fill,
                             stroke=edge, stroke_width=edge_w,
                             dash=opts.get("linestyle"), alpha=alpha))
    else:
        out.append(draw_polygon(pts, fill=fill, stroke=edge,
                                stroke_width=edge_w, alpha=alpha,
                                project=warp))
    return "".join(out)


def _long_form_1d_weighted(data, x_col, group_col, weights):
    """Like `utils.long_form_1d` but carries an optional per-row weight
    column/sequence through the grouping. Returns (groups, vals, wgts)
    where `wgts` is None when no weights were given, else shaped like
    `vals`."""
    xs = to_list(data[x_col])
    if weights is None:
        ws = None
    else:
        ws = to_list(data[weights]) if isinstance(weights, str) else to_list(weights)
        if len(ws) != len(xs):
            raise ValueError(
                f"hist: weights= has {len(ws)} values for {len(xs)} rows."
            )
    if group_col is None:
        return [None], [xs], None if ws is None else [ws]
    hs = to_list(data[group_col])
    groups = []
    for h in hs:
        if h not in groups: groups.append(h)
    vals = [[] for _ in groups]
    wgts = None if ws is None else [[] for _ in groups]
    group_idx = {h: j for j, h in enumerate(groups)}
    for i, (x, h) in enumerate(zip(xs, hs)):
        vals[group_idx[h]].append(x)
        if wgts is not None:
            wgts[group_idx[h]].append(ws[i])
    return groups, vals, wgts


def _hist_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "hist requires long-form input: "
            "c.hist(data=df, x='col')."
        )
    data_df = kw.pop("data", None)
    x_col = kw.pop("x", None)
    if data_df is None or x_col is None:
        raise TypeError(
            "hist requires data=, x= (fill= optional)."
        )
    histtype = kw.get("histtype", "bar")
    if histtype not in ("bar", "step", "stepfilled"):
        raise ValueError(
            f"hist histtype={histtype!r} — must be 'bar', 'step', or 'stepfilled'."
        )
    position = kw.pop("position", "overlay")
    if position not in _POSITIONS:
        raise ValueError(
            f"unknown position={position!r}; expected one of {_POSITIONS}."
        )
    if position != "overlay" and histtype != "bar":
        raise ValueError(
            f"hist position={position!r} needs histtype='bar' — step "
            f"outlines can't stack or dodge."
        )
    bins = kw.get("bins")
    if bins is not None and not isinstance(bins, int):
        edges = [float(e) for e in to_list(bins)]
        if len(edges) < 2 or any(b <= a for a, b in zip(edges, edges[1:])):
            raise ValueError(
                "hist bins= as a sequence must be 2+ strictly increasing "
                "bin edges."
            )
        kw["bins"] = edges
        if "binrange" in kw:
            raise TypeError(
                "hist: explicit bin edges already pin the range — drop "
                "binrange=."
            )
    if "bins" in kw and "binwidth" in kw:
        raise TypeError("hist: pass bins= or binwidth=, not both.")
    binwidth = kw.get("binwidth")
    if binwidth is not None and binwidth <= 0:
        raise ValueError(f"hist binwidth={binwidth!r} — must be positive.")
    binrange = kw.get("binrange")
    if binrange is not None:
        if len(binrange) != 2 or not binrange[0] < binrange[1]:
            raise ValueError(
                f"hist binrange={binrange!r} — must be (lo, hi) with lo < hi."
            )
    fill = kw.pop("fill", None)
    fill_kind, fill_value = resolve_aes(data_df, fill)
    group_col = fill if fill_kind == "column" else None
    weights = kw.pop("weights", None)
    groups, vals, wgts = _long_form_1d_weighted(data_df, x_col, group_col,
                                                weights)
    if fill_kind == "literal" and fill_value is not None:
        kw["_fill_literal"] = fill_value
    return {"type": "hist", "groups": groups, "vals": vals,
            "weights": wgts, "_position": position, "opts": kw}


def _bin_xs(bin_groups):
    return [v for bins in bin_groups for b in bins for v in (b["x0"], b["x1"])]


def _bin_ys(a):
    bin_groups = a.get("_bin_groups", [])
    multi = len(bin_groups) > 1
    if multi and a["_position"] == "fill":
        return [0, 1]
    if multi and a["_position"] == "stack":
        n = len(bin_groups[0])
        return [sum(g[i]["count"] for g in bin_groups)
                for i in range(n)] + [0]
    return [b["count"] for bins in bin_groups for b in bins] + [0]


def _hist_data_attrs(a):
    vals = a["vals"]
    bin_groups = a.get("_bin_groups", [])
    n = sum(len(g) for g in vals)
    out = {"n": n, "bins": (len(bin_groups[0]) if bin_groups else 0)}
    flat_bins = [b for bins in bin_groups for b in bins]
    if flat_bins:
        out["x-min"] = min(b["x0"] for b in flat_bins)
        out["x-max"] = max(b["x1"] for b in flat_bins)
        out["count-max"] = max(b["count"] for b in flat_bins)
    return out


def _hist_horizontal(a): return a["opts"].get("orientation") == "h"


def _hist_xdomain(a):
    return _bin_ys(a) if _hist_horizontal(a) else _bin_xs(a.get("_bin_groups", []))


def _hist_ydomain(a):
    return _bin_xs(a.get("_bin_groups", [])) if _hist_horizontal(a) else _bin_ys(a)


def _hist_rect_style(a):
    """Shared per-call styling for the positioned bar paths."""
    opts = a["opts"]
    return dict(alpha=opts.get("alpha", _D["hist_alpha"]),
                stroke=resolve_color(opts.get("color")),
                dash=opts.get("linestyle"))


def _hist_draw_stacked(a, ctx, bin_groups, fills, *, normalize):
    opts = a["opts"]
    horizontal = _hist_horizontal(a)
    bin_scale, count_scale = ((ctx.y_scale, ctx.x_scale) if horizontal
                              else (ctx.x_scale, ctx.y_scale))
    style = _hist_rect_style(a)
    lw = opts.get("linewidth", _D["linewidth"]) if style["stroke"] else 1
    half_gap = _D["hist_gap"] / 2
    n = len(bin_groups[0])
    totals = ([sum(g[i]["count"] for g in bin_groups) or 1 for i in range(n)]
              if normalize else None)
    running = [0.0] * n
    out = []
    for j, bins in enumerate(bin_groups):
        for i, b in enumerate(bins):
            v = b["count"] / totals[i] if normalize else b["count"]
            bp0 = bin_scale(b["x0"]); bp1 = bin_scale(b["x1"])
            bp_lo, bp_hi = min(bp0, bp1), max(bp0, bp1)
            bp_lo += half_gap; bp_hi -= half_gap
            bin_size = max(0, bp_hi - bp_lo)
            c0 = count_scale(running[i]); c1 = count_scale(running[i] + v)
            count_lo, count_hi = min(c0, c1), max(c0, c1)
            if horizontal:
                x, y, w, h = count_lo, bp_lo, count_hi - count_lo, bin_size
            else:
                x, y, w, h = bp_lo, count_lo, bin_size, count_hi - count_lo
            out.append(draw_rect(x, y, w, h, fill=fills[j],
                                 stroke=style["stroke"], stroke_width=lw,
                                 dash=style["dash"], alpha=style["alpha"],
                                 project=ctx.warp))
            running[i] += v
    return "".join(out)


def _hist_draw_dodged(a, ctx, bin_groups, fills):
    opts = a["opts"]
    horizontal = _hist_horizontal(a)
    bin_scale, count_scale = ((ctx.y_scale, ctx.x_scale) if horizontal
                              else (ctx.x_scale, ctx.y_scale))
    style = _hist_rect_style(a)
    lw = opts.get("linewidth", _D["linewidth"]) if style["stroke"] else 1
    half_gap = _D["hist_gap"] / 2
    base = count_scale(0)
    k = len(bin_groups)
    out = []
    for j, bins in enumerate(bin_groups):
        for b in bins:
            bp0 = bin_scale(b["x0"]); bp1 = bin_scale(b["x1"])
            bp_lo, bp_hi = min(bp0, bp1), max(bp0, bp1)
            bp_lo += half_gap; bp_hi -= half_gap
            slot = max(0, bp_hi - bp_lo) / k
            s_lo = bp_lo + j * slot
            cp = count_scale(b["count"])
            count_lo, count_hi = min(base, cp), max(base, cp)
            if horizontal:
                x, y, w, h = count_lo, s_lo, count_hi - count_lo, slot
            else:
                x, y, w, h = s_lo, count_lo, slot, count_hi - count_lo
            out.append(draw_rect(x, y, w, h, fill=fills[j],
                                 stroke=style["stroke"], stroke_width=lw,
                                 dash=style["dash"], alpha=style["alpha"],
                                 project=ctx.warp))
    return "".join(out)


def _hist_draw(a, ctx):
    palette = a["opts"].get("palette")
    bin_groups = a.get("_bin_groups", [])
    fill_literal = resolve_color(a["opts"].get("_fill_literal"))
    fill_fallback = fill_literal if fill_literal is not None else ctx.color
    fills = [_group_fill(a["groups"], palette, j, fill_fallback)
             for j in range(len(bin_groups))]
    position = a["_position"]
    if len(bin_groups) > 1 and position in ("stack", "fill"):
        return _hist_draw_stacked(a, ctx, bin_groups, fills,
                                  normalize=(position == "fill"))
    if len(bin_groups) > 1 and position == "dodge":
        return _hist_draw_dodged(a, ctx, bin_groups, fills)
    out = []
    for j, bins in enumerate(bin_groups):
        out.append(_artist_hist(a, ctx.x_scale, ctx.y_scale, fills[j], bins,
                                 warp=ctx.warp))
    return "".join(out)


def _hist_legend_entries(a):
    groups = a["groups"]
    opts = a["opts"]
    alpha = opts.get("alpha", _D["hist_alpha"])
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
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return draw_rect(x0, y_mid - 5, sw, 10, fill=_col, alpha=alpha)
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="hist",
    record=_hist_record,
    xdomain=_hist_xdomain,
    ydomain=_hist_ydomain,
    draw=_hist_draw,
    legend_entries=_hist_legend_entries,
    data_attrs=_hist_data_attrs,
    force_zero_y=lambda a: not _hist_horizontal(a),
    force_zero_x=_hist_horizontal,
))
