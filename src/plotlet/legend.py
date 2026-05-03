"""Layout-level legend — one guide for both discrete and continuous.

A legend is a leaf-flavored `Chart`. The layout treats it as a regular
leaf with intrinsic size, but it renders through the legend renderer
instead of the standard frame+artists pipeline. Geometry (gradient strip
vs. swatch list) is decided at render time from the source's color
mapping, not by the constructor name. See `docs/SUBPLOTS.md`.

Two render paths share one panel:
  - Continuous: each source artist's `spec.legend_gradient` returns a
    {cmap, vmin, vmax, label, ticks} descriptor; the legend draws a
    vertical gradient strip with ticks (vmax at top).
  - Discrete: each labeled artist's `spec.legend_swatch` paints its own
    swatch (today's behavior, factored out of the in-frame overlay).
Mixed sources stack continuous-first, discrete-second.
"""
from __future__ import annotations

from .core import Figure
from .chart import Chart
from .colormaps import colormap
from .registry import RenderContext, get_artist
from .font import _text_path
from .scales import _LinearScale, _fmt_tick
from ._spec import _D, _DASH, _FONTSPEC, _FRAME, _LEGSPEC

_DEFAULT_W = 100
_DEFAULT_H = 300
_FONT = _FONTSPEC["family"]
_SPINE = _FRAME["color"]
_SPW = _FRAME["width"]
_TICK_LEN = _FRAME["tick_length"]
_TICK_PAD = _FRAME["tick_pad"]
_GRAD_W = _LEGSPEC["gradient_width"]
_GRAD_N = _LEGSPEC["gradient_n_stops"]
_SECTION_GAP = _LEGSPEC["section_gap"]


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


def _harvest_continuous(sources: list[Chart], states: dict[int, dict]) -> list[dict]:
    """Collect continuous-mapping descriptors across `sources`. Each
    artist with a `spec.legend_gradient` is asked to describe its mapping;
    a None return means "no continuous entry to show" (e.g. categorical
    imshow once that lands)."""
    out = []
    for src in sources:
        st = states.get(id(src))
        if st is None:
            continue
        for a in st["artists"]:
            spec = get_artist(a["type"])
            if spec is None or spec.legend_gradient is None:
                continue
            desc = spec.legend_gradient(a)
            if desc is not None:
                out.append(desc)
    return out


def _gradient_stops(cmap_name: str, n: int) -> str:
    """SVG <stop> list for a vertical top→bottom strip running vmax→vmin."""
    cm = colormap(cmap_name)
    stops = []
    for i in range(n + 1):
        offset = i / n
        # offset 0 = top of strip = vmax color; offset 1 = bottom = vmin
        r, g, b = cm(1.0 - offset)
        stops.append(f'<stop offset="{offset*100:.2f}%" '
                     f'stop-color="rgb({r},{g},{b})"/>')
    return "".join(stops)


def _render_continuous_entry(entry: dict, x: float, y: float, h: float, gid: str) -> str:
    """One continuous entry: optional label above, gradient strip with
    right-side ticks below. Labels and ticks scale with the entry's
    allocated height; sizing-from-content lands in commit 5."""
    parts = [f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
             f'{_gradient_stops(entry["cmap"], _GRAD_N)}'
             f'</linearGradient></defs>']

    tick_size = _FONTSPEC["tick_size"]
    label_text = entry.get("label")
    label_h = tick_size + 4 if label_text else 0
    if label_text:
        parts.append(_text_path(label_text, x, y + tick_size,
                                tick_size, anchor="start"))

    strip_y = y + label_h
    strip_h = max(0.0, h - label_h)
    parts.append(f'<rect x="{x:.2f}" y="{strip_y:.2f}" width="{_GRAD_W}" '
                 f'height="{strip_h:.2f}" fill="url(#{gid})" '
                 f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')

    vmin, vmax = entry["vmin"], entry["vmax"]
    scale = _LinearScale(vmin, vmax, strip_y + strip_h, strip_y)
    ticks = list(entry["ticks"]) if entry.get("ticks") is not None else scale.ticks(5)

    tx0 = x + _GRAD_W
    tx1 = tx0 + _TICK_LEN
    label_x = tx1 + _TICK_PAD
    for t in ticks:
        ty = scale(t)
        parts.append(f'<line x1="{tx0}" x2="{tx1}" '
                     f'y1="{ty:.2f}" y2="{ty:.2f}" '
                     f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')
        parts.append(_text_path(_fmt_tick(t), label_x, ty + 4,
                                tick_size, anchor="start"))
    return "".join(parts)


def _render_legend(leaf: Chart, w: float, h: float,
                   states: dict[int, dict],
                   data_leaves: list[Chart],
                   legend_idx: int = 0) -> str:
    """Render the legend leaf's content into its allocated rect.

    Sources default to all data leaves in the layout; explicit
    `pt.legend(a, b)` narrows to those. Continuous entries (gradient
    strips) stack above discrete entries (swatch + label rows)."""
    sources = leaf._legend_sources or data_leaves
    cont_entries = _harvest_continuous(sources, states)
    disc_entries = _harvest_discrete(sources, states)
    if not cont_entries and not disc_entries:
        return ''

    pad_x = _LEGSPEC["pad_x"]
    pad_y = _LEGSPEC["pad_y"]
    row_h = _LEGSPEC["row_height"]
    sw    = _LEGSPEC["swatch_width"]
    tick_size = _FONTSPEC["tick_size"]

    n_cont = len(cont_entries)
    n_disc = len(disc_entries)
    # Discrete block sized by its row count; continuous block divides
    # the rest of the height equally across continuous entries.
    disc_h = n_disc * row_h
    section_gap = _SECTION_GAP if n_cont and n_disc else 0
    cont_total_h = max(0.0, h - 2 * pad_y - disc_h - section_gap)
    per_cont_h = cont_total_h / n_cont if n_cont else 0

    parts = []
    cy = pad_y
    for i, entry in enumerate(cont_entries):
        gid = f"plotlet-grad-{legend_idx}-{i}"
        parts.append(_render_continuous_entry(
            entry, pad_x, cy, per_cont_h, gid))
        cy += per_cont_h
    if n_cont and n_disc:
        cy += section_gap

    for i, a in enumerate(disc_entries):
        ry = cy + i * row_h + row_h / 2
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
