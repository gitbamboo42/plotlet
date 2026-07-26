"""Circular coordinate

Any Cartesian chart becomes a ring with one line: bars grouped into
named wedges, with gaps between the sector groups.
"""
import plotlet as pt
from plotlet import aes

df = {"cat": list("abcdefgh"), "val": [3, 5, 2, 6, 4, 7, 3, 5]}

c = pt.chart(df, aes(x="cat", y="val", fill="cat"),
             title="categorical sectors on a ring")
c.coordinate(pt.CircularCoordinate())
c.sectors({"G1": ["a", "b", "c"], "G2": ["d", "e"], "G3": ["f", "g", "h"]},
          axis="x")
c.add_bar(palette="Set2")

