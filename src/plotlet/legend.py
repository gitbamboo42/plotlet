"""Layout-level legend — one guide for both discrete and continuous.

A legend is a leaf-flavored `Chart`. The layout treats it as a regular
leaf with intrinsic size, but it renders through the legend renderer
instead of the standard frame+artists pipeline. Geometry (gradient strip
vs. swatch list) is decided at render time from the source's color
mapping, not by the constructor name. See `docs/SUBPLOTS.md`.

This module ships the constructor and a placeholder render. The
discrete and continuous render paths land in subsequent commits.
"""
from __future__ import annotations

from .core import Figure
from .chart import Chart
from ._spec import _FONTSPEC

_DEFAULT_W = 100
_DEFAULT_H = 300
_FONT = _FONTSPEC["family"]


def legend(*sources: Chart, width: int | None = None,
           height: int | None = None) -> Chart:
    """Create a layout-level legend.

    With no `sources`, the legend harvests entries from every leaf in
    its parent layout. With sources, it harvests only from those.
    """
    for src in sources:
        if not isinstance(src, Chart):
            raise TypeError(
                f"pt.legend() sources must be Chart objects; got {type(src).__name__}."
            )
        if src._is_parent:
            raise ValueError(
                "pt.legend() sources must be leaf charts, not composed parents."
            )
    leaf = Chart.__new__(Chart)
    leaf._fig = Figure(width=width or _DEFAULT_W, height=height or _DEFAULT_H)
    leaf._data = None
    leaf._parent = None
    leaf._layout_kind = None
    leaf._children = []
    leaf._share_x = None
    leaf._share_y = None
    leaf._legend_kind = True
    leaf._legend_sources = list(sources)
    return leaf


def _render_legend(leaf: Chart, w: float, h: float) -> str:
    """Placeholder render — outlined rect so the legend's allocated
    rect is visible during step 3 development. Discrete/continuous
    render paths replace this in later commits."""
    return (f'<rect x="0.5" y="0.5" width="{w-1:.2f}" height="{h-1:.2f}" '
            f'fill="none" stroke="#bbb" stroke-dasharray="4,3"/>')


def _render_standalone_legend(leaf: Chart) -> str:
    """Render a legend that's not part of any parent — wraps the leaf
    render in an outer <svg>. Mostly for early development; in real use
    a legend lives inside a layout."""
    w, h = leaf._fig._width, leaf._fig._height
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family="{_FONT}" font-size="11" '
            f'style="background:#fff">'
            f'{_render_legend(leaf, w, h)}'
            f'</svg>')
