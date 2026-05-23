"""plotlet — pure-Python SVG renderer, matplotlib-flavored.

    import plotlet as pt
    c = pt.chart(df, title="...", xlabel="x", ylabel="y", legend=True, grid=True)
    c.line(x="time", y="value", hue="series")
    c                         # auto-renders in Jupyter

For non-tabular use, the chained form works directly on the same Chart:

    c = pt.chart()
    c.plot([1, 2, 3], [1, 4, 9], label="squares")
    c.title("Hello").legend().grid(True)
    c
"""
from ._spec import SPEC
from .draw.colors import TAB10, colors
from .draw.colormaps import colormap, list_colormaps
from .chart import Chart, Layout, chart, grid
from .legend import legend
from .registry import ArtistSpec, add_artist
from .layout_diagram import layout_diagram
from .themes import load_theme, available_themes, register_theme
from .facet import facet, FacetGrid
from .data import load, list_datasets
from . import draw, utils

__all__ = ["chart", "Chart", "Layout", "SPEC", "TAB10", "colors",
           "colormap", "list_colormaps", "grid", "legend",
           "ArtistSpec", "add_artist", "layout_diagram",
           "load_theme", "available_themes", "register_theme",
           "facet", "FacetGrid",
           "load", "list_datasets",
           "draw", "utils"]

# Single source of truth: pyproject.toml. importlib.metadata reads it at
# runtime from the installed package metadata (works for `pip install` and
# `pip install -e .` alike). Migrating to setuptools_scm later doesn't
# touch this code — it just changes how pyproject.toml's version is set.
from importlib.metadata import version as _pkg_version
__version__ = _pkg_version("plotlet")
