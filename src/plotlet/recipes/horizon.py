"""Custom artist: horizon chart.

A horizon chart compresses a wide time-series band into a short strip
by folding the y-range into N bands and stacking them with progressively
darker colors. Negative values mirror upward (or use a separate color
ramp). Widely used in dashboards for visualizing many series in
limited vertical space.

API: c.horizon(xs, ys, bands=3, base=0,
               pos_color="#1f77b4", neg_color="#d62728").
The chart's y-domain is [0, band_height], regardless of the data — the
folding compresses all y info into shaded layers.
"""

SUMMARY = 'Banded compressed time-series strip; folds large y-ranges into N progressively-shaded layers.'
from pathlib import Path

import plotlet as pt
from plotlet.draw import polygon as draw_polygon
from plotlet.utils import to_list


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(rgb, white, t):
    """Mix toward white by `t` in [0, 1] — bands get progressively lighter
    further from baseline. (We use *darker* for nearer bands; lighter for
    overflow.) Returns hex."""
    r = int(rgb[0] + (white[0] - rgb[0]) * t)
    g = int(rgb[1] + (white[1] - rgb[1]) * t)
    b = int(rgb[2] + (white[2] - rgb[2]) * t)
    return f"rgb({r},{g},{b})"


def horizon_record(args, kw):
    return {"type": "horizon", "xs": to_list(args[0]),
            "ys": to_list(args[1]), "opts": kw}


def horizon_xdomain(a): return a["xs"]
def horizon_ydomain(a):
    return [0, 1]  # data y is folded; the strip is always [0, 1]


def horizon_draw(a, ctx):
    bands = a["opts"].get("bands", 3)
    base = a["opts"].get("base", 0)
    pos = a["opts"].get("pos_color", "#1f77b4")
    neg = a["opts"].get("neg_color", "#d62728")
    deviations = [y - base for y in a["ys"]]
    band_h = max(max(deviations, default=0), -min(deviations, default=0)) / bands
    if band_h <= 0:
        return ""
    out = []
    pos_rgb = _hex_to_rgb(pos); neg_rgb = _hex_to_rgb(neg); white = (255, 255, 255)
    # Render each band as a polygon: the contribution of values in
    # [b*band_h, (b+1)*band_h] (folded into [0, band_h]) for positives;
    # symmetrically for negatives. Bands closer to baseline are
    # rendered darker (paler outside).
    for b in range(bands):
        for sign, color_rgb in ((+1, pos_rgb), (-1, neg_rgb)):
            lo = b * band_h
            hi = (b + 1) * band_h
            pts = []
            for x, d in zip(a["xs"], deviations):
                m = sign * d
                if m <= lo:
                    yfold = 0.0
                elif m >= hi:
                    yfold = 1.0
                else:
                    yfold = (m - lo) / band_h
                px = ctx.x_scale(x); py = ctx.y_scale(yfold)
                pts.append((px, py))
            # Close along the baseline.
            x_last = ctx.x_scale(a["xs"][-1])
            x_first = ctx.x_scale(a["xs"][0])
            y_base = ctx.y_scale(0)
            pts.append((x_last, y_base))
            pts.append((x_first, y_base))
            # Closer-to-baseline bands are paler; farther bands keep full
            # saturation so larger magnitudes catch the eye (standard horizon).
            fade = 1 - b / max(bands - 1, 1)
            fill = _mix(color_rgb, white, fade * 0.6)
            out.append(draw_polygon(pts, fill=fill))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="horizon",
    record=horizon_record,
    xdomain=horizon_xdomain,
    ydomain=horizon_ydomain,
    draw=horizon_draw,
    uses_color_cycle=False,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import math, random
    random.seed(7)
    xs = list(range(200))
    ys = [math.sin(x * 0.1) * (1 + 0.4 * math.sin(x * 0.03)) + random.gauss(0, 0.15)
          for x in xs]
    c = pt.chart(data_height=80, data_width=560)
    c.horizon(xs, ys, bands=3, base=0)
    c.title("Horizon chart").xlabel("t")
    c.yticks([])
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
