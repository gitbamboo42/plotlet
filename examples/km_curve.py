"""Custom artist: Kaplan-Meier survival curve.

Step-down survival function S(t) with tick marks at censored times.
Each call adds one group; overlay multiple for treatment-vs-control
plots. Greenwood-formula 95 % CI bands are drawn around each curve
(log-log-transformed so the bounds stay in [0, 1]).

For two-group comparisons, an optional companion helper
`logrank_pvalue(t1, e1, t2, e2)` computes the standard log-rank
chi-squared statistic and its p-value using `scipy.stats.chi2`.

API:
    c.km(times, events, ci=True, level=0.95)
- `times`  -> follow-up duration (>= 0) per subject.
- `events` -> 1 if event observed, 0 if censored.
- `ci`     -> draw a Greenwood CI band (default True).
- `level`  -> confidence level for the band.
"""

SUMMARY = "Kaplan-Meier survival + Greenwood CI band; log-rank helper for two-group comparison."

import math
from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist
from scipy.stats import chi2, norm


def _km_path(times, events):
    """Compute step times, S(t), the variance term for Greenwood, and
    the censoring marks for one group."""
    pairs = sorted(zip(times, events), key=lambda x: x[0])
    s = 1.0
    cum_var = 0.0  # running sum of d_i / (n_i * (n_i - d_i)) for Greenwood
    step_t = [0.0]; step_s = [1.0]; step_var = [0.0]
    censored = []
    by_time = {}
    for t, e in pairs:
        by_time.setdefault(t, []).append(e)
    cur_risk = len(pairs)
    for t in sorted(by_time):
        events_here = sum(by_time[t])
        cens_here = len(by_time[t]) - events_here
        if events_here > 0 and cur_risk > 0:
            s *= 1 - events_here / cur_risk
            denom = cur_risk * (cur_risk - events_here)
            if denom > 0:
                cum_var += events_here / denom
            step_t.append(t); step_s.append(s); step_var.append(cum_var)
        if cens_here > 0:
            for _ in range(cens_here):
                censored.append((t, s))
        cur_risk -= len(by_time[t])
    return step_t, step_s, step_var, censored


def km_record(args, kw):
    times = _to_pylist(args[0])
    events = _to_pylist(args[1])
    t, s, var, cens = _km_path(times, events)
    return {"type": "km", "_t": t, "_s": s, "_var": var, "_cens": cens,
            "opts": kw}


def km_xdomain(a): return a["_t"]
def km_ydomain(a): return [0, 1]


def _greenwood_loglog_ci(s, cum_var, z):
    """Greenwood log-log-transformed CI for S at one time point."""
    if s <= 0 or s >= 1:
        return s, s
    log_s = math.log(s)
    # Var(log S) ≈ cum_var; Var(log(-log S)) ≈ cum_var / log_s^2.
    var_loglog = cum_var / (log_s * log_s)
    se = math.sqrt(max(var_loglog, 0))
    # CI on log(-log S): center ± z*se. Back-transform.
    lo_loglog = math.log(-log_s) - z * se
    hi_loglog = math.log(-log_s) + z * se
    return math.exp(-math.exp(hi_loglog)), math.exp(-math.exp(lo_loglog))


def km_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.6)
    show_ci = a["opts"].get("ci", True)
    level = a["opts"].get("level", 0.95)
    z = float(norm.ppf((1 + level) / 2))
    out = []
    if not a["_t"]:
        return ""
    # --- CI band (drawn before the curve so it sits behind) ---
    if show_ci and len(a["_t"]) > 1:
        # Build a step-shaped upper and lower path.
        upper = []; lower = []
        for i, (t, s, v) in enumerate(zip(a["_t"], a["_s"], a["_var"])):
            lo, hi = _greenwood_loglog_ci(s, v, z)
            if i > 0:
                prev_lo, prev_hi = _greenwood_loglog_ci(
                    a["_s"][i - 1], a["_var"][i - 1], z)
                # Horizontal hold then vertical drop.
                upper.append((ctx.x_scale(t), ctx.y_scale(prev_hi)))
                lower.append((ctx.x_scale(t), ctx.y_scale(prev_lo)))
            upper.append((ctx.x_scale(t), ctx.y_scale(hi)))
            lower.append((ctx.x_scale(t), ctx.y_scale(lo)))
        # Extend final segment.
        last_t = a["_t"][-1]
        last_lo, last_hi = _greenwood_loglog_ci(a["_s"][-1], a["_var"][-1], z)
        upper.append((ctx.x_scale(last_t), ctx.y_scale(last_hi)))
        lower.append((ctx.x_scale(last_t), ctx.y_scale(last_lo)))
        band = upper + lower[::-1]
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in band) + " Z"
        out.append(f'<path d="{d}" fill="{col}" fill-opacity="0.18"/>')
    # --- main step-after curve ---
    pts = []
    for i, (t, s) in enumerate(zip(a["_t"], a["_s"])):
        if i > 0:
            prev_s = a["_s"][i - 1]
            pts.append((ctx.x_scale(t), ctx.y_scale(prev_s)))
        pts.append((ctx.x_scale(t), ctx.y_scale(s)))
    pts.append((ctx.x_scale(a["_t"][-1]), ctx.y_scale(a["_s"][-1])))
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{lw}"/>')
    # --- censoring ticks ---
    for t, s in a["_cens"]:
        px = ctx.x_scale(t); py = ctx.y_scale(s)
        out.append(
            f'<line x1="{px:.2f}" x2="{px:.2f}" y1="{py - 4:.2f}" y2="{py + 4:.2f}" '
            f'stroke="{col}" stroke-width="{lw}"/>'
        )
    return "".join(out)


def km_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    return (f'<line x1="{x0}" x2="{x0 + 22}" y1="{y_mid}" y2="{y_mid}" '
            f'stroke="{col}" stroke-width="1.6"/>')


pt.add_artist(pt.ArtistSpec(
    name="km",
    record=km_record,
    xdomain=km_xdomain,
    ydomain=km_ydomain,
    draw=km_draw,
    legend_swatch=km_legend_swatch,
))


def logrank_pvalue(t1, e1, t2, e2):
    """Two-sample log-rank test. Returns (chi-square statistic, p-value)."""
    # Pool unique event times.
    all_times = sorted({*[t for t, e in zip(t1, e1) if e == 1],
                        *[t for t, e in zip(t2, e2) if e == 1]})
    o_minus_e = 0.0; v = 0.0
    for t in all_times:
        n1 = sum(1 for ti in t1 if ti >= t)
        n2 = sum(1 for ti in t2 if ti >= t)
        d1 = sum(1 for ti, ei in zip(t1, e1) if ti == t and ei == 1)
        d2 = sum(1 for ti, ei in zip(t2, e2) if ti == t and ei == 1)
        n = n1 + n2; d = d1 + d2
        if n <= 1 or d == 0:
            continue
        e1_exp = d * n1 / n
        o_minus_e += d1 - e1_exp
        v += (n1 * n2 * d * (n - d)) / (n * n * (n - 1))
    if v <= 0:
        return 0.0, 1.0
    chi_sq = (o_minus_e ** 2) / v
    p = 1 - chi2.cdf(chi_sq, df=1)
    return chi_sq, float(p)


if __name__ == "__main__":
    import random
    random.seed(6)

    def simulate(rate, n=80, max_t=60):
        ts, es = [], []
        for _ in range(n):
            event_t = random.expovariate(rate)
            cens_t = random.uniform(20, max_t)
            t = min(event_t, cens_t)
            e = 1 if event_t <= cens_t else 0
            ts.append(t); es.append(e)
        return ts, es

    t1, e1 = simulate(rate=0.04)
    t2, e2 = simulate(rate=0.08)
    chi_sq, p_val = logrank_pvalue(t1, e1, t2, e2)
    c = pt.chart()
    c.km(t1, e1, label="treatment")
    c.km(t2, e2, label="control")
    c.title(f"Kaplan-Meier survival (log-rank χ²={chi_sq:.2f}, p={p_val:.4f})")
    c.xlabel("months").ylabel("S(t)").legend(True)
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
