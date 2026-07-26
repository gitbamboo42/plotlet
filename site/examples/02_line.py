"""Line

A single time series: monthly airline passengers, 1949-1960.
"""
import plotlet as pt
from plotlet import aes

df = pt.load_dataset("flights")
t = [df["year"][i] + (i % 12) / 12 for i in range(len(df["year"]))]
series = {"t": t, "n": df["passengers"]}

c = pt.chart(series, aes(x="t", y="n"), title="airline passengers",
             xlabel="year", ylabel="passengers / month",
             data_width=460, data_height=200, gridlines=True)
c.add_line()

