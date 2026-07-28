"""2-D density

KDE contours layered over the raw scatter.
"""
import random

import plotlet as pt
from plotlet import aes

rng = random.Random(12)
n = 200
xs = ([rng.gauss(-1, 0.7) for _ in range(n)]
      + [rng.gauss(1.2, 1.0) for _ in range(n)])
ys = ([rng.gauss(0, 1.0) for _ in range(n)]
      + [rng.gauss(2, 0.8) for _ in range(n)])
df = {"x": xs, "y": ys}

c = pt.chart(df, aes(x="x", y="y"),
             title="2-D KDE", xlabel="x", ylabel="y",
             data_width=300, data_height=260)
c.add_scatter(size=1.2, alpha=0.25, color="#444444")
c.add_kde_2d(n_grid=40, cmap="viridis")

