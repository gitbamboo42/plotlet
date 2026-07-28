"""Boxplot + strip

The chart-level aes() mapping is inherited by every artist call, so
overlays are two lines: a boxplot and the raw points on top.
"""
import plotlet as pt
from plotlet import aes

df = pt.load_dataset("tips")

c = pt.chart(df, aes(x="day", y="total_bill"),
             title="bill by day", ylabel="total bill ($)",
             data_width=340, data_height=220)
c.xscale("category", order=["Thur", "Fri", "Sat", "Sun"])
c.add_boxplot()
c.add_strip(size=2.5, alpha=0.45)

