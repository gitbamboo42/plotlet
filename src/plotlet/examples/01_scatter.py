"""Scatter

Map a categorical column to color with aes(). Data is the built-in
Palmer penguins table.
"""
import math

import plotlet as pt
from plotlet import aes

raw = pt.load_dataset("penguins")
keep = [i for i in range(len(raw["species"]))
        if not math.isnan(raw["flipper_length_mm"][i])
        and not math.isnan(raw["body_mass_g"][i])]
df = {k: [raw[k][i] for i in keep]
      for k in ("species", "flipper_length_mm", "body_mass_g")}

c = pt.chart(df, aes(x="flipper_length_mm", y="body_mass_g",
                     color="species"),
             title="Palmer penguins",
             xlabel="flipper length (mm)", ylabel="body mass (g)",
             gridlines=True)
c.add_scatter(size=3, alpha=0.7)

