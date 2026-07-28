"""ECDF

Empirical distribution functions compare groups without binning.
"""
import plotlet as pt
from plotlet import aes

df = pt.load_dataset("tips")

c = pt.chart(df, aes(x="total_bill", color="time"),
             title="bill size by service", xlabel="total bill ($)",
             ylabel="fraction of parties", legend=True,
             data_width=320, data_height=210)
c.add_ecdf()
