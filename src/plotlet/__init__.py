"""plotlet — pure-Python SVG renderer, matplotlib-flavored.

Tabular API (recommended):

    import plotlet as pt
    c = pt.chart(df, title="...", xlabel="x", ylabel="y", legend=True, grid=True)
    c.line(x="time", y="value", hue="series")
    c                         # auto-renders in Jupyter

Chained API (legacy, still supported):

    fig = pt.figure()
    fig.plot([1, 2, 3], [1, 4, 9], label="squares")
    fig.title("Hello").legend().grid(True)
    fig
"""
from ._spec import SPEC
from .colors import TAB10, colors
from .colormaps import colormap, list_colormaps
from .core import Figure, figure
from .chart import Chart, chart
from .layout import grid
from .registry import ArtistSpec, add_artist

__all__ = ["chart", "Chart", "figure", "Figure", "SPEC", "TAB10", "colors",
           "colormap", "list_colormaps", "grid", "ArtistSpec", "add_artist"]
__version__ = "0.1.1"
