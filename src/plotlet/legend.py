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
from .font import _measure_text, _text_path
from .scales import _LinearScale, _fmt_tick
from ._spec import _D, _DASH, _FONTSPEC, _FRAME, _LEGSPEC

_FONT = _FONTSPEC["family"]
_SPINE = _FRAME["color"]
_SPW = _FRAME["width"]
_TICK_LEN = _FRAME["tick_length"]
_TICK_PAD = _FRAME["tick_pad"]
_GRAD_W = _LEGSPEC["gradient_width"]
_GRAD_H = _LEGSPEC["gradient_height"]
_GRAD_N = _LEGSPEC["gradient_n_stops"]
_SECTION_GAP = _LEGSPEC["section_gap"]


def _adaptive_n_ticks(strip_h: float) -> int:
    """Cap tick count for short strips so labels (~11 px tall each) don't
    crowd. Mirrors the axis-tick-density rule in core._render_inner."""
    return max(2, min(5, int(strip_h // 18)))


def legend(*sources: Chart, names: dict | None = None,
           group_by_chart: bool = True,
           canvas_width: int | float | str | None = None,
           canvas_height: int | float | str | None = None,
           **kwargs) -> Chart:
    """Create a layout-level legend.

    With no `sources`, the legend harvests entries from every leaf in
    its parent layout. With sources, it harvests only from those.

    Multiple sources are grouped by source chart, with each chart's
    `title` rendered as a section header. `names={chart: "Override"}`
    replaces a header text; `names={chart: None}` hides the header
    while keeping the entries. `group_by_chart=False` flattens all
    entries into a single unsectioned list (useful when small-multiples
    genuinely share a series).

    Legend leaves have no data axes, so the dimensional surface is
    canvas-only: pass `canvas_width=` / `canvas_height=` to override the
    content-driven auto-size.
    """
    if "width" in kwargs or "height" in kwargs:
        raise TypeError(
            "pt.legend() no longer accepts `width=` / `height=` (changed in 0.2.0). "
            "Use `canvas_width=` / `canvas_height=` instead — legend leaves "
            "have no data axes, so the canvas is the only meaningful dimension."
        )
    if kwargs:
        raise TypeError(f"pt.legend() got unexpected keyword arguments: {list(kwargs)!r}")
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
    # Canvas size starts as a 1×1 placeholder; `_size_legends` overrides
    # it from harvested content at render time, unless the user passed
    # an explicit canvas_*.
    leaf._fig = Figure(canvas_width=canvas_width if canvas_width is not None else 1,
                       canvas_height=canvas_height if canvas_height is not None else 1)
    leaf._data = None
    leaf._parent = None
    leaf._layout_kind = None
    leaf._children = []
    leaf._share_x = None
    leaf._share_y = None
    leaf._legend_kind = True
    leaf._legend_sources = list(sources)
    leaf._legend_names = dict(names) if names else {}
    leaf._legend_group_by_chart = group_by_chart
    leaf._legend_user_width = canvas_width
    leaf._legend_user_height = canvas_height
    return leaf


def _swatch_ctx(a: dict) -> RenderContext:
    """Minimal context for `legend_swatch` — only the fields swatch helpers
    actually read (defaults, dash, color). x/y scales aren't relevant."""
    return RenderContext(
        x_scale=None, y_scale=None, iw=0, ih=0,
        color=a["_color"], defaults=_D, dash=_DASH,
    )


def _build_groups(sources: list[Chart], states: dict[int, dict],
                  names: dict, group_by_chart: bool) -> list[dict]:
    """Collect entries per source and decide each section's header.

    Each returned dict is `{"header": str|None, "cont": [...], "disc": [...]}`.
    `header` is `None` either because the user explicitly hid it via
    `names[src] = None`, the source has no `title`, grouping is off, or
    a continuous entry already carries its own `legend["label"]` (the
    chart title would just stack a second redundant caption above the
    gradient). Sources contributing zero entries are skipped entirely."""
    raw = []
    for src in sources:
        st = states.get(id(src))
        if st is None:
            continue
        cont, disc = [], []
        for a in st["artists"]:
            spec = get_artist(a["type"])
            if spec is None:
                continue
            if spec.legend_gradient is not None:
                desc = spec.legend_gradient(a)
                if desc is not None:
                    cont.append(desc)
            if a["opts"].get("label") and spec.legend_swatch is not None:
                disc.append(a)
        if not cont and not disc:
            continue
        if not group_by_chart:
            header = None
        elif src in names:
            header = names[src]   # user-overridden — keep verbatim
        elif any(c.get("label") for c in cont):
            header = None         # entry's own label already names the gradient
        else:
            header = st.get("title")
        raw.append({"header": header, "cont": cont, "disc": disc})

    if not group_by_chart and raw:
        return [{
            "header": None,
            "cont": [c for g in raw for c in g["cont"]],
            "disc": [d for g in raw for d in g["disc"]],
        }]
    return raw


def _render_continuous_entry(entry: dict, x: float, y: float) -> str:
    """One continuous entry: optional label above, then a gradient strip
    of fixed height (`legend.gradient_height`) with right-side ticks.
    Tick count adapts to strip height so labels don't crowd.

    The strip is drawn as `_GRAD_N + 1` solid-fill rect bands rather than
    a `<linearGradient>` — no `<defs>`, no `id`, no `url(#…)`, so the SVG
    has nothing that can collide when multiple plotlet SVGs are inlined
    into the same HTML document. Bands are sub-pixel at the spec strip
    height (60 px / 33 stops ≈ 1.8 px each); rasterizer AA on rect edges
    makes the result visually identical to a native gradient."""
    parts = []
    tick_size = _FONTSPEC["tick_size"]
    label_text = entry.get("label")
    label_h = tick_size + 4 if label_text else 0
    if label_text:
        parts.append(_text_path(label_text, x, y + tick_size,
                                tick_size, anchor="start"))

    strip_y = y + label_h
    strip_h = float(_GRAD_H)
    cm = colormap(entry["cmap"])
    n_bands = _GRAD_N + 1
    band_h = strip_h / n_bands
    for i in range(n_bands):
        # i=0 at top → vmax color; i=n-1 at bottom → vmin color.
        # Each band but the last extends 1 px into the next so AA seams
        # don't show as hairline white lines between sub-pixel rects.
        r, g, b = cm(1.0 - i / _GRAD_N)
        h = band_h + (1.0 if i < n_bands - 1 else 0.0)
        parts.append(f'<rect x="{x:.2f}" y="{strip_y + i*band_h:.4f}" '
                     f'width="{_GRAD_W}" height="{h:.4f}" '
                     f'fill="rgb({r},{g},{b})"/>')
    parts.append(f'<rect x="{x:.2f}" y="{strip_y:.2f}" width="{_GRAD_W}" '
                 f'height="{strip_h:.2f}" fill="none" '
                 f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')

    vmin, vmax = entry["vmin"], entry["vmax"]
    scale = _LinearScale(vmin, vmax, strip_y + strip_h, strip_y)
    ticks = (list(entry["ticks"]) if entry.get("ticks") is not None
             else scale.ticks(_adaptive_n_ticks(strip_h)))

    tx0 = x + _GRAD_W
    tx1 = tx0 + _TICK_LEN
    label_x = tx1 + _TICK_PAD
    # Bias each tick-label baseline toward the strip's vertical center —
    # top tick shifts down so it doesn't crowd whatever sits above the
    # strip (entry label / chart title), bottom tick shifts up by the
    # same amount, middle ticks unchanged. The tick line still points
    # at the exact value position; only the text shifts.
    strip_mid = strip_y + strip_h / 2
    for t in ticks:
        ty = scale(t)
        parts.append(f'<line x1="{tx0}" x2="{tx1}" '
                     f'y1="{ty:.2f}" y2="{ty:.2f}" '
                     f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')
        bias = 4 * (strip_mid - ty) / (strip_h / 2) if strip_h > 0 else 0
        parts.append(_text_path(_fmt_tick(t), label_x, ty + 4 + bias,
                                tick_size, anchor="start"))
    return "".join(parts)


def _legend_content_size(leaf: Chart, sources: list[Chart],
                         states: dict[int, dict]) -> tuple[float, float]:
    """Compute the legend leaf's content-driven (width, height).

    Width = max content width across sections (gradient column +
    ticks/labels for continuous, swatch + label for discrete, plus
    headers and any per-entry above-strip label) + side padding.

    Height = sum of section heights + inter-section gaps + top/bottom
    padding. Strip height is fixed at `legend.gradient_height` per
    continuous entry — independent of source plot height."""
    names = leaf._legend_names or {}
    group_by_chart = leaf._legend_group_by_chart
    groups = _build_groups(sources, states, names, group_by_chart)
    if not groups:
        return 1.0, 1.0

    pad_x = _LEGSPEC["pad_x"]
    pad_y = _LEGSPEC["pad_y"]
    row_h = _LEGSPEC["row_height"]
    sw = _LEGSPEC["swatch_width"]
    tick_size = _FONTSPEC["tick_size"]
    label_size = _FONTSPEC["label_size"]
    header_h = label_size + 4
    n_ticks = _adaptive_n_ticks(_GRAD_H)

    max_w = 0.0
    total_h = 2 * pad_y
    for gi, g in enumerate(groups):
        if g["header"]:
            max_w = max(max_w, _measure_text(g["header"], label_size))
            total_h += header_h
        for entry in g["cont"]:
            label = entry.get("label")
            if label:
                max_w = max(max_w, _measure_text(label, tick_size))
                total_h += tick_size + 4
            ticks = (list(entry["ticks"]) if entry.get("ticks") is not None
                     else _LinearScale(entry["vmin"], entry["vmax"], 0, 1).ticks(n_ticks))
            max_tw = max((_measure_text(_fmt_tick(t), tick_size) for t in ticks), default=0.0)
            strip_col_w = _GRAD_W + _TICK_LEN + _TICK_PAD + max_tw
            max_w = max(max_w, strip_col_w)
            total_h += _GRAD_H
        if g["cont"] and g["disc"]:
            total_h += _SECTION_GAP
        for a in g["disc"]:
            disc_w = sw + 6 + _measure_text(a["opts"]["label"], tick_size)
            max_w = max(max_w, disc_w)
        total_h += len(g["disc"]) * row_h
        if gi < len(groups) - 1:
            total_h += _SECTION_GAP

    return max_w + 2 * pad_x, total_h


def _size_legends(root: Chart, states: dict[int, dict]) -> None:
    """Pre-render pass: override each legend leaf's intrinsic _fig canvas
    size with its content-driven size, except where the user passed
    explicit `canvas_width=` / `canvas_height=` to `pt.legend(...)`."""
    from .layout import _iter_leaves  # avoid circular import at module load
    data_leaves = [l for l in _iter_leaves(root) if not l._legend_kind]
    for leaf in _iter_leaves(root):
        if not leaf._legend_kind:
            continue
        sources = leaf._legend_sources or data_leaves
        cw, ch = _legend_content_size(leaf, sources, states)
        if leaf._legend_user_width is None:
            leaf._fig._canvas_width = max(1, int(round(cw)))
        if leaf._legend_user_height is None:
            leaf._fig._canvas_height = max(1, int(round(ch)))


def _render_legend(leaf: Chart, w: float, h: float,
                   states: dict[int, dict],
                   data_leaves: list[Chart]) -> str:
    """Render the legend leaf's content into its allocated rect.

    Sources default to all data leaves in the layout; explicit
    `pt.legend(a, b)` narrows to those. With grouping on (the default),
    each source becomes a section with its `title` as header; continuous
    entries (gradient strips) stack above discrete entries (swatch +
    label rows) within each section.

    Strip height is fixed at `legend.gradient_height` (independent of
    `h`); when the parent allocates more vertical space than the content
    needs, the content is top-aligned and the surplus sits below."""
    sources = leaf._legend_sources or data_leaves
    names = getattr(leaf, "_legend_names", {}) or {}
    group_by_chart = getattr(leaf, "_legend_group_by_chart", True)

    groups = _build_groups(sources, states, names, group_by_chart)
    if not groups:
        return ''

    pad_x = _LEGSPEC["pad_x"]
    pad_y = _LEGSPEC["pad_y"]
    row_h = _LEGSPEC["row_height"]
    sw    = _LEGSPEC["swatch_width"]
    tick_size = _FONTSPEC["tick_size"]
    label_size = _FONTSPEC["label_size"]
    header_h = label_size + 4

    parts = []
    cy = pad_y
    for gi, g in enumerate(groups):
        if g["header"]:
            parts.append(_text_path(g["header"], pad_x, cy + label_size,
                                    label_size, anchor="start"))
            cy += header_h
        for entry in g["cont"]:
            entry_label_h = (tick_size + 4) if entry.get("label") else 0
            parts.append(_render_continuous_entry(entry, pad_x, cy))
            cy += entry_label_h + _GRAD_H
        if g["cont"] and g["disc"]:
            cy += _SECTION_GAP
        for i, a in enumerate(g["disc"]):
            ry = cy + i * row_h + row_h / 2
            spec = get_artist(a["type"])
            if spec is not None and spec.legend_swatch is not None:
                parts.append(spec.legend_swatch(a, _swatch_ctx(a), pad_x, ry))
            else:
                parts.append(f'<line x1="{pad_x}" x2="{pad_x + sw}" y1="{ry}" y2="{ry}" '
                             f'stroke="{a["_color"]}" stroke-width="{_D["linewidth"]}"/>')
            parts.append(_text_path(a["opts"]["label"], pad_x + sw + 6, ry + 4,
                                    tick_size, anchor="start"))
        cy += len(g["disc"]) * row_h
        if gi < len(groups) - 1:
            cy += _SECTION_GAP

    return ''.join(parts)


def _render_standalone_legend(leaf: Chart) -> str:
    """Render a legend not part of any parent — wraps the leaf render in
    an outer <svg>. Standalone with explicit sources requires replaying
    + color-assigning those sources, which lands when grouping does
    (commit 5). For now this draws an empty placeholder rect."""
    w, h = leaf._fig._canvas_width, leaf._fig._canvas_height
    inner = (f'<rect x="0.5" y="0.5" width="{w-1:.2f}" height="{h-1:.2f}" '
             f'fill="none" stroke="#bbb" stroke-dasharray="4,3"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family="{_FONT}" font-size="11" '
            f'style="background:#fff">{inner}</svg>')
