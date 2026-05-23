"""OLS fit line plus Student-t confidence ribbon. ggplot2's `geom_smooth(method="lm")`.

Fits y ~ x by closed-form OLS, draws the fit line, and shades a confidence
band using the exact Student-t critical value at n - 2 degrees of freedom.
The scatter is not drawn here — overlay your own `c.scatter(xs, ys)`.

  c.regression(xs, ys)                                  # single fit
  c.regression(data=df, x="col_x", y="col_y")           # long-form
  c.regression(data=df, x=..., y=..., hue="group")      # one fit per hue

Styling kwargs:
  level=0.95     confidence level for the band
  n_grid=80      grid resolution for evaluating the band
  alpha=0.2      ribbon fill opacity
  linewidth=1.8  fit line stroke width
  label=None     legend label (single-fit only — multi-hue auto-labels)

Math:
    slope b = Σ((x - x̄)(y - ȳ)) / Σ((x - x̄)²)
    intercept a = ȳ - b·x̄
    residual σ² = SSE / (n - 2)
    se(ŷ(x)) = σ · sqrt(1/n + (x - x̄)² / Σ(x - x̄)²)
    t · se for the band, t = t_{α/2, n-2}
"""
import math

from scipy.stats import t as _t_dist

from ..registry import ArtistSpec, add_artist
from ..utils import to_list, long_form_xy, hue_color
from .._spec import _LEGSPEC
from ..draw import polygon, polyline, rect, segment


def _drop_nan_xy(xs, ys):
    out_x, out_y = [], []
    for x, y in zip(xs, ys):
        if isinstance(x, float) and math.isnan(x): continue
        if isinstance(y, float) and math.isnan(y): continue
        out_x.append(x); out_y.append(y)
    return out_x, out_y


def _fit_ols(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    xm = sum(xs) / n
    ym = sum(ys) / n
    sxx = sum((x - xm) ** 2 for x in xs) or 1e-12
    sxy = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = ym - b * xm
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    sse = sum(r * r for r in resid)
    sigma2 = sse / max(n - 2, 1)
    return a, b, xm, sxx, math.sqrt(sigma2), n


def _regression_record(args, kw):
    kw = dict(kw)
    if "data" in kw or "x" in kw or "y" in kw:
        data = kw.pop("data", None)
        x_col = kw.pop("x", None)
        y_col = kw.pop("y", None)
        hue_col = kw.pop("hue", None)
        if data is None or x_col is None or y_col is None:
            raise TypeError(
                "regression long-form requires data=, x=, y= (hue= optional)."
            )
        hues, groups = long_form_xy(data, x_col, y_col, hue_col)
    else:
        hues = [None]
        groups = [(to_list(args[0]), to_list(args[1]))]
    cleaned = [_drop_nan_xy(xs, ys) for xs, ys in groups]
    fits = [_fit_ols(xs, ys) for xs, ys in cleaned]
    return {"type": "regression", "hues": hues, "groups": cleaned,
            "fits": fits, "opts": kw}


def _regression_xdomain(a):
    return [x for xs, _ in a["groups"] for x in xs]


def _regression_ydomain(a):
    level = a["opts"].get("level", 0.95)
    out = []
    for fit, (xs, _) in zip(a["fits"], a["groups"]):
        if fit is None or not xs:
            continue
        a0, b0, _xm, _sxx, sigma, n = fit
        df = max(n - 2, 1)
        crit = _t_dist.ppf((1 + level) / 2, df)
        lo, hi = min(xs), max(xs)
        out.append(a0 + b0 * lo - crit * sigma)
        out.append(a0 + b0 * hi + crit * sigma)
    return out


def _regression_draw(a, ctx):
    palette = a["opts"].get("palette")
    fill_alpha = a["opts"].get("alpha", 0.2)
    lw = a["opts"].get("linewidth", 1.8)
    level = a["opts"].get("level", 0.95)
    n_grid = a["opts"].get("n_grid", 80)
    out = []
    for j, ((xs, _ys), fit) in enumerate(zip(a["groups"], a["fits"])):
        if fit is None or len(xs) < 3:
            continue
        col = hue_color(a["hues"], palette, j, ctx.color)
        a0, b0, xm, sxx, sigma, n = fit
        crit = _t_dist.ppf((1 + level) / 2, n - 2)
        lo, hi = min(xs), max(xs)
        grid = [lo + (hi - lo) * i / (n_grid - 1) for i in range(n_grid)]
        upper, lower, mid = [], [], []
        for x in grid:
            yhat = a0 + b0 * x
            se = sigma * math.sqrt(1 / n + (x - xm) ** 2 / sxx)
            upper.append((x, yhat + crit * se))
            lower.append((x, yhat - crit * se))
            mid.append((x, yhat))
        pts_top = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in upper]
        pts_bot = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in lower]
        band = pts_top + pts_bot[::-1]
        out.append(polygon(band, fill=col, alpha=fill_alpha))
        line_pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in mid]
        out.append(polyline(line_pts, color=col, width=lw))
    return "".join(out)


def _regression_legend_entries(a):
    hues = a["hues"]
    opts = a["opts"]
    fill_alpha = opts.get("alpha", 0.2)
    lw = opts.get("linewidth", 1.8)
    sw = _LEGSPEC["swatch_width"]
    if hues == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(_a, _ctx, x0, y_mid):
            col = _a.get("_color", _ctx.color)
            return (rect(x0, y_mid - 5, sw, 10, fill=col, alpha=fill_alpha)
                    + segment(x0, y_mid, x0 + sw, y_mid, color=col, width=lw))
        return [{"label": label, "color": None, "paint": paint}]
    palette = opts.get("palette")
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return (rect(x0, y_mid - 5, sw, 10, fill=_col, alpha=fill_alpha)
                    + segment(x0, y_mid, x0 + sw, y_mid, color=_col, width=lw))
        entries.append({"label": str(h), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="regression",
    record=_regression_record,
    xdomain=_regression_xdomain,
    ydomain=_regression_ydomain,
    draw=_regression_draw,
    legend_entries=_regression_legend_entries,
))
