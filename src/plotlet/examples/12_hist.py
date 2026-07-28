"""Histogram

Stacked bins by group, straight from a long-form table.
"""
import math

import plotlet as pt
from plotlet import aes

raw = pt.load_dataset("penguins")
keep = [i for i in range(len(raw["species"]))
        if not math.isnan(raw["body_mass_g"][i])]
df = {k: [raw[k][i] for i in keep] for k in ("species", "body_mass_g")}

c = pt.chart(df, aes(x="body_mass_g", fill="species"),
             title="body mass", xlabel="body mass (g)", ylabel="count",
             data_width=380, data_height=200)
c.add_hist(bins=24, position="stack")

