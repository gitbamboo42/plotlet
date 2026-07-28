"""Bar

Aggregate in plain Python, then plot. Tipping rate by weekday from
the built-in tips table.
"""
import plotlet as pt
from plotlet import aes

df = pt.load_dataset("tips")
days = ["Thur", "Fri", "Sat", "Sun"]
pct = {d: [] for d in days}
for bill, tip, day in zip(df["total_bill"], df["tip"], df["day"]):
    pct[day].append(100 * tip / bill)
rates = {"day": days, "rate": [sum(v) / len(v) for v in pct.values()]}

c = pt.chart(rates, aes(x="day", y="rate", fill="day"),
             title="mean tip rate by day", ylabel="tip (% of bill)",
             data_width=300, data_height=200)
c.add_bar(legend=False)

