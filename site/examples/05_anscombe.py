"""Anscombe's quartet

A 2x2 grid with shared scales: same means, same variances, same
regression line -- four very different point clouds.
"""
import plotlet as pt
from plotlet import aes

raw = pt.load_dataset("anscombe")

panels = []
for ds in ("I", "II", "III", "IV"):
    xs = [x for x, d in zip(raw["x"], raw["dataset"]) if d == ds]
    ys = [y for y, d in zip(raw["y"], raw["dataset"]) if d == ds]
    sub = {"x": xs, "y": ys}

    p = pt.chart(sub, aes(x="x", y="y"),
                 title=f"dataset {ds}", data_width=190, data_height=140)
    p.add_scatter(size=3.5, alpha=0.8)
    p.add_regression()
    panels.append(p)

p1, p2, p3, p4 = panels
c = pt.grid([[p1, p2], [p3, p4]]).share_x(True).share_y(True)
