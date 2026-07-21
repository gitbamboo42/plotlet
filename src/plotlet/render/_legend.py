"""Legend rendering — harvest entries from source panels and emit.

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

The `pt.legend(...)` factory that *creates* legend leaves lives in the
recording half (`legend.py`); this module only consumes render-tree
nodes.
"""
from __future__ import annotations

from ..draw import colormap, ContinuousNorm, resolve_color
from ..registry import RenderContext, get_artist
from ..draw import cap_height, measure_text
from ..draw import coord, rect, segment, text_path
from .. import _regions
from ..scales import _fmt_tick
from .._spec import _D, _DASH, _FONTSPEC, _FRAME, _LEGSPEC


def _adaptive_n_ticks(strip_h: float) -> int:
    """Cap tick count for short strips so labels (~11 px tall each) don't
    crowd. Mirrors the axis-tick-density rule in emit._render_inner."""
    return max(2, min(5, int(strip_h // 18)))


def _swatch_ctx(a: dict) -> RenderContext:
    """Minimal context for an entry's `paint` callback — only the fields swatch helpers
    actually read (defaults, dash, color). x/y scales aren't relevant."""
    return RenderContext(
        x_scale=None, y_scale=None, iw=0, ih=0,
        color=a["_color"], defaults=_D, dash=_DASH,
    )


# Aesthetic keys a per-artist `legend={...}` dict may override for swatch
# painting — ggplot2's `override.aes`. Applied at harvest time
# (`_legend_source_artist`) so every paint callback sees the overridden
# values whether it reads the record's opts or closure-captured them at
# emission; the plot itself is untouched. `glyph` is not in this set —
# it swaps the swatch drawing entirely and is handled at paint time in
# `_render_discrete_entry`.
_SWATCH_AES = ("alpha", "size", "marker", "markersize", "linewidth", "linestyle")


def _legend_source_artist(a: dict) -> dict:
    """The record to harvest an artist's legend entries from: a shallow
    copy with `legend={...}` aesthetic overrides merged into opts, or the
    record itself when there are none. `c.add_scatter(..., alpha=0.2,
    legend={"alpha": 1})` plots translucent points but paints an opaque
    legend key."""
    legend_opts = (a.get("opts") or {}).get("legend") or {}
    overrides = {k: legend_opts[k] for k in _SWATCH_AES if k in legend_opts}
    if not overrides:
        return a
    return {**a, "opts": {**a["opts"], **overrides}}


def _manual_entry(e: dict) -> dict:
    """A free-form `entries=` dict → the harvested-entry shape. The `_a`
    stub stands in for the source artist that manual entries don't have;
    the default rect-swatch paint path only reads its `opts`/`_color`."""
    entry = dict(e)
    entry["color"] = resolve_color(entry["color"])
    entry["_a"] = {"type": "_manual", "opts": {}, "_color": entry["color"]}
    return entry


def _build_groups(sources: list, states: dict[int, dict],
                  names: dict, group_by_chart: bool,
                  reverse: bool = False, manual: list | None = None) -> list[dict]:
    """Collect entries per source and decide each section's header.

    Each returned dict is `{"header": str|None, "cont": [...], "disc": [...]}`.
    `header` is `None` either because the user explicitly hid it via
    `names[src] = None`, the source has no `title`, grouping is off, or
    a continuous entry already carries its own `legend["label"]` (the
    chart title would just stack a second redundant caption above the
    gradient). Sources contributing zero entries are skipped entirely.

    `reverse=True` flips each section's discrete entry order; `manual`
    entries (`pt.legend(entries=)`) form one final headerless section."""
    raw = []
    for src in sources:
        state = states.get(id(src))
        if state is None:
            continue
        cont, disc = [], []
        for a in state["artists"]:
            spec = get_artist(a["type"])
            if spec is None:
                continue
            a = _legend_source_artist(a)
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
            header = state.get("title")
        raw.append({"header": header, "cont": cont, "disc": disc})

    if not group_by_chart and raw:
        raw = [{
            "header": None,
            "cont": [c for g in raw for c in g["cont"]],
            "disc": [d for g in raw for d in g["disc"]],
        }]
    if manual:
        raw.append({"header": None, "cont": [],
                    "disc": [_manual_entry(e) for e in manual]})
    if reverse:
        for g in raw:
            g["disc"] = g["disc"][::-1]
    return raw


def _partition_by_group(entries, key):
    """Partition a flat list into [(group_name, [items]), ...] runs by
    each item's group key. Unlike a consecutive-only grouping, items
    with the same key are collected together even when separated by
    intervening items — so multi-aesthetic legends stack cleanly
    (all color entries together, all size entries together, etc.)
    regardless of which artist record contributed them.

    None-keyed entries (un-grouped) stay first in their relative order.
    Named groups follow, ordered by first-appearance."""
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


def _entry_columns(entries: list, ncols: int) -> list[list]:
    """Split a discrete entry list into `ncols` columns, filled
    down-then-across (matplotlib / ggplot2 fill order): ceil(N / ncols)
    rows per column. Fewer real columns come back when there aren't
    enough entries to fill them all."""
    if ncols <= 1 or not entries:
        return [entries]
    rows = -(-len(entries) // ncols)
    return [entries[i:i + rows] for i in range(0, len(entries), rows)]


def _render_discrete_entry(entry: dict, a: dict, ctx_for,
                           x: float, y_mid: float) -> str:
    """One discrete legend row: swatch + label. Shared between the inline
    legend (emit._render_inner) and the standalone legend leaf
    (_render_legend) so swatch behavior — paint callback, default color,
    alpha aesthetic, `legend={"glyph": ...}` override — stays in one place.

    `a` is the source artist (needed by paint callbacks). `ctx_for(a)`
    builds the RenderContext for that callback; standalone uses
    `_swatch_ctx`, inline uses the panel's own draw context.

    An artist call carrying `legend={"glyph": "rect"}` gets the standard
    rect swatch instead of its own `paint` — the readable key when the
    plot mark is tiny (ggplot2's `key_glyph = "rect"`). Grouped entries
    (aesthetic guides like scatter's size dots) are exempt: a uniform
    rect would erase the very encoding they exist to show. Aesthetic
    overrides (`legend={"alpha": 1, ...}`, see `_SWATCH_AES`) don't
    appear here — they were merged into the record's opts at harvest by
    `_legend_source_artist`, before `paint` was even created."""
    sw = _LEGSPEC["swatch_width"]
    # One canonical swatch bbox per entry, regardless of what `paint`
    # actually draws — a line, a 4-px scatter dot, a 14-px scatter dot,
    # and a default rect should all show the same diagram footprint.
    # Sized to the legend row so the biggest possible swatch (large
    # size-graded marker) still fits inside; we record the rect manually
    # and call `paint` outside any tag context so its primitives don't
    # add their own size-varying bboxes.
    row_h = _LEGSPEC["row_height"]
    _regions.record("rect", (x, y_mid - row_h / 2, sw, row_h),
                    name="legend-mark")
    paint = entry.get("paint")
    legend_opts = (a.get("opts") or {}).get("legend") or {}
    glyph = legend_opts.get("glyph")
    if glyph not in (None, "rect"):
        raise ValueError(
            f"legend={{'glyph': {glyph!r}}} — 'rect' is the only supported "
            f"glyph override."
        )
    if glyph == "rect" and entry.get("group") is None:
        paint = None
    if paint is not None:
        swatch = paint(a, ctx_for(a), x, y_mid)
    else:
        alpha = entry.get("alpha", 1)
        if entry.get("group") is None:
            alpha = legend_opts.get("alpha", alpha)
        swatch = rect(x, y_mid - 5, sw, 10,
                      fill=entry["color"], alpha=alpha)
    label = text_path(entry["label"], x + sw + _LEGSPEC["swatch_label_gap"], y_mid + 4,
                      _FONTSPEC["tick_size"], anchor="start",
                      color=_FONTSPEC["color"], tag="legend-text")
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
    label_h = tick_size + _LEGSPEC["gradient_label_pad"] if label_text else 0
    if label_text:
        parts.append(text_path(label_text, x, y + tick_size,
                                tick_size, anchor="start", color=text_color,
                                tag="legend-header"))

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
    # The gradient itself is many sub-pixel bands above; the bordering
    # rect captures the strip as one chrome region so the diagram /
    # overlap-check sees "the colorbar" as a single bbox instead of 33
    # tiny band rects.
    parts.append(rect(x, strip_y, _LEGSPEC["gradient_width"], strip_h,
                      stroke=_FRAME["color"], stroke_width=_FRAME["width"],
                      tag="legend-mark"))

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
                                tick_size, anchor=label_anchor, color=text_color,
                                tag="legend-text"))
    return "".join(parts)


def _h_gradient_geometry(entry: dict):
    """Shared geometry for one horizontal gradient strip: the norm, tick
    values, and how far the centered tick labels overhang past each strip
    end (after the same inward baseline bias the vertical strip applies).
    Sizing and painting both call this so they can't drift apart."""
    tick_size = _FONTSPEC["tick_size"]
    length = float(_LEGSPEC["gradient_length"])
    norm = ContinuousNorm(entry["vmin"], entry["vmax"],
                           kind=entry.get("norm", "linear"),
                           center=entry.get("center"))
    n = max(2, min(7, int(length // 45)))
    ticks = (list(entry["ticks"]) if entry.get("ticks") is not None
             else norm.ticks(n))
    mid = length / 2
    over_l = over_r = 0.0
    for t in ticks:
        tx = norm.to_unit(t) * length
        bias = 4 * (mid - tx) / mid if mid > 0 else 0.0
        half = measure_text(_fmt_tick(t), tick_size) / 2
        over_l = max(over_l, half - (tx + bias))
        over_r = max(over_r, tx + bias + half - length)
    return norm, ticks, over_l, over_r


def _render_continuous_entry_h(entry: dict, x: float, y: float) -> str:
    """Horizontal variant of `_render_continuous_entry`: optional label
    above, then a gradient strip of fixed length (`legend.gradient_length`)
    running vmin-left → vmax-right, ticks below the strip. `x` is the
    block's left edge — the strip starts `over_l` further right so edge
    tick labels stay inside the block."""
    parts = []
    tick_size = _FONTSPEC["tick_size"]
    text_color = _FONTSPEC["color"]
    length = float(_LEGSPEC["gradient_length"])
    thick = _LEGSPEC["gradient_width"]
    norm, ticks, over_l, _ = _h_gradient_geometry(entry)
    x0 = x + over_l
    label_text = entry.get("label")
    label_h = tick_size + _LEGSPEC["gradient_label_pad"] if label_text else 0
    if label_text:
        parts.append(text_path(label_text, x0, y + tick_size,
                                tick_size, anchor="start", color=text_color,
                                tag="legend-header"))

    strip_y = y + label_h
    cm = colormap(entry["cmap"])
    n_bands = _LEGSPEC["gradient_n_stops"] + 1
    band_w = length / n_bands
    for i in range(n_bands):
        # i=0 at left → vmin color; same rect-band construction (and AA
        # overlap) as the vertical strip — see _render_continuous_entry.
        r, g, b = cm(i / _LEGSPEC["gradient_n_stops"])
        w = band_w + (1.0 if i < n_bands - 1 else 0.0)
        parts.append(rect(x0 + i * band_w, strip_y, w, thick,
                          fill=f"rgb({r},{g},{b})"))
    parts.append(rect(x0, strip_y, length, thick,
                      stroke=_FRAME["color"], stroke_width=_FRAME["width"],
                      tag="legend-mark"))

    ty0 = strip_y + thick
    ty1 = ty0 + _FRAME["tick_length"]
    base_y = ty1 + _FRAME["tick_pad"] + cap_height(tick_size)
    mid = length / 2
    for t in ticks:
        tx = x0 + norm.to_unit(t) * length
        parts.append(segment(tx, ty0, tx, ty1,
                             color=_FRAME["color"], width=_FRAME["width"]))
        bias = 4 * (x0 + mid - tx) / mid if mid > 0 else 0.0
        parts.append(text_path(_fmt_tick(t), tx + bias, base_y,
                                tick_size, anchor="middle", color=text_color,
                                tag="legend-text"))
    return "".join(parts)


def _h_gradient_entry_height(entry: dict) -> float:
    """Block height of one horizontal gradient entry — label band (if
    any) + strip thickness + tick + tick-label band."""
    tick_size = _FONTSPEC["tick_size"]
    label_h = tick_size + _LEGSPEC["gradient_label_pad"] if entry.get("label") else 0
    return (label_h + _LEGSPEC["gradient_width"] + _FRAME["tick_length"]
            + _FRAME["tick_pad"] + tick_size)


def _inline_gradient_block_size_h(cont_entries: list[dict]) -> tuple[float, float]:
    """Horizontal counterpart of `_inline_gradient_block_size` — strips
    stack vertically, each `legend.gradient_length` long plus whatever
    the edge tick labels overhang."""
    if not cont_entries:
        return 0, 0
    tick_size = _FONTSPEC["tick_size"]
    length = float(_LEGSPEC["gradient_length"])
    max_w = 0.0
    total_h = 0.0
    for i, entry in enumerate(cont_entries):
        _, _, over_l, over_r = _h_gradient_geometry(entry)
        label = entry.get("label")
        if label:
            max_w = max(max_w, over_l + measure_text(label, tick_size))
        max_w = max(max_w, over_l + length + over_r)
        total_h += _h_gradient_entry_height(entry)
        if i < len(cont_entries) - 1:
            total_h += _LEGSPEC["section_gap"]
    return max_w, total_h


def _inline_gradient_block_size(cont_entries: list[dict]) -> tuple[float, float]:
    """Block (width, height) for a vertical stack of gradient strips —
    used by the in-frame inline-colorbar path. Mirrors the per-entry
    geometry inside `_legend_content_size` but with no header, no
    discrete rows, and no outer padding (the in-frame block does its
    own positioning relative to the data edge).

    Returns plain `0, 0` (int) for an empty input so callers that add
    to an integer `lh` stay int (no float promotion)."""
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
            total_h += tick_size + _LEGSPEC["gradient_label_pad"]
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


def _legend_content_size(leaf, sources: list,
                         states: dict[int, dict]) -> tuple[float, float]:
    """Compute the legend leaf's content-driven (width, height).

    Width = max content width across sections (gradient column +
    ticks/labels for continuous, swatch + label for discrete, plus
    headers and any per-entry above-strip label) + side padding.

    Height = sum of section heights + inter-section gaps + top/bottom
    padding. Strip height is fixed at `legend.gradient_height` per
    continuous entry — independent of source plot height.

    With `ncols > 1` each discrete block spreads over columns (sized
    per-column to its widest entry, `legend.column_gap` apart) and
    contributes only its first column's row count to the height —
    mirror of the paint geometry in `_render_legend`."""
    names = leaf._legend_names or {}
    group_by_chart = leaf._legend_group_by_chart
    groups = _build_groups(sources, states, names, group_by_chart,
                           reverse=leaf._legend_reverse,
                           manual=leaf._legend_manual)
    if not groups:
        return 1.0, 1.0

    pad_x = _LEGSPEC["pad_x"]
    pad_y = _LEGSPEC["pad_y"]
    row_h = _LEGSPEC["row_height"]
    sw = _LEGSPEC["swatch_width"]
    tick_size = _FONTSPEC["tick_size"]
    label_size = _FONTSPEC["label_size"]
    header_h = label_size + _LEGSPEC["header_pad"]
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
                total_h += tick_size + _LEGSPEC["gradient_label_pad"]
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
            cols = _entry_columns(sub_entries, leaf._legend_ncols)
            block_w = sum(
                max(sw + _LEGSPEC["swatch_label_gap"] + measure_text(e["label"], tick_size) for e in col)
                for col in cols
            ) + (len(cols) - 1) * _LEGSPEC["column_gap"]
            max_w = max(max_w, block_w)
            total_h += len(cols[0]) * row_h
            if si < len(sub_groups) - 1:
                total_h += _LEGSPEC["section_gap"]
        if gi < len(groups) - 1:
            total_h += _LEGSPEC["section_gap"]

    return max_w + 2 * pad_x, total_h


def _size_legends(root, states: dict[int, dict]) -> None:
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


def _render_legend(leaf, w: float, h: float,
                   states: dict[int, dict],
                   data_leaves: list) -> str:
    """Render the legend leaf's content into its allocated rect.

    Sources default to all data leaves in the layout; explicit
    `pt.legend(a, b)` narrows to those. With grouping on (the default),
    each source becomes a section with its `title` as header; continuous
    entries (gradient strips) stack above discrete entries (swatch +
    label rows) within each section.

    Strip height is fixed at `legend.gradient_height` (independent of
    `h`); when the parent allocates more vertical space than the content
    needs, the content is top-aligned and the surplus sits below.

    `pt.legend(ncols=N)` wraps each discrete block into columns filled
    down-then-across; headers and gradient strips span the full width."""
    sources = leaf._legend_sources or data_leaves
    names = leaf._legend_names or {}
    group_by_chart = leaf._legend_group_by_chart
    valign = leaf._legend_valign

    groups = _build_groups(sources, states, names, group_by_chart,
                           reverse=leaf._legend_reverse,
                           manual=leaf._legend_manual)
    if not groups:
        return ''

    pad_x = _LEGSPEC["pad_x"]
    pad_y = _LEGSPEC["pad_y"]
    row_h = _LEGSPEC["row_height"]
    sw = _LEGSPEC["swatch_width"]
    tick_size = _FONTSPEC["tick_size"]
    label_size = _FONTSPEC["label_size"]
    text_color = _FONTSPEC["color"]
    header_h = label_size + _LEGSPEC["header_pad"]

    # valign="middle" slides the whole block down by half the surplus.
    # Computed up front (via the mirror `_legend_content_size`) so region
    # bboxes recorded during emission can carry the same offset — a
    # post-hoc <g translate> alone would leave them stale.
    if valign == "middle":
        content_h = _legend_content_size(leaf, sources, states)[1]
        dy = max(0.0, (h - content_h) / 2)
    else:
        dy = 0.0

    with _regions.translate(0, dy):
        body = _emit_legend_body(groups, leaf, states, pad_x, pad_y, row_h,
                                 sw, tick_size, label_size, text_color,
                                 header_h)
    if dy > 0:
        body = f'<g transform="translate(0,{coord(dy)})">{body}</g>'
    return body


def _emit_legend_body(groups, leaf, states, pad_x, pad_y, row_h,
                      sw, tick_size, label_size, text_color, header_h):
    parts = []
    cy = pad_y
    for gi, g in enumerate(groups):
        if g["header"]:
            parts.append(text_path(g["header"], pad_x, cy + label_size,
                                    label_size, anchor="start", color=text_color,
                                    tag="legend-header"))
            cy += header_h
        for entry in g["cont"]:
            entry_label_h = (tick_size + _LEGSPEC["gradient_label_pad"]) if entry.get("label") else 0
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
                                       color=text_color,
                                       tag="legend-header"))
                cy += header_h
            cols = _entry_columns(sub_entries, leaf._legend_ncols)
            cx = pad_x
            for col in cols:
                for i, entry in enumerate(col):
                    ry = cy + i * row_h + row_h / 2
                    parts.append(_render_discrete_entry(entry, entry["_a"],
                                                        _swatch_ctx, cx, ry))
                cx += (max(sw + _LEGSPEC["swatch_label_gap"] + measure_text(e["label"], tick_size)
                           for e in col) + _LEGSPEC["column_gap"])
            cy += len(cols[0]) * row_h
            if si < len(sub_groups) - 1:
                cy += _LEGSPEC["section_gap"]
        if gi < len(groups) - 1:
            cy += _LEGSPEC["section_gap"]

    return ''.join(parts)
