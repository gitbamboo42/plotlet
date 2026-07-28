"""Q-Q plot

Sample quantiles against a theoretical normal, with the reference
line drawn for you.
"""
import random

import plotlet as pt
from plotlet import aes

rng = random.Random(16)
df = {"s": [rng.gauss(0, 1) + 0.2 * (rng.expovariate(1) - 1)
            for _ in range(150)]}

c = pt.chart(df, aes(sample="s"),
             title="Q-Q vs N(0, 1)",
             xlabel="theoretical quantile", ylabel="sample quantile",
             data_width=260, data_height=230)
c.add_qq(dist="normal")

