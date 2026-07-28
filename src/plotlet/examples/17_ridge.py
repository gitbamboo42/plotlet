"""Ridge

Overlapping densities, one row per category.
"""
import random

import plotlet as pt
from plotlet import aes

rng = random.Random(15)
months = ["Jan", "Feb", "Mar", "Apr", "May"]
data = {"month": [], "temp": []}
for i, month in enumerate(months):
    for _ in range(200):
        data["month"].append(month)
        data["temp"].append(rng.gauss(20 + i, 3))

c = pt.chart(data, aes(x="month", y="temp"),
             title="daily temperature", xlabel="temperature (°C)",
             data_width=320, data_height=240)
c.add_ridge(overlap=1.6)
c.yticks([])

