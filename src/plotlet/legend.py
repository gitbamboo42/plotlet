"""Layout-level legend — one guide for both discrete and continuous.

A legend is a leaf-flavored `Chart`. The layout treats it as a regular
leaf with intrinsic size, but it renders through the legend renderer
instead of the standard frame+artists pipeline. Geometry (gradient strip
vs. swatch list) is decided at render time from the source's color
mapping, not by the constructor name. See `docs/SUBPLOTS.md`.

This module currently ships the constructor and the discrete swatch-list
render. The continuous gradient strip lands in the next commit.
"""
from __future__ import annotations

from .core import Figure
from .chart import Chart
from .registry import RenderContext, get_artist
from .font import _text_path
from ._spec import _D, _DASH, _FONTSPEC, _LEGSPEC

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


def _swatch_ctx(a: dict) -> RenderContext:
    """Minimal context for `legend_swatch` — only the fields swatch helpers
    actually read (defaults, dash, color). x/y scales aren't relevant."""
    return RenderContext(
        x_scale=None, y_scale=None, iw=0, ih=0,
        color=a["_color"], defaults=_D, dash=_DASH,
    )


def _harvest_discrete(sources: list[Chart], states: dict[int, dict]) -> list[dict]:
    """Collect labeled artists across `sources`, in order. Each source's
    state must already have `_color` assigned (which `_render_inner` does
    during the data-leaf render pass)."""
    out = []
    for src in sources:
        st = states.get(id(src))
        if st is None:
            continue
        for a in st["artists"]:
            if a["opts"].get("label"):
                out.append(a)
    return out


def _render_legend(leaf: Chart, w: float, h: float,
                   states: dict[int, dict],
                   data_leaves: list[Chart]) -> str:
    """Render the legend leaf's content into its allocated rect.

    Sources default to all data leaves in the layout; explicit
    `pt.legend(a, b)` narrows to those. Currently emits the discrete
    swatch list only; gradient strips for continuous-color sources land
    in the next commit."""
    sources = leaf._legend_sources or data_leaves
    entries = _harvest_discrete(sources, states)
    if not entries:
        return ''

    row_h = _LEGSPEC["row_height"]
    pad_x = _LEGSPEC["pad_x"]
    pad_y = _LEGSPEC["pad_y"]
    sw    = _LEGSPEC["swatch_width"]
    tick_size = _FONTSPEC["tick_size"]

    parts = []
    for i, a in enumerate(entries):
        ry = pad_y + i * row_h + row_h / 2
        spec = get_artist(a["type"])
        if spec is not None and spec.legend_swatch is not None:
            parts.append(spec.legend_swatch(a, _swatch_ctx(a), pad_x, ry))
        else:
            parts.append(f'<line x1="{pad_x}" x2="{pad_x + sw}" y1="{ry}" y2="{ry}" '
                         f'stroke="{a["_color"]}" stroke-width="{_D["linewidth"]}"/>')
        parts.append(_text_path(a["opts"]["label"], pad_x + sw + 6, ry + 4,
                                tick_size, anchor="start"))
    return ''.join(parts)


def _render_standalone_legend(leaf: Chart) -> str:
    """Render a legend not part of any parent — wraps the leaf render in
    an outer <svg>. Standalone with explicit sources requires replaying
    + color-assigning those sources, which lands when grouping does
    (commit 5). For now this draws an empty placeholder rect."""
    w, h = leaf._fig._width, leaf._fig._height
    inner = (f'<rect x="0.5" y="0.5" width="{w-1:.2f}" height="{h-1:.2f}" '
             f'fill="none" stroke="#bbb" stroke-dasharray="4,3"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family="{_FONT}" font-size="11" '
            f'style="background:#fff">{inner}</svg>')
