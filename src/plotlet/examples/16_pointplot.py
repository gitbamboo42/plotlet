"""Pointplot

Group means with confidence intervals, one series per level.
"""
import random

import plotlet as pt
from plotlet import aes

rng = random.Random(30)
weeks = ["1 wk", "2 wk", "4 wk", "8 wk"]
data = {"week": [], "score": [], "arm": []}
for arm, slope in (("control", 0.04), ("drug", 0.45)):
    for i, week in enumerate(weeks):
        for _ in range(20):
            data["week"].append(week)
            data["arm"].append(arm)
            data["score"].append(rng.gauss(5.0 + slope * i, 1.0))

c = pt.chart(data, aes(x="week", y="score", color="arm"),
             title="response over time", xlabel="timepoint",
             ylabel="score", legend=True,
             data_width=320, data_height=200)
c.xscale("category", order=weeks)
c.add_pointplot()
c.legend()

