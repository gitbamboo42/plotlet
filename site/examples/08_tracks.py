"""Stacked tracks with sectors

Named, length-weighted partitions of a shared x-axis -- the layout
underneath genome-browser and phase-plot figures. Both tracks share
x and the sector chrome.
"""
import random

import plotlet as pt
from plotlet import aes

rng = random.Random(4)
regions = {"region A": 100, "region B": 500, "region C": 200}

pts = {"region": [], "pos": [], "score": []}
for name, length in regions.items():
    for _ in range(14):
        pts["region"].append(name)
        pts["pos"].append(rng.uniform(0, length))
        pts["score"].append(rng.uniform(0.1, 0.9))

steps = {"region": [], "pos": [], "cov": []}
for name, length in regions.items():
    for i in range(24):
        steps["region"].append(name)
        steps["pos"].append(length * i / 23)
        steps["cov"].append(0.5 + 0.3 * rng.uniform(-1, 1))

t1 = pt.chart(pts, aes(x="pos", y="score"),
              data_width=480, data_height=80, ylabel="score", ylim=(0, 1))
t1.add_scatter(size=3, color="#534AB7")

t2 = pt.chart(steps, aes(x="pos", y="cov", group="region"),
              data_width=480, data_height=80, ylabel="coverage",
              ylim=(0, 1))
t2.add_line(color="#1D9E75")
t2.add_axhline(0.5, color="#888888", linestyle="--")

c = (pt.grid([[t1], [t2]])
       .share_x("col")
       .sectors(regions, column="region"))
