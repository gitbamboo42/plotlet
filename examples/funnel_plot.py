"""Custom artist: funnel plot (meta-analysis publication-bias check).

Scatter of per-study effect estimate (x) vs precision — usually standard
error (y, with y axis *inverted* so small-SE / high-precision studies
sit at the top, producing the characteristic funnel shape). Pseudo
confidence-interval lines fan out from the pooled estimate as the
expected ±1.96·SE envelope; missing dots in the lower corners are the
classic publication-bias signature.

This is unrelated to `sales_funnel` (the conversion / drop-off chart);
the two share a one-word name in everyday usage but solve totally
different problems.

API:
    c.funnel_plot(estimates, ses, pooled=None, z=1.96)
- `estimates` — per-study effect estimate.
- `ses`       — per-study standard error.
- `pooled`    — the meta-analytic mean (drawn as a vertical line). If
                None, uses the inverse-variance-weighted mean.
"""

SUMMARY = 'Meta-analysis funnel: effect vs standard error with ±1.96·SE envelope to spot publication bias.'

from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist
from plotlet.font import _text_path


def funnel_plot_record(args, kw):
    est = _to_pylist(args[0])
    ses = _to_pylist(args[1])
    pooled = kw.get("pooled")
    if pooled is None and est:
        # Inverse-variance-weighted mean.
        w = [1 / (s * s) for s in ses]
        pooled = sum(e * wi for e, wi in zip(est, w)) / sum(w)
    return {"type": "funnel_plot", "est": est, "ses": ses, "_pooled": pooled,
            "opts": kw}


def funnel_plot_xdomain(a):
    z = a["opts"].get("z", 1.96)
    out = list(a["est"])
    if a["_pooled"] is not None and a["ses"]:
        # Pseudo-CI fans out to ± z * max(ses) at the bottom of the funnel.
        max_se = max(a["ses"])
        out += [a["_pooled"] - z * max_se, a["_pooled"] + z * max_se]
    return out


def funnel_plot_ydomain(a):
    # SE on y; reserve a small pad above 0.
    return [0] + list(a["ses"])


def funnel_plot_draw(a, ctx):
    col = a["opts"].get("color", "#1f77b4")
    r = a["opts"].get("size", 3)
    z = a["opts"].get("z", 1.96)
    out = []
    # Pseudo confidence-interval envelope from (pooled, 0) fanning out
    # along ± z * SE as SE grows.
    if a["_pooled"] is not None and a["ses"]:
        max_se = max(a["ses"])
        x_left = a["_pooled"] - z * max_se
        x_right = a["_pooled"] + z * max_se
        # Top vertex at SE=0, bottom corners at SE=max_se.
        px_top = ctx.x_scale(a["_pooled"]); py_top = ctx.y_scale(0)
        px_l = ctx.x_scale(x_left); py_b = ctx.y_scale(max_se)
        px_r = ctx.x_scale(x_right)
        out.append(
            f'<line x1="{px_top:.2f}" x2="{px_l:.2f}" y1="{py_top:.2f}" '
            f'y2="{py_b:.2f}" stroke="#888" stroke-width="0.8" '
            f'stroke-dasharray="4,3"/>'
        )
        out.append(
            f'<line x1="{px_top:.2f}" x2="{px_r:.2f}" y1="{py_top:.2f}" '
            f'y2="{py_b:.2f}" stroke="#888" stroke-width="0.8" '
            f'stroke-dasharray="4,3"/>'
        )
        # Pooled estimate vertical line.
        out.append(
            f'<line x1="{px_top:.2f}" x2="{px_top:.2f}" y1="{py_top:.2f}" '
            f'y2="{py_b:.2f}" stroke="#444" stroke-width="0.8"/>'
        )
        out.append(_text_path(f"pooled = {a['_pooled']:.2f}",
                              px_top + 4, py_top + 11, 9, anchor="start"))
    for e, s in zip(a["est"], a["ses"]):
        out.append(
            f'<circle cx="{ctx.x_scale(e):.2f}" cy="{ctx.y_scale(s):.2f}" '
            f'r="{r}" fill="{col}" opacity="0.8"/>'
        )
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="funnel_plot",
    record=funnel_plot_record,
    xdomain=funnel_plot_xdomain,
    ydomain=funnel_plot_ydomain,
    draw=funnel_plot_draw,
    uses_color_cycle=False,
    flips_y_axis=lambda a: True,  # invert: small SE (precise) at top
))


if __name__ == "__main__":
    import random, math
    random.seed(0)
    # 30 fictitious studies estimating an effect ~0.30 with SE-dependent noise.
    estimates = []; ses = []
    for _ in range(30):
        se = random.uniform(0.05, 0.45)
        e = 0.30 + random.gauss(0, se)
        # Introduce mild publication bias: drop a few small studies with
        # large negative estimates (the missing lower-left corner signal).
        if se > 0.25 and e < 0.10 and random.random() < 0.6:
            continue
        estimates.append(e); ses.append(se)
    c = pt.chart(data_width=420, data_height=320)
    c.funnel_plot(estimates, ses)
    c.title("Funnel plot (publication-bias check)")
    c.xlabel("effect estimate").ylabel("standard error")
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
