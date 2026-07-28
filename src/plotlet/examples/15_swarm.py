"""Swarm

Beeswarm layout: every observation visible, no overlap.
"""
import plotlet as pt
from plotlet import aes

df = pt.load_dataset("tips")

c = pt.chart(df, aes(x="day", y="tip", fill="sex"),
             title="tips by day", ylabel="tip ($)",
             data_width=380, data_height=220)
c.xscale("category", order=["Thur", "Fri", "Sat", "Sun"])
c.add_swarm(size=2.2)

