"""Circle demo — circular and linear layouts from the same shared data.

Four artist types per layout: scatter, line+fill_between, numeric_bar, hist.
All use standard plotlet artists; the circular layout maps them through
_warp_svg without any custom artist code.

Run from the repo root:
    python cookbook/circle/demo.py
"""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import plotlet as pt
import plotlet.extensions.numeric_bar  # noqa — registers numeric_bar
from coordinate import CircularCoordinate
from layout import circular

random.seed(11)


def _clamp01(v):
    return max(0.0, min(1.0, v))


# ---------------------------------------------------------------------------
# Shared data
# ---------------------------------------------------------------------------

N_LINE = 80
line_ts = [i / N_LINE for i in range(N_LINE + 1)]
line_v  = [_clamp01(0.5 + 0.35 * math.sin(2 * math.pi * t)) for t in line_ts]
band_lo = [_clamp01(v - 0.08) for v in line_v]
band_hi = [_clamp01(v + 0.08) for v in line_v]

scatter_t = [random.random() for _ in range(120)]
scatter_v = [_clamp01(0.5 + 0.4 * math.sin(2 * math.pi * t)
                      + random.gauss(0, 0.06))
             for t in scatter_t]

N_BAR = 48
bar_t = [(i + 0.5) / N_BAR for i in range(N_BAR)]
bar_v = [_clamp01(0.3 + 0.5 * abs(math.sin(2 * math.pi * t))) for t in bar_t]

hist_samples = [_clamp01(random.gauss(0.5, 0.15)) for _ in range(500)]

# ---------------------------------------------------------------------------
# Circular layout — four rings
# ---------------------------------------------------------------------------

c1 = pt.chart(xlim=(0, 1), ylim=(0, 1))
c1.scatter(data={"x": scatter_t, "y": scatter_v}, x="x", y="y",
           color="#534AB7", size=3, alpha=0.55)

c2 = pt.chart(xlim=(0, 1), ylim=(0, 1))
c2.fill_between(data={"x": line_ts, "lo": band_lo, "hi": band_hi},
                x="x", y1="lo", y2="hi", fill="#1D9E75", alpha=0.25)
c2.line(data={"x": line_ts, "y": line_v}, x="x", y="y",
        color="#1D9E75", width=1.5)

c3 = pt.chart(xlim=(0, 1), ylim=(0, 1))
c3.numeric_bar(data={"x": bar_t, "y": bar_v}, x="x", y="y",
               width=0.014, color="#D9534F", alpha=0.85)

c4 = pt.chart(xlim=(0, 1), ylim=(0, 60))
c4.hist(data={"v": hist_samples}, x="v", bins=24, color="#E0A030", alpha=0.85)

circle_panel = circular([c1, c2, c3, c4], width=500, height=500)

# ---------------------------------------------------------------------------
# Linear layout — same data, standard grid for comparison
# ---------------------------------------------------------------------------

p1 = pt.chart(ylabel="scatter", xlim=(0, 1), ylim=(0, 1),
              data_width=400, data_height=110)
p1.scatter(data={"x": scatter_t, "y": scatter_v}, x="x", y="y",
           color="#534AB7", size=4, alpha=0.55)

p2 = pt.chart(ylabel="line+band", xlim=(0, 1), ylim=(0, 1),
              data_width=400, data_height=110)
p2.fill_between(data={"x": line_ts, "lo": band_lo, "hi": band_hi},
                x="x", y1="lo", y2="hi", fill="#1D9E75", alpha=0.25)
p2.line(data={"x": line_ts, "y": line_v}, x="x", y="y",
        color="#1D9E75", width=1.5)

p3 = pt.chart(ylabel="bar", xlim=(0, 1), ylim=(0, 1),
              data_width=400, data_height=110)
p3.numeric_bar(data={"x": bar_t, "y": bar_v}, x="x", y="y",
               width=0.014, color="#D9534F", alpha=0.85)

p4 = pt.chart(ylabel="hist", xlabel="t", xlim=(0, 1),
              data_width=400, data_height=110)
p4.hist(data={"v": hist_samples}, x="v", bins=24, color="#E0A030", alpha=0.85)

linear_panel = pt.grid([[p1], [p2], [p3], [p4]]).share_x("col")

# ---------------------------------------------------------------------------
# Side-by-side composition — circular panel | linear grid
# ---------------------------------------------------------------------------

(circle_panel | linear_panel).save_svg("cookbook/circle/output/combined.svg")
print("wrote output/combined.svg")
