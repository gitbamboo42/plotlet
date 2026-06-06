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
  - Discrete: each source artist's `spec.legend_entries` returns a list
    of `{"label", "color", "paint"?}` dicts — one per legend row. An
    artist may emit zero, one, or many entries from a single call,
    which lets multi-category artists (sankey, mosaic, dag, ...) carry
    their own legend without forcing the caller into a fan-out loop.
Mixed sources stack continuous-first, discrete-second.
"""
from __future__ import annotations

from .chart import Chart
from .draw import colormap, ContinuousNorm
from .registry import RenderContext, get_artist
from .draw import measure_text
from .draw import text_path, rect, segment
from .scales import _fmt_tick
from ._spec import _D, _DASH, _FIGSPEC, _FONTSPEC, _FRAME, _LEGSPEC


def _adaptive_n_ticks(strip_h: float) -> int:
    """Cap tick count for short strips so labels (~11 px tall each) don't
    crowd. Mirrors the axis-tick-density rule in core._render_inner."""
    return max(2, min(5, int(strip_h // 18)))


def legend(*sources: Chart, names: dict | None = None,
           group_by_chart: bool = True,
           canvas_width: int | float | str | None = None,
           canvas_height: int | float | str | None = None,
           legend_gap: int | float | None = None,
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
    content-driven auto-size. `legend_gap=N` overrides the default 6 px
    separation between this legend and its source neighbor (falls back
    to `spec.json:layout.legend_gap` when unset).
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
    # Canvas size starts as a 1×1 placeholder; `_size_legends` overrides
    # it from harvested content at render time, unless the user passed
    # an explicit canvas_*. Legend leaves have no data region — the
    # canvas IS the dimensional primitive (see `Chart._new_sized_leaf`).
    from .core import _to_px
    cw = _to_px(canvas_width) if canvas_width is not None else 1
    ch = _to_px(canvas_height) if canvas_height is not None else 1
    leaf = Chart._new_sized_leaf(canvas_width=cw, canvas_height=ch,
                                 leaf_kind="legend")
    leaf._legend_sources = list(sources)
    leaf._legend_names = dict(names) if names else {}
    leaf._legend_group_by_chart = group_by_chart
    leaf._legend_user_width = canvas_width
    leaf._legend_user_height = canvas_height
    leaf._legend_gap = float(legend_gap) if legend_gap is not None else None
    return leaf


def _swatch_ctx(a: dict) -> RenderContext:
    """Minimal context for an entry's `paint` callback — only the fields swatch helpers
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
            if spec.legend_entries is not None:
                for entry in spec.legend_entries(a):
                    entry = dict(entry)
                    entry.setdefault("_a", a)
                    disc.append(entry)
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


def _partition_by_group(entries, key):
    """Partition a flat list into [(group_name, [items]), ...] runs by
    each item's group key. Unlike a consecutive-only grouping, items
    with the same key are collected together even when separated by
    intervening items — so multi-aesthetic legends stack cleanly
    (all color entries together, all size entries together, etc.)
    regardless of which artist record contributed them.

    None-keyed entries (the legacy un-grouped path) stay first in their
    relative order. Named groups follow, ordered by first-appearance."""
    none_items: list = []
    named: dict = {}
    order: list = []
    for item in entries:
        k = key(item)
        if k is None:
            none_items.append(item)
        else:
            if k not in named:
                named[k] = []
                order.append(k)
            named[k].append(item)
    out: list = []
    if none_items:
        out.append((None, none_items))
    for k in order:
        out.append((k, named[k]))
    return out


def _render_discrete_entry(entry: dict, a: dict, ctx_for,
                           x: float, y_mid: float) -> str:
    """One discrete legend row: swatch + label. Shared between the inline
    legend (core._render_inner) and the standalone legend leaf
    (_render_legend) so swatch behavior — paint callback, default color,
    alpha aesthetic — stays in one place.

    `a` is the source artist (needed by paint callbacks). `ctx_for(a)`
    builds the RenderContext for that callback; standalone uses
    `_swatch_ctx`, inline uses the panel's own draw context."""
    sw = _LEGSPEC["swatch_width"]
    paint = entry.get("paint")
    if paint is not None:
        swatch = paint(a, ctx_for(a), x, y_mid)
    else:
        swatch = rect(x, y_mid - 5, sw, 10,
                      fill=entry["color"], alpha=entry.get("alpha", 1))
    label = text_path(entry["label"], x + sw + 6, y_mid + 4,
                      _FONTSPEC["tick_size"], anchor="start",
                      color=_FONTSPEC["color"])
    return swatch + label


def _render_continuous_entry(entry: dict, x: float, y: float,
                              tick_side: str = "right") -> str:
    """One continuous entry: optional label above, then a gradient strip
    of fixed height (`legend.gradient_height`) with ticks on the chosen
    side. Tick count adapts to strip height so labels don't crowd.

    `tick_side="right"` (default) puts the tick marks and labels to the
    right of the strip — the layout-leaf legend's geometry. `tick_side=
    "left"` mirrors for an inline left-position colorbar so the strip
    sits flush with the data area's left edge and ticks face outward.

    The strip is drawn as `_LEGSPEC["gradient_n_stops"] + 1` solid-fill rect bands rather than
    a `<linearGradient>` — no `<defs>`, no `id`, no `url(#…)`, so the SVG
    has nothing that can collide when multiple plotlet SVGs are inlined
    into the same HTML document. Bands are sub-pixel at the spec strip
    height (60 px / 33 stops ≈ 1.8 px each); rasterizer AA on rect edges
    makes the result visually identical to a native gradient."""
    parts = []
    tick_size = _FONTSPEC["tick_size"]
    text_color = _FONTSPEC["color"]
    label_text = entry.get("label")
    label_h = tick_size + 4 if label_text else 0
    if label_text:
        parts.append(text_path(label_text, x, y + tick_size,
                                tick_size, anchor="start", color=text_color))

    strip_y = y + label_h
    strip_h = float(_LEGSPEC["gradient_height"])
    cm = colormap(entry["cmap"])
    n_bands = _LEGSPEC["gradient_n_stops"] + 1
    band_h = strip_h / n_bands
    for i in range(n_bands):
        # i=0 at top → vmax color; i=n-1 at bottom → vmin color.
        # Each band but the last extends 1 px into the next so AA seams
        # don't show as hairline white lines between sub-pixel rects.
        # Strip is always uniform in cmap space — non-linear norms (log,
        # diverging-center) move the *ticks*, not the band colors.
        r, g, b = cm(1.0 - i / _LEGSPEC["gradient_n_stops"])
        h = band_h + (1.0 if i < n_bands - 1 else 0.0)
        parts.append(rect(x, strip_y + i * band_h,
                          _LEGSPEC["gradient_width"], h,
                          fill=f"rgb({r},{g},{b})"))
    parts.append(rect(x, strip_y, _LEGSPEC["gradient_width"], strip_h,
                      stroke=_FRAME["color"], stroke_width=_FRAME["width"]))

    norm = ContinuousNorm(entry["vmin"], entry["vmax"],
                           kind=entry.get("norm", "linear"),
                           center=entry.get("center"))
    ticks = (list(entry["ticks"]) if entry.get("ticks") is not None
             else norm.ticks(_adaptive_n_ticks(strip_h)))

    if tick_side == "right":
        tx0 = x + _LEGSPEC["gradient_width"]
        tx1 = tx0 + _FRAME["tick_length"]
        label_x = tx1 + _FRAME["tick_pad"]
        label_anchor = "start"
    else:  # "left"
        tx0 = x
        tx1 = x - _FRAME["tick_length"]
        label_x = tx1 - _FRAME["tick_pad"]
        label_anchor = "end"
    # Bias each tick-label baseline toward the strip's vertical center —
    # top tick shifts down so it doesn't crowd whatever sits above the
    # strip (entry label / chart title), bottom tick shifts up by the
    # same amount, middle ticks unchanged. The tick line still points
    # at the exact value position; only the text shifts.
    strip_mid = strip_y + strip_h / 2
    for t in ticks:
        ty = strip_y + (1.0 - norm.to_unit(t)) * strip_h
        parts.append(segment(tx0, ty, tx1, ty,
                             color=_FRAME["color"], width=_FRAME["width"]))
        bias = 4 * (strip_mid - ty) / (strip_h / 2) if strip_h > 0 else 0
        parts.append(text_path(_fmt_tick(t), label_x, ty + 4 + bias,
                                tick_size, anchor=label_anchor, color=text_color))
    return "".join(parts)


def _inline_gradient_block_size(cont_entries: list[dict]) -> tuple[float, float]:
    """Block (width, height) for a vertical stack of gradient strips —
    used by the in-frame inline-colorbar path. Mirrors the per-entry
    geometry inside `_legend_content_size` but with no header, no
    discrete rows, and no outer padding (the in-frame block does its
    own positioning relative to the data edge).

    Returns plain `0, 0` (int) for an empty input so callers that add
    to an integer `lh` don't get float promotion — keeps byte-identical
    discrete-only legend output."""
    if not cont_entries:
        return 0, 0
    tick_size = _FONTSPEC["tick_size"]
    n_ticks = _adaptive_n_ticks(_LEGSPEC["gradient_height"])
    max_w = 0.0
    total_h = 0.0
    for i, entry in enumerate(cont_entries):
        label = entry.get("label")
        if label:
            max_w = max(max_w, measure_text(label, tick_size))
            total_h += tick_size + 4
        ticks = (list(entry["ticks"]) if entry.get("ticks") is not None
                 else ContinuousNorm(entry["vmin"], entry["vmax"],
                                      kind=entry.get("norm", "linear"),
                                      center=entry.get("center")).ticks(n_ticks))
        max_tw = max((measure_text(_fmt_tick(t), tick_size) for t in ticks), default=0.0)
        strip_col_w = _LEGSPEC["gradient_width"] + _FRAME["tick_length"] + _FRAME["tick_pad"] + max_tw
        max_w = max(max_w, strip_col_w)
        total_h += _LEGSPEC["gradient_height"]
        if i < len(cont_entries) - 1:
            total_h += _LEGSPEC["section_gap"]
    return max_w, total_h


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
    n_ticks = _adaptive_n_ticks(_LEGSPEC["gradient_height"])

    max_w = 0.0
    total_h = 2 * pad_y
    for gi, g in enumerate(groups):
        if g["header"]:
            max_w = max(max_w, measure_text(g["header"], label_size))
            total_h += header_h
        for entry in g["cont"]:
            label = entry.get("label")
            if label:
                max_w = max(max_w, measure_text(label, tick_size))
                total_h += tick_size + 4
            ticks = (list(entry["ticks"]) if entry.get("ticks") is not None
                     else ContinuousNorm(entry["vmin"], entry["vmax"],
                                          kind=entry.get("norm", "linear"),
                                          center=entry.get("center")).ticks(n_ticks))
            max_tw = max((measure_text(_fmt_tick(t), tick_size) for t in ticks), default=0.0)
            strip_col_w = _LEGSPEC["gradient_width"] + _FRAME["tick_length"] + _FRAME["tick_pad"] + max_tw
            max_w = max(max_w, strip_col_w)
            total_h += _LEGSPEC["gradient_height"]
        if g["cont"] and g["disc"]:
            total_h += _LEGSPEC["section_gap"]
        sub_groups = _partition_by_group(g["disc"], lambda e: e.get("group"))
        for si, (sub_name, sub_entries) in enumerate(sub_groups):
            if sub_name:
                max_w = max(max_w, measure_text(str(sub_name), label_size))
                total_h += header_h
            for entry in sub_entries:
                disc_w = sw + 6 + measure_text(entry["label"], tick_size)
                max_w = max(max_w, disc_w)
            total_h += len(sub_entries) * row_h
            if si < len(sub_groups) - 1:
                total_h += _LEGSPEC["section_gap"]
        if gi < len(groups) - 1:
            total_h += _LEGSPEC["section_gap"]

    return max_w + 2 * pad_x, total_h


def _size_legends(root: Chart, states: dict[int, dict]) -> None:
    """Pre-render pass: override each legend leaf's intrinsic _fig canvas
    size with its content-driven size, except where the user passed
    explicit `canvas_width=` / `canvas_height=` to `pt.legend(...)`."""
    from ._layout_engine import _iter_leaves  # avoid circular import at module load
    data_leaves = [l for l in _iter_leaves(root) if l._leaf_kind == "data"]
    for leaf in _iter_leaves(root):
        if leaf._leaf_kind != "legend":
            continue
        sources = leaf._legend_sources or data_leaves
        cw, ch = _legend_content_size(leaf, sources, states)
        if leaf._legend_user_width is None:
            leaf._canvas_width = max(1, int(round(cw)))
        if leaf._legend_user_height is None:
            leaf._canvas_height = max(1, int(round(ch)))


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
    tick_size = _FONTSPEC["tick_size"]
    label_size = _FONTSPEC["label_size"]
    text_color = _FONTSPEC["color"]
    header_h = label_size + 4

    parts = []
    cy = pad_y
    for gi, g in enumerate(groups):
        if g["header"]:
            parts.append(text_path(g["header"], pad_x, cy + label_size,
                                    label_size, anchor="start", color=text_color))
            cy += header_h
        for entry in g["cont"]:
            entry_label_h = (tick_size + 4) if entry.get("label") else 0
            parts.append(_render_continuous_entry(entry, pad_x, cy))
            cy += entry_label_h + _LEGSPEC["gradient_height"]
        if g["cont"] and g["disc"]:
            cy += _LEGSPEC["section_gap"]
        # Partition entries by their `group` field so an artist
        # contributing multiple aesthetics (color + size + shape) renders
        # each aesthetic as its own labeled block — entries with the
        # same group key cluster together even across artist records.
        sub_groups = _partition_by_group(g["disc"], lambda e: e.get("group"))
        for si, (sub_name, sub_entries) in enumerate(sub_groups):
            if sub_name:
                parts.append(text_path(str(sub_name), pad_x, cy + label_size,
                                       label_size, anchor="start",
                                       color=text_color))
                cy += header_h
            for i, entry in enumerate(sub_entries):
                ry = cy + i * row_h + row_h / 2
                parts.append(_render_discrete_entry(entry, entry["_a"],
                                                    _swatch_ctx, pad_x, ry))
            cy += len(sub_entries) * row_h
            if si < len(sub_groups) - 1:
                cy += _LEGSPEC["section_gap"]
        if gi < len(groups) - 1:
            cy += _LEGSPEC["section_gap"]

    return ''.join(parts)


def _render_standalone_legend(leaf: Chart) -> str:
    """Render a legend not part of any parent — wraps the leaf render in
    an outer <svg>. Standalone with explicit sources requires replaying
    + color-assigning those sources, which lands when grouping does
    (commit 5). For now this draws an empty placeholder rect."""
    w, h = leaf._canvas_width, leaf._canvas_height
    inner = rect(0.5, 0.5, w - 1, h - 1,
                 stroke="#bbb", dash="4,3")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family="{_FONTSPEC["family"]}" font-size="11" '
            f'style="background:{_FIGSPEC["background"]}">{inner}</svg>')
