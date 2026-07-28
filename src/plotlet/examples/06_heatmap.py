"""Heatmap

The flights table as a month x year matrix, with the shared legend
placed as its own layout cell.
"""
import plotlet as pt
from plotlet import aes

df = pt.load_dataset("flights")
months = df["month"][:12]
years = sorted(set(df["year"]))

data = {"year": [str(y) for y in years]}
for m in months:
    data[m] = [n for n, month in zip(df["passengers"], df["month"])
               if month == m]

hm = pt.chart(title="airline passengers", data_width=420, data_height=240)
hm.add_heatmap(data=data, mapping=aes(x="year"), values=months,
               cmap="viridis", legend={"label": "passengers"})

c = pt.grid([[hm, pt.legend()]]).gap(0)
