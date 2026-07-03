"""plotlet — pure-Python deferred-rendering SVG plot library.

    import plotlet as pt
    c = pt.chart(df, title="...", xlabel="x", ylabel="y", legend=True, grid=True)
    c.line(x="time", y="value", color="series")
    c                         # auto-renders in Jupyter

Chart methods chain for incremental composition:

    df = {"x": [1, 2, 3], "y": [1, 4, 9]}
    c = pt.chart()
    c.line(df, x="x", y="y", label="squares")
    c.title("Hello").legend().grid(True)
    c
"""
from ._spec import SPEC
from .draw import TAB10, colors
from .draw import colormap, list_colormaps
from . import artists  # noqa: F401  — registers built-in artists on import
from .chart import Chart, Layout, chart, grid
from .legend import legend
from .registry import ArtistSpec, add_artist, artist_table, declare_coord_support
from .coordinates import CircularCoordinate
from .sectors import Sectors
from .layout_diagram import layout_diagram
from .themes import load_theme, available_themes, register_theme
from .facet import facet, FacetGrid
from .datasets import load, list_datasets
from .cluster import cluster, cluster_split, SplitTree
from .formatters import register_formatter, list_formatters
from ._coord_registry import register_coord_codec
from ._journal import (to_journal, from_journal, to_json, from_json,
                       JournalNode, Journal)
from . import draw, utils

__all__ = ["chart", "Chart", "Layout", "SPEC", "TAB10", "colors",
           "colormap", "list_colormaps", "grid", "legend",
           "ArtistSpec", "add_artist", "artist_table", "declare_coord_support",
           "CircularCoordinate", "Sectors",
           "layout_diagram",
           "load_theme", "available_themes", "register_theme",
           "facet", "FacetGrid",
           "load", "list_datasets",
           "cluster", "cluster_split", "SplitTree",
           "register_formatter", "list_formatters",
           "to_json", "from_json", "register_coord_codec",
           "to_journal", "from_journal", "JournalNode", "Journal",
           "draw", "utils"]

# Single source of truth: pyproject.toml. importlib.metadata reads it at
# runtime from the installed package metadata (works for `pip install` and
# `pip install -e .` alike). Migrating to setuptools_scm later doesn't
# touch this code — it just changes how pyproject.toml's version is set.
from importlib.metadata import version as _pkg_version
__version__ = _pkg_version("plotlet")
