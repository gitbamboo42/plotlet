"""Chord diagram

A sectored ring with chord ribbons through the center disc --
Circos-style flow figures from the same chart API.
"""
import plotlet as pt
from plotlet import aes

sectors = pt.Sectors(names=["A", "B", "C"], lengths=[30, 25, 20], gap=4)
span = (0, sectors.total())

flows = {
    "src": ["A", "A", "B"],
    "dst": ["B", "C", "C"],
    "x1a": [0, 18, 0], "x1b": [10, 28, 15],
    "x2a": [0, 0, 0],  "x2b": [10, 8, 12],
}
arcs = pt.chart(flows, xlim=span)
arcs.sectors(sectors, column="src", label=False)
arcs.add_chord_ribbon(aes(x1_start="x1a", x1_end="x1b",
                          x2_start="x2a", x2_end="x2b",
                          x1_sector="src", x2_sector="dst",
                          color="src"), alpha=0.6)

ring = pt.chart(xlim=span, ylim=(0, 1))
ring.sectors(sectors, column="x")

c = pt.grid([[ring]]).coordinate(
    pt.CircularCoordinate(r_inner=0.85, inner=arcs)
)
