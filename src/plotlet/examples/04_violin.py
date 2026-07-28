"""Violin

Distributions split by two categoricals: x position and fill color.
"""
import math

import plotlet as pt
from plotlet import aes

raw = pt.load_dataset("penguins")
keep = [i for i in range(len(raw["species"]))
        if isinstance(raw["sex"][i], str)
        and not math.isnan(raw["body_mass_g"][i])]
df = {k: [raw[k][i] for i in keep] for k in ("species", "sex", "body_mass_g")}

c = pt.chart(df, aes(x="species", y="body_mass_g", fill="sex"),
             title="body mass by species and sex",
             ylabel="body mass (g)",
             data_width=380, data_height=220)
c.add_violin(inner="box")

