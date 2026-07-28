"""Facets

One panel per group with shared axes, from a single call.
"""
import math

import plotlet as pt
from plotlet import aes

raw = pt.load_dataset("penguins")
keep = [i for i in range(len(raw["species"]))
        if not math.isnan(raw["bill_length_mm"][i])
        and not math.isnan(raw["bill_depth_mm"][i])]
df = {k: [raw[k][i] for i in keep]
      for k in ("species", "bill_length_mm", "bill_depth_mm")}

c = pt.facet(df, by="species", col_wrap=3,
             data_width=170, data_height=150,
             xlabel="bill length (mm)", ylabel="bill depth (mm)")
c.add_scatter(aes(x="bill_length_mm", y="bill_depth_mm"),
              size=2, alpha=0.7)
