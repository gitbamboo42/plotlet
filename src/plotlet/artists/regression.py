"""OLS fit line plus Student-t confidence ribbon.

Fits y ~ x by closed-form OLS, draws the fit line, and shades a confidence
band using the exact Student-t critical value at n - 2 degrees of freedom.
The scatter is not drawn here — overlay your own
`c.add_scatter(aes(x="col_x", y="col_y"))`.

  c.add_regression(aes(x="col_x", y="col_y"))           # columns via aes
  c.add_regression(aes(x=..., y=..., color="group"))    # one fit per group
  c.add_regression(aes(x=..., y=...), order=2)          # polynomial
  c.add_regression(aes(x=..., y=...), robust=True)      # Huber IRLS
  c.add_regression(aes(x=..., y=...), lowess=True)      # LOWESS smoother

Styling kwargs:
  color=         bare → literal line color; aes(color="col") → one fit
                 per level
  palette=       maps levels → colors when color is mapped in aes
  order=1        polynomial degree of the fit (seaborn regplot order=);
                 the band generalizes to t_{α/2, n-p} with the full
                 covariance term  se(ŷ) = σ·sqrt(xᵀ(XᵀX)⁻¹x)
  robust=False   True → Huber-weighted IRLS fit that downweights
                 outliers (seaborn regplot robust=). No analytic band
                 exists, so the ribbon comes from a percentile bootstrap
                 (n_boot=200, seed=0 — deterministic)
  lowess=False   True → LOWESS local-linear smoother (seaborn regplot
                 lowess=, ggplot geom_smooth method="loess"). Draws the
                 smoothed line only — like seaborn, no confidence band.
                 Incompatible with order=/robust=.
  frac=2/3       LOWESS window: fraction of points in each local fit
                 (statsmodels frac=; ggplot calls it span=)
  it=3           LOWESS robustifying iterations (bisquare-downweight
                 outliers, statsmodels it=); 0 = plain single pass
  level=0.95     confidence level for the band
  n_grid=80      grid resolution for evaluating the band
  n_boot=200     bootstrap resamples for the robust band
  seed=0         RNG seed for the robust bootstrap
  alpha=0.2      ribbon fill opacity
  linewidth=1.8  fit line stroke width
  label=None     legend label (single-fit only — multi-group auto-labels)

Math (order=1, robust=False — the closed-form fast path):
    slope b = Σ((x - x̄)(y - ȳ)) / Σ((x - x̄)²)
    intercept a = ȳ - b·x̄
    residual σ² = SSE / (n - 2)
    se(ŷ(x)) = σ · sqrt(1/n + (x - x̄)² / Σ(x - x̄)²)
    t · se for the band, t = t_{α/2, n-2}

Polynomial/robust fits solve the normal equations on centered x
(conditioning); Huber uses c=1.345 with MAD scale, IRLS to convergence.
LOWESS is Cleveland's classic: per evaluation point, a degree-1 fit over
the `frac`-nearest neighbours with tricube distance weights, then `it`
rounds of bisquare residual downweighting. O(n·frac) work per point —
for very large n, lower `frac` or subsample first.
"""
import bisect
import math
import random

from scipy.stats import t as _t_dist

from ..registry import ArtistSpec, add_artist
from ..utils import long_form_xy, resolve_aes, quantile, pack_opts
from ..draw import resolve_color
from .._spec import _LEGSPEC
from ..draw import polygon, polyline, rect, segment
from ..utils import group_color as _group_color


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


# --- generic path: polynomial order and/or Huber-robust fits ---------------

def _solve(A, b):
    """Solve A·x = b by Gaussian elimination with partial pivoting.
    A is a small p×p normal-equations matrix (p = order + 1)."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[piv] = M[piv], M[col]
        if abs(M[col][col]) < 1e-12:
            M[col][col] = 1e-12  # degenerate design (e.g. constant x)
        for r in range(col + 1, n):
            f = M[r][col] / M[col][col]
            for k in range(col, n + 1):
                M[r][k] -= f * M[col][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = M[r][n] - sum(M[r][k] * x[k] for k in range(r + 1, n))
        x[r] = s / M[r][r]
    return x


def _peval(beta, t):
    """Evaluate the polynomial Σ beta[k]·t^k (Horner)."""
    v = 0.0
    for b in reversed(beta):
        v = v * t + b
    return v


def _wls(ts, ys, order, weights):
    """Weighted least squares on centered x. Returns `(beta, XtX)` where
    `XtX` is the (weighted) normal-equations matrix — callers invert it
    for the covariance term."""
    n = len(ts)
    p = order + 1
    w = weights if weights is not None else [1.0] * n
    rows = [[t ** k for k in range(p)] for t in ts]
    XtX = [[sum(w[i] * rows[i][a] * rows[i][b] for i in range(n))
            for b in range(p)] for a in range(p)]
    Xty = [sum(w[i] * rows[i][a] * ys[i] for i in range(n)) for a in range(p)]
    return _solve(XtX, Xty), XtX


def _mat_inv(A):
    """Invert a small matrix by solving against identity columns."""
    n = len(A)
    cols = [_solve(A, [1.0 if r == c else 0.0 for r in range(n)])
            for c in range(n)]
    return [[cols[c][r] for c in range(n)] for r in range(n)]


def _huber_fit(ts, ys, order, *, c=1.345, max_iter=30):
    """Huber IRLS: reweight residuals beyond c·s (s = MAD scale) until
    the coefficients stop moving."""
    beta, _ = _wls(ts, ys, order, None)
    for _ in range(max_iter):
        resid = [y - _peval(beta, t) for t, y in zip(ts, ys)]
        s = quantile([abs(r) for r in resid], 0.5) / 0.6745
        if s <= 1e-12:
            break
        w = [1.0 if abs(r) <= c * s else c * s / abs(r) for r in resid]
        new, _ = _wls(ts, ys, order, w)
        moved = max(abs(nb - ob) for nb, ob in zip(new, beta))
        beta = new
        if moved < 1e-9 * (1 + max(abs(v) for v in beta)):
            break
    return beta


def _fit_generic(xs, ys, order=1, robust=False, level=0.95, n_grid=80,
                 n_boot=200, seed=0):
    """Polynomial / robust fit evaluated on the band grid at record time.
    Returns `{"grid", "mid", "lo", "hi"}` in data space, or None when the
    group is too small (needs n ≥ order + 2 for one residual df)."""
    n = len(xs)
    p = order + 1
    if n < p + 1:
        return None
    xm = sum(xs) / n
    ts = [x - xm for x in xs]
    lo_x, hi_x = min(xs), max(xs)
    grid = [lo_x + (hi_x - lo_x) * i / (n_grid - 1) for i in range(n_grid)]
    if robust:
        beta = _huber_fit(ts, ys, order)
        mid = [_peval(beta, g - xm) for g in grid]
        rng = random.Random(seed)
        curves = []
        for _ in range(n_boot):
            idx = [rng.randrange(n) for _ in range(n)]
            bb = _huber_fit([ts[i] for i in idx], [ys[i] for i in idx],
                            order, max_iter=10)
            curves.append([_peval(bb, g - xm) for g in grid])
        a2 = (1 - level) / 2
        lo = [quantile([c[i] for c in curves], a2) for i in range(n_grid)]
        hi = [quantile([c[i] for c in curves], 1 - a2) for i in range(n_grid)]
        return {"grid": grid, "mid": mid, "lo": lo, "hi": hi}
    beta, XtX = _wls(ts, ys, order, None)
    inv = _mat_inv(XtX)
    resid = [y - _peval(beta, t) for t, y in zip(ts, ys)]
    sigma = math.sqrt(sum(r * r for r in resid) / (n - p))
    crit = _t_dist.ppf((1 + level) / 2, n - p)
    mid, lo, hi = [], [], []
    for g in grid:
        t = g - xm
        row = [t ** k for k in range(p)]
        var = sum(row[a] * inv[a][b] * row[b]
                  for a in range(p) for b in range(p))
        yhat = _peval(beta, t)
        se = sigma * math.sqrt(max(var, 0.0))
        mid.append(yhat)
        lo.append(yhat - crit * se)
        hi.append(yhat + crit * se)
    return {"grid": grid, "mid": mid, "lo": lo, "hi": hi}


# --- LOWESS path: Cleveland local-linear smoother -------------------------

def _lowess_window(xs_sorted, g, k):
    """Index range [lo, lo+k) of the k x-values nearest to `g` in a sorted
    list. Two-pointer walk: start at the insertion point and grow toward
    whichever side is closer."""
    n = len(xs_sorted)
    lo = bisect.bisect_left(xs_sorted, g)
    lo = max(0, min(lo, n - 1))
    hi = lo + 1
    while hi - lo < k:
        if lo == 0:
            hi += 1
        elif hi == n:
            lo -= 1
        elif g - xs_sorted[lo - 1] <= xs_sorted[hi] - g:
            lo -= 1
        else:
            hi += 1
    return lo, hi


def _lowess_at(xs_sorted, ys_sorted, rob, g, k):
    """Tricube-weighted degree-1 fit over the k nearest points, evaluated
    at `g`. `rob` carries the bisquare robustness weights (all 1.0 on the
    first pass)."""
    lo, hi = _lowess_window(xs_sorted, g, k)
    xw = xs_sorted[lo:hi]
    yw = ys_sorted[lo:hi]
    h = max(g - xw[0], xw[-1] - g)
    if h <= 0:
        # All window x's coincide with g — weighted mean.
        wsum = sum(rob[lo:hi]) or 1e-12
        return sum(r * y for r, y in zip(rob[lo:hi], yw)) / wsum
    w = []
    for x, r in zip(xw, rob[lo:hi]):
        u = abs(x - g) / h
        w.append(r * (1 - u ** 3) ** 3 if u < 1 else 0.0)
    if sum(w) <= 1e-12:
        return sum(yw) / len(yw)
    ts = [x - g for x in xw]
    beta, _ = _wls(ts, yw, 1, w)
    return beta[0]


def _fit_lowess(xs, ys, frac=2 / 3, it=3, n_grid=80):
    """LOWESS evaluated on the band grid at record time. Returns
    `{"grid", "mid"}` (no band — none exists analytically), or None when
    the group is too small."""
    if not 0 < frac <= 1:
        raise ValueError(f"regression: frac={frac!r} — must be in (0, 1].")
    n = len(xs)
    if n < 3:
        return None
    pairs = sorted(zip(xs, ys))
    xs_s = [p[0] for p in pairs]
    ys_s = [p[1] for p in pairs]
    k = max(2, min(n, int(math.ceil(frac * n))))
    rob = [1.0] * n
    for _ in range(max(0, it)):
        resid = [y - _lowess_at(xs_s, ys_s, rob, x, k)
                 for x, y in zip(xs_s, ys_s)]
        s = quantile([abs(r) for r in resid], 0.5)
        if s <= 1e-12:
            break
        rob = [(1 - (r / (6 * s)) ** 2) ** 2 if abs(r) < 6 * s else 0.0
               for r in resid]
    lo_x, hi_x = xs_s[0], xs_s[-1]
    grid = [lo_x + (hi_x - lo_x) * i / (n_grid - 1) for i in range(n_grid)]
    mid = [_lowess_at(xs_s, ys_s, rob, g, k) for g in grid]
    return {"grid": grid, "mid": mid}


def _regression_record(data=None,
                       # input & fitting — consumed here at record
                       x=None, y=None, color=None,
                       order=1, robust=False, frac=2 / 3, it=3,
                       n_boot=200, seed=0,
                       # `lowess` gates the record-time fit AND tells the
                       # legend to drop the band swatch; `level`/`n_grid`
                       # feed the record-time generic fits AND the OLS
                       # band evaluated at draw — all three are packed.
                       lowess=None, level=0.95, n_grid=80,
                       # style — packed into opts for the draw/legend side
                       alpha=None, linewidth=None, palette=None,
                       label=None, legend=None):
    if data is None or x is None or y is None:
        raise TypeError(
            "regression requires data=, x=, y= (color= optional)."
        )
    color_kind, color_value = resolve_aes(data, color)
    group_col = color if color_kind == "column" else None
    groups, xy = long_form_xy(data, x, y, group_col)
    opts = pack_opts(lowess=lowess, level=level, n_grid=n_grid,
                     alpha=alpha, linewidth=linewidth, palette=palette,
                     label=label, legend=legend)
    if color_kind == "literal" and color_value is not None:
        opts["_color_literal"] = color_value
    if not isinstance(order, int) or order < 1:
        raise ValueError(f"regression: order={order!r} — must be an int ≥ 1.")
    cleaned = [_drop_nan_xy(xs, ys) for xs, ys in xy]
    if lowess:
        if order > 1 or robust:
            raise TypeError(
                "regression: lowess=True is a nonparametric smoother — "
                "order= and robust= don't apply."
            )
        fits = [_fit_lowess(xs, ys, frac, it, n_grid) for xs, ys in cleaned]
        return {"type": "regression", "groups": groups, "xy": cleaned,
                "fits": fits, "_generic": True, "opts": opts}
    if order > 1 or robust:
        fits = [_fit_generic(xs, ys, order, robust, level, n_grid,
                             n_boot, seed) for xs, ys in cleaned]
        return {"type": "regression", "groups": groups, "xy": cleaned,
                "fits": fits, "_generic": True, "opts": opts}
    fits = [_fit_ols(xs, ys) for xs, ys in cleaned]
    return {"type": "regression", "groups": groups, "xy": cleaned,
            "fits": fits, "opts": opts}


def _regression_xdomain(a):
    return [x for xs, _ in a["xy"] for x in xs]


def _regression_ydomain(a):
    if a.get("_generic"):
        out = []
        for fit in a["fits"]:
            if fit is None:
                continue
            if "lo" in fit:
                out.append(min(fit["lo"]))
                out.append(max(fit["hi"]))
            else:
                out.append(min(fit["mid"]))
                out.append(max(fit["mid"]))
        return out
    level = a["opts"].get("level", 0.95)
    out = []
    for fit, (xs, _) in zip(a["fits"], a["xy"]):
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
    color_literal = resolve_color(a["opts"].get("_color_literal"))
    fallback = color_literal if color_literal is not None else ctx.color
    out = []
    if a.get("_generic"):
        for j, fit in enumerate(a["fits"]):
            if fit is None:
                continue
            col = _group_color(a["groups"], palette, j, fallback)
            if "lo" in fit:
                pts_top = [(ctx.x_scale(x), ctx.y_scale(y))
                           for x, y in zip(fit["grid"], fit["hi"])]
                pts_bot = [(ctx.x_scale(x), ctx.y_scale(y))
                           for x, y in zip(fit["grid"], fit["lo"])]
                out.append(polygon(pts_top + pts_bot[::-1], fill=col,
                                   alpha=fill_alpha, project=ctx.warp))
            line_pts = [(ctx.x_scale(x), ctx.y_scale(y))
                        for x, y in zip(fit["grid"], fit["mid"])]
            out.append(polyline(line_pts, color=col, width=lw,
                                project=ctx.warp))
        return "".join(out)
    for j, ((xs, _ys), fit) in enumerate(zip(a["xy"], a["fits"])):
        if fit is None or len(xs) < 3:
            continue
        col = _group_color(a["groups"], palette, j, fallback)
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
        out.append(polygon(band, fill=col, alpha=fill_alpha, project=ctx.warp))
        line_pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in mid]
        out.append(polyline(line_pts, color=col, width=lw, project=ctx.warp))
    return "".join(out)


def _regression_legend_entries(a):
    groups = a["groups"]
    opts = a["opts"]
    fill_alpha = opts.get("alpha", 0.2)
    lw = opts.get("linewidth", 1.8)
    sw = _LEGSPEC["swatch_width"]
    has_band = not opts.get("lowess", False)
    if groups == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(_a, _ctx, x0, y_mid):
            col = _a.get("_color", _ctx.color)
            band = (rect(x0, y_mid - 5, sw, 10, fill=col, alpha=fill_alpha)
                    if has_band else "")
            return band + segment(x0, y_mid, x0 + sw, y_mid, color=col, width=lw)
        return [{"label": label, "color": None, "paint": paint}]
    palette = opts.get("palette")
    entries = []
    for j, g in enumerate(groups):
        col = _group_color(groups, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            band = (rect(x0, y_mid - 5, sw, 10, fill=_col, alpha=fill_alpha)
                    if has_band else "")
            return band + segment(x0, y_mid, x0 + sw, y_mid, color=_col, width=lw)
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="regression",
    record=_regression_record,
    xdomain=_regression_xdomain,
    ydomain=_regression_ydomain,
    draw=_regression_draw,
    legend_entries=_regression_legend_entries,
))
