"""Hexbin

Hexagonal binning for dense point clouds, with the count legend as
its own layout cell.
"""
import random

import plotlet as pt
from plotlet import aes

rng = random.Random(13)
xs = [rng.gauss(0, 1) + rng.gauss(0, 0.4) for _ in range(3000)]
df = {"x": xs, "y": [x + rng.gauss(0, 1) for x in xs]}

hexes = pt.chart(df, aes(x="x", y="y"),
                 title="3000 points, binned", xlabel="x", ylabel="y",
                 data_width=300, data_height=260)
hexes.add_hexbin(gridsize=22)

c = hexes | pt.legend(hexes)
