"""Custom artist: calibration plot (reliability diagram).

For a probabilistic binary classifier, bin predictions by their predicted
probability, then plot mean predicted vs observed frequency in each bin.
A well-calibrated model traces the y = x diagonal. Used heavily for
neural net validation, weather forecasting, and any "we output 0.7 — is
that *actually* 70 % positive?" check.

API:
    c.calibration(y_true, y_score, n_bins=10, strategy="quantile")

- `strategy="quantile"` → equal-count bins (sklearn default; robust to
  imbalance).
- `strategy="uniform"`  → equal-width bins on [0, 1].
"""

SUMMARY = "Reliability diagram: predicted vs observed probability in bins; diagonal = perfect calibration."

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list


def calibration_record(args, kw):
    y_true = to_list(args[0])
    y_score = to_list(args[1])
    n_bins = kw.get("n_bins", 10)
    strategy = kw.get("strategy", "quantile")
    paired = sorted(zip(y_score, y_true), key=lambda p: p[0])
    n = len(paired)
    if n == 0:
        return {"type": "calibration", "_pred": [], "_obs": [], "_count": [],
                "opts": kw}
    bins = []
    if strategy == "quantile":
        # Split into n_bins by sample-count quantile.
        per = max(n // n_bins, 1)
        for i in range(n_bins):
            chunk = paired[i * per: (i + 1) * per if i < n_bins - 1 else n]
            if chunk:
                bins.append(chunk)
    else:
        for i in range(n_bins):
            lo = i / n_bins; hi = (i + 1) / n_bins
            chunk = [(s, t) for s, t in paired if lo <= s < hi or (i == n_bins - 1 and s == 1)]
            if chunk:
                bins.append(chunk)
    pred, obs, cnt = [], [], []
    for chunk in bins:
        ss = [s for s, _ in chunk]
        ts = [t for _, t in chunk]
        pred.append(sum(ss) / len(ss))
        obs.append(sum(ts) / len(ts))
        cnt.append(len(chunk))
    return {"type": "calibration", "_pred": pred, "_obs": obs, "_count": cnt,
            "opts": kw}


def calibration_xdomain(a): return [0, 1]
def calibration_ydomain(a): return [0, 1]


def calibration_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.6)
    out = []
    # Perfect-calibration diagonal (drawn once).
    if a["opts"].get("_first", True):
        out.append(
            f'<line x1="{ctx.x_scale(0):.2f}" y1="{ctx.y_scale(0):.2f}" '
            f'x2="{ctx.x_scale(1):.2f}" y2="{ctx.y_scale(1):.2f}" '
            f'stroke="#888" stroke-width="0.8" stroke-dasharray="4,3"/>'
        )
    pts = [(ctx.x_scale(p), ctx.y_scale(o)) for p, o in zip(a["_pred"], a["_obs"])]
    if len(pts) >= 2:
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{lw}"/>')
    # Dot per bin sized by count.
    max_cnt = max(a["_count"]) if a["_count"] else 1
    for (px, py), n in zip(pts, a["_count"]):
        r = 2 + 6 * (n / max_cnt) ** 0.5
        out.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{r:.2f}" fill="{col}"/>')
    return "".join(out)


def calibration_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    return (
        f'<line x1="{x0}" x2="{x0 + 22}" y1="{y_mid}" y2="{y_mid}" '
        f'stroke="{col}" stroke-width="1.6"/>'
        f'<circle cx="{x0 + 11}" cy="{y_mid}" r="3" fill="{col}"/>'
    )


pt.add_artist(pt.ArtistSpec(
    name="calibration",
    record=calibration_record,
    xdomain=calibration_xdomain,
    ydomain=calibration_ydomain,
    draw=calibration_draw,
    legend_swatch=calibration_legend_swatch,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    n = 4000
    # A well-calibrated model: y_score = P(y=1) ish.
    well = []
    for _ in range(n):
        p = random.random()
        y = 1 if random.random() < p else 0
        well.append((y, p))
    # A miscalibrated model: pushes scores toward extremes (overconfident).
    overconfident = [(y, min(1, max(0, 0.5 + (p - 0.5) * 1.7))) for y, p in well]
    c = pt.chart(data_width=320, data_height=320)
    c.calibration([y for y, _ in well], [p for _, p in well],
                  label="well-calibrated")
    c.calibration([y for y, _ in overconfident], [p for _, p in overconfident],
                  label="overconfident", _first=False)
    c.title("Calibration").xlabel("mean predicted").ylabel("observed fraction").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
