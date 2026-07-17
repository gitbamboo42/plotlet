"""SVG emission — the transcribe stage of the render pipeline.

Everything here writes SVG from decisions already made: `_panel_open`
opens a panel `<g>` with its structural data attrs, `_render_inner`
fills it (grid → artists → chrome → labels → legend → insets), and the
attr helpers encode the AI-readable `data-plotlet-*` schema. Resolution
(replay, domains, margins, decided chrome flags) lives in `_resolution.py` and
`_layout_engine.py`; the split keeps "emit never re-resolves"
(`docs/ARCHITECTURE.md`) visible in the module layout.

The `from ._resolution import ...` list below is the contract's edge, enforced
by `tests/test_import_boundary.py`: every *function* in it is one the
resolution pass also calls (`_required_margin`, `_resolve_panels`),
so re-running it here is idempotent — emit re-derives values the
resolved IR already carries (necessary because the circular coord's
per-leaf path reaches `_render_inner` with freshly replayed states),
never new ones. Widening the list means emit is about to make a
decision of its own — put the decided flag in `_chrome_visibility` /
resolution instead.
"""
from __future__ import annotations

import html
import json
from importlib.metadata import version as _pkg_version
from types import SimpleNamespace

from .._spec import (
    SPEC, _GRIDSPEC, _FONTSPEC, _LEGSPEC, _LAYOUTSPEC, _D, _DASH,
)
from ..draw import resolve_color
from ..draw import measure_text
from ..draw import coord, rect, segment, text_path
from .. import _regions
from ..registry import RenderContext, get_artist, _COORD_SUPPORT
from . import _chrome
from ._resolution import (
    _INSIDE_POSITIONS, _PanelOpts,
    _inline_legend_layout, _prebin_hist, _resolve_panel_inputs,
    _stamp_artist_colors,
)

# ---------------------------------------------------------------------------
# AI-readable SVG attrs — schema and helpers
# ---------------------------------------------------------------------------
# Every plotlet SVG carries `data-plotlet-*` attributes describing plot type,
# axes, scales, ranges, and series labels (see docs/AI_ATTRS.md). Schema is
# semver-stable, declared via `data-plotlet-schema` on the root.
_SCHEMA_VERSION = "2"
# Read from package metadata (pyproject.toml) so there's a single source
# of truth for the version. Independent of `__init__.__version__` to
# avoid a circular import.
_PLOTLET_VERSION = _pkg_version("plotlet")


def _attr_str(v) -> str:
    """Stringify a value for a data-plotlet-* attribute. Floats use 10 sig
    figs — plenty for AI consumption and round-trip within 1e-10, while
    truncating float noise that drifts across numpy/scipy builds. Ints
    and strings stringify naturally; bools are "true"/"false". Lists
    are not supported here — they go in <metadata>."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.10g}"
    return str(v)


def _attrs_str(d: dict) -> str:
    """Encode `{"key": val}` as ` data-plotlet-key="val"` pairs, HTML-escaped.
    Keys with `None` values are skipped. Empty dict -> ''."""
    out = []
    for k, v in d.items():
        if v is None:
            continue
        out.append(f' data-plotlet-{k}="{html.escape(_attr_str(v), quote=True)}"')
    return "".join(out)


def _category_metadata(name: str, cats) -> str:
    """Emit a `<metadata data-plotlet-payload="name">` block carrying a JSON
    array of category labels. Wrapped in CDATA so labels can contain `<`
    `>` `&` without XML escaping. `json.dumps` emits `]]>` verbatim when a
    label contains it, so any occurrence is split across two CDATA sections
    — after the split, every `]]>` in the block is immediately followed by
    `<![CDATA[`, so the terminator sequence appears exactly once."""
    body = json.dumps(list(cats), ensure_ascii=False, separators=(",", ":"))
    body = body.replace("]]>", "]]]]><![CDATA[>")
    return (f'<metadata data-plotlet-payload="{name}">'
            f'<![CDATA[{body}]]></metadata>')


def _figure_root_attrs() -> str:
    """Attrs for the outer `<svg>`. Every plotlet SVG carries `kind="layout"`
    — a lone chart is just a 1x1 layout, so there's no separate figure
    kind anymore."""
    return _attrs_str({
        "version": _PLOTLET_VERSION,
        "schema":  _SCHEMA_VERSION,
        "kind":    "layout",
    })


def _panel_attrs_and_meta(state, M, iw, ih, x_axis, y_axis,
                          panel_bbox: tuple[float, float, float, float]
                          ) -> tuple[str, str]:
    """Build (attrs, metadata) for one panel <g>. `attrs` is the attribute
    string spliced into the open tag; `metadata` is one or more <metadata>
    children placed at the start of the <g> body (currently: x/y category
    lists)."""
    attrs = {"kind": "panel"}
    if state["title"]:  attrs["title"]  = state["title"]
    if state["xlabel"]: attrs["xlabel"] = state["xlabel"]
    if state["ylabel"]: attrs["ylabel"] = state["ylabel"]
    attrs["xscale"] = x_axis.kind
    attrs["yscale"] = y_axis.kind

    if x_axis.kind != "category":
        attrs["xlim"] = f"{x_axis.lo:.10g},{x_axis.hi:.10g}"
    if y_axis.kind != "category":
        attrs["ylim"] = f"{y_axis.lo:.10g},{y_axis.hi:.10g}"
    if y_axis.flip:
        attrs["yflip"] = "true"

    # Panel bbox in figure-SVG coords: the full rect this panel occupies,
    # margins included. Standalone figures: (0, 0, W, H). Multi-panel
    # layouts: the (x, y, w, h) the parent allocated.
    px, py, pw, ph = panel_bbox
    attrs["panel-bbox"] = (
        f'{int(round(px))},{int(round(py))},'
        f'{int(round(pw))},{int(round(ph))}'
    )
    # Data-area rect in panel-local coords: (M.left, M.top) within the
    # panel bbox, with size (iw, ih). To get figure-SVG coords, add the
    # panel bbox's (px, py).
    attrs["data-area"] = (
        f'{int(round(M["left"]))},{int(round(M["top"]))},'
        f'{int(round(iw))},{int(round(ih))}'
    )

    meta_parts = []
    if x_axis.kind == "category" and x_axis.cats:
        meta_parts.append(_category_metadata("xcategories", x_axis.cats))
    if y_axis.kind == "category" and y_axis.cats:
        meta_parts.append(_category_metadata("ycategories", y_axis.cats))

    return _attrs_str(attrs), "".join(meta_parts)


def _wrap_artist(a, idx: int, body: str) -> str:
    """Wrap one artist's draw fragment in `<g class="plotlet-artist" ...>`.
    Common attrs (type, index, label, color) come from the artist record;
    type-specific attrs come from the registered spec's `data_attrs`
    callback if it has one."""
    spec = get_artist(a["type"])
    attrs = {"type": a["type"], "index": idx}
    label = a["opts"].get("label")
    if label:
        attrs["label"] = label
    if a.get("_color"):
        attrs["color"] = a["_color"]
    if spec is not None and spec.data_attrs is not None:
        extra = spec.data_attrs(a)
        if extra:
            attrs.update(extra)
    return f'<g class="plotlet-artist"{_attrs_str(attrs)}>{body}</g>'


# ---------------------------------------------------------------------------
# pixel materialization — decided descriptors → closures
# ---------------------------------------------------------------------------

def _build_xy_scales(state, iw, ih, panel_opts: _PanelOpts):
    """Instantiate pixel-bound scales. `panel_opts.x_axis` / `y_axis` come
    from the layout pre-pass (share-equivalence class descriptor). y-category
    runs top-to-bottom (cats on rows); y-linear/log runs cartesian unless
    the descriptor requested a flip."""
    x_axis = panel_opts.x_axis
    y_axis = panel_opts.y_axis
    if x_axis.kind == "category" or not x_axis.flip:
        x_scale = x_axis.build(0, iw)
    else:
        x_scale = x_axis.build(iw, 0)
    if y_axis.kind == "category":
        y_scale = y_axis.build(0, ih)
    elif y_axis.flip:
        y_scale = y_axis.build(0, ih)
    else:
        y_scale = y_axis.build(ih, 0)
    x_is_cat = (x_axis.kind == "category")
    return x_scale, y_scale, x_is_cat


def _make_px_warp(project, iw, ih):
    """Build the Cartesian-pixel → projected-pixel closure handed to
    coord-native artists as `ctx.warp`. Normalizes x_px/iw → t and
    1 - y_px/ih → r (r is bottom-up; SVG y is top-down), then calls the
    coord's project. Returns None when there's no project to apply so
    artists can branch with a single `if ctx.warp`."""
    if project is None:
        return None
    def warp(x_px, y_px):
        t = x_px / iw
        r = 1.0 - y_px / ih
        return project(t, r)
    return warp


# ---------------------------------------------------------------------------
# render orchestrator — generic over the registry
# ---------------------------------------------------------------------------

def _panel_open(state, panel_opts: _PanelOpts, transform: str,
                M: dict, iw: float, ih: float,
                panel_bbox: tuple[float, float, float, float]) -> str:
    """Open a panel `<g>` with transform + structural data attrs, and emit
    any panel-level `<metadata>` children (currently x/y category lists).
    Returns a string ending mid-element — the caller appends
    `_render_inner(...)` then `</g>`."""
    x_axis = panel_opts.x_axis
    y_axis = panel_opts.y_axis
    attrs, meta = _panel_attrs_and_meta(state, M, iw, ih, x_axis, y_axis, panel_bbox)
    return f'<g transform="{transform}"{attrs}>{meta}'


def _emit_inline_legend_body(lw, lh, pos, cont, disc, horizontal, gradient_h,
                              ncols, pad_x, pad_y, row_h, sw, tick_size,
                              text_color, ctx_for) -> str:
    """Render the inline legend body — the part *inside* the
    `<g transform="translate(lx, ly)">` wrapper. Lives in its own
    function so the translate ctxmgr in `_render_inner` stays a
    2-liner instead of forcing 70 lines of indentation. No behavior
    change vs the previous inline form."""
    from ._legend import _render_continuous_entry, _render_discrete_entry
    parts = []
    is_gradient_only = bool(cont) and not disc
    if not is_gradient_only and pos in _INSIDE_POSITIONS:
        # Inside-position legends overlay the data area, so a
        # translucent background keeps text/swatches readable on top
        # of plot marks. No stroke — ggplot/vega-lite default look.
        # Outside positions skip the rect entirely.
        parts.append(rect(0, 0, lw, lh,
                          fill=_LEGSPEC["background"],
                          alpha=_LEGSPEC["opacity"]))
    if gradient_h:
        # Horizontal colorbar (gradient-only, outside top/bottom).
        from ._legend import (_h_gradient_entry_height,
                              _render_continuous_entry_h)
        cur_y = 0.0
        for i, (_, desc) in enumerate(cont):
            parts.append(_render_continuous_entry_h(desc, 0.0, cur_y))
            cur_y += _h_gradient_entry_height(desc)
            if i < len(cont) - 1:
                cur_y += _LEGSPEC["section_gap"]
        return ''.join(parts)
    if horizontal:
        # Discrete-only horizontal row. Entries left-to-right,
        # vertically centered. Spacer matches `_inline_legend_layout`.
        spacer = 2 * pad_x
        cx = pad_x
        ry = pad_y + row_h / 2
        for a, entry in disc:
            parts.append(_render_discrete_entry(entry, a, ctx_for, cx, ry))
            cx += sw + _LEGSPEC["swatch_label_gap"] + measure_text(entry["label"], tick_size) + spacer
        return ''.join(parts)
    # Vertical layout: gradient strips on top, discrete rows below.
    # Ticks face away from the data area — right-position gets
    # tick_side="right", left-position "left". Mixed (gradient +
    # discrete) defaults to "right"; the rare left-position mixed
    # case ends up with ticks pointing toward the discrete entries,
    # which is acceptable for that uncommon combination.
    if is_gradient_only and pos == "left":
        tick_side = "left"
        strip_x = lw - _LEGSPEC["gradient_width"]
        cur_y = 0.0
    elif is_gradient_only:
        tick_side = "right"
        strip_x = 0.0
        cur_y = 0.0
    else:
        tick_side = "right"
        strip_x = pad_x
        cur_y = float(pad_y)
    for i, (_, desc) in enumerate(cont):
        entry_h = (tick_size + _LEGSPEC["gradient_label_pad"] if desc.get("label") else 0) \
                  + _LEGSPEC["gradient_height"]
        parts.append(_render_continuous_entry(desc, strip_x, cur_y, tick_side))
        cur_y += entry_h
        if i < len(cont) - 1:
            cur_y += _LEGSPEC["section_gap"]
    if cont and disc:
        cur_y += _LEGSPEC["section_gap"]
    # Partition entries by their `group` field so a multi-aesthetic
    # artist (color + size + shape) renders each aesthetic as its own
    # block with a header — entries with the same key cluster together
    # across artist records.
    from ._legend import _entry_columns, _partition_by_group
    sub_groups = _partition_by_group(disc, lambda ae: ae[1].get("group"))
    label_size = _FONTSPEC["label_size"]
    sub_header_h = label_size + _LEGSPEC["header_pad"]
    for si, (sub_name, sub_items) in enumerate(sub_groups):
        if sub_name:
            parts.append(text_path(str(sub_name), pad_x,
                                   cur_y + label_size,
                                   label_size, anchor="start",
                                   color=text_color,
                                   tag="legend-header"))
            cur_y += sub_header_h
        cols = _entry_columns(sub_items, ncols)
        cx = pad_x
        for col in cols:
            for i, (a, entry) in enumerate(col):
                ry = cur_y + i * row_h + row_h / 2
                parts.append(_render_discrete_entry(entry, a, ctx_for, cx, ry))
            cx += (max(sw + _LEGSPEC["swatch_label_gap"] + measure_text(e["label"], tick_size)
                       for _, e in col) + _LEGSPEC["column_gap"])
        cur_y += len(cols[0]) * row_h
        if si < len(sub_groups) - 1:
            cur_y += _LEGSPEC["section_gap"]
    return ''.join(parts)


def _render_inner(state, iw, ih, M, panel_opts: _PanelOpts, *, clip_counter):
    """Body fragment for one panel — the string appended inside the panel
    `<g>` opened by `_panel_open`. Coordinates are panel-local: data area
    at `(0,0)`→`(iw,ih)`, chrome placed relative to `M`. `panel_opts`
    supplies axis descriptors and joined-side flags. `clip_counter` is
    shared across panels so coord-clip ids stay unique in the SVG."""
    _prebin_hist(state)

    x_scale, y_scale, x_is_cat = _build_xy_scales(state, iw, ih, panel_opts)
    inp = _resolve_panel_inputs(state, x_scale=x_scale, y_scale=y_scale,
                                 dw=iw, dh=ih, layout_opts=panel_opts)
    # Label bands + raw chrome stack — both passes share the chrome dict
    # so we only compute it once per render. `label_bands` feeds the
    # inline-legend block; `chrome` feeds frame-label placement and the
    # top-legend gap below.
    label_bands, chrome = _chrome.label_band_sizes(state, inp, iw, ih)
    _x_sec = state["x_sectors"]
    _y_sec = state["y_sectors"]

    # Color assignment — normally already stamped at resolve time
    # (`_resolve_panels` calls `_stamp_artist_colors` so the resolved
    # IR carries final colors); recomputed here because this function
    # is also reached with freshly replayed states (the circular coord's
    # per-leaf render). Idempotent — identical values either way. Runs
    # before the legend harvest below: entries capture `_color` at
    # harvest time (a `legend={...}` override harvests from a *copy* of
    # the record, so later in-place stamping wouldn't reach it).
    _stamp_artist_colors(state)

    # In-frame legend geometry is computed up front because a top-position
    # legend sits between the title and the data area — the title's y
    # offset depends on it. For other positions / inside / no legend, the
    # title stays at `_PADSPEC["title"]`.
    leg = _inline_legend_layout(state, env=SimpleNamespace(
        x_scale=x_scale, y_scale=y_scale, iw=iw, ih=ih))
    legend_pos = leg["position"] if leg is not None else None
    legend_gap = _LAYOUTSPEC["legend_gap"]
    # `inner_gap_top` is the data-side gap below the top-position legend
    # — at least `legend_gap`, but expands to clear the top-side x-axis
    # chrome band when `xticks(side="top")`. None when no top legend is
    # in play.
    inner_gap_top = (max(chrome["top"], legend_gap)
                     if legend_pos == "top" else None)

    # Resolve the panel coordinate — always panel-level via c.coordinate(...).
    # Lifted above the grid block so the grid/spine/x-tick passes below can
    # check the coordinate's optional hooks (draw_x_frame, clip_path_d)
    # before emitting anything.
    _coord_object = state.get("coordinate")
    _coord_project = _coord_object({}, iw, ih) if _coord_object is not None else None

    _has_coord_frame   = _coord_object is not None and hasattr(_coord_object, "draw_frame")
    _has_svg_transform   = _coord_object is not None and hasattr(_coord_object, "svg_transform")
    _has_x_frame         = _coord_object is not None and hasattr(_coord_object, "draw_x_frame")
    _has_clip_d          = _coord_object is not None and hasattr(_coord_object, "clip_path_d")
    _has_x_sector_chrome = _coord_object is not None and hasattr(_coord_object, "draw_x_sector_chrome")

    # A coordinate that owns the x-axis (draw_x_frame) needs a matching
    # `draw_x_sector_chrome` to handle x-sectors; otherwise the Cartesian
    # vertical-divider chrome would land outside the coordinate.
    if _has_x_frame and _x_sec is not None and not _has_x_sector_chrome:
        raise NotImplementedError(
            "c.sectors(axis='x') with a coordinate that owns draw_x_frame "
            "requires the coordinate to implement draw_x_sector_chrome."
        )
    # y-sectors with a coord-owned x-axis (CircularCoordinate's concentric
    # bands case) is a different design and not yet supported.
    if _has_x_frame and _y_sec is not None:
        raise NotImplementedError(
            "c.sectors(axis='y') is not yet supported with a coordinate "
            "that owns the x-axis (e.g. CircularCoordinate)."
        )
    # Per-artist gate: each artist opts in via `declare_coord_support`
    # under the coord's short name (class name minus `Coordinate` suffix).
    # Vanilla Cartesian (no coord set) skips this gate entirely; non-affine
    # coords like CircularCoordinate only accept artists whose draw
    # forwards `project=ctx.warp`.
    if _coord_object is not None:
        coord_short = type(_coord_object).__name__.removesuffix("Coordinate")
        supported = _COORD_SUPPORT.get(coord_short, set())
        bad = sorted({a["type"] for a in state["artists"]
                      if a["type"] not in supported})
        if bad:
            coord_name = type(_coord_object).__name__
            raise NotImplementedError(
                f"{coord_name} ({coord_short!r}) doesn't support {bad}; "
                f"these artists aren't declared as renderable under it. "
                f"Supported under {coord_name}: {sorted(supported)}.\n"
                f"To add support: call "
                f"`pt.declare_coord_support({coord_short!r}, [...])` "
                f"listing the artists, and make sure each forwards "
                f"`project=ctx.warp` to every `draw.*` helper call in its "
                f"draw function."
            )

    # ---- emit body fragment ----
    parts = []

    if state["facecolor"] is not None:
        parts.append(rect(0, 0, iw, ih, fill=resolve_color(state["facecolor"])))

    # grid — straight Cartesian lines; suppressed when the coordinate owns
    # the x-axis (e.g. CircularCoordinate) because horizontals/verticals
    # render outside the ring after the warp would naturally apply.
    if state["grid"] and not _has_x_frame:
        gcol = _GRIDSPEC["color"]
        which = state["grid_which"]
        # Minor lines first so major lines paint on top where they meet.
        # grid(which="minor"/"both") is itself the explicit ask, so when
        # the user hasn't configured minor ticks the auto subdivisions
        # apply (ggplot behavior) — an explicit minor= list still wins.
        if which in ("minor", "both"):
            mw = _GRIDSPEC["minor_width"]; md = _GRIDSPEC["minor_dasharray"]
            if not x_is_cat:
                xm = state["x_minor"]
                for t in _chrome._resolve_minor_ticks(
                        xm if xm not in (None, False) else True,
                        x_scale, inp.x_ticks):
                    x = x_scale(t)
                    parts.append(segment(x, 0, x, ih,
                                         color=gcol, width=mw, dash=md))
            if panel_opts.y_axis.kind != "category":
                ym = state["y_minor"]
                for t in _chrome._resolve_minor_ticks(
                        ym if ym not in (None, False) else True,
                        y_scale, inp.y_ticks):
                    y = y_scale(t)
                    parts.append(segment(0, y, iw, y,
                                         color=gcol, width=mw, dash=md))
        if which in ("major", "both"):
            gw = _GRIDSPEC["width"]; gd = _GRIDSPEC["dasharray"]
            if not x_is_cat:
                for t in inp.x_ticks:
                    x = x_scale(t)
                    parts.append(segment(x, 0, x, ih,
                                         color=gcol, width=gw, dash=gd))
            for t in inp.y_ticks:
                y = y_scale(t)
                parts.append(segment(0, y, iw, y,
                                     color=gcol, width=gw, dash=gd))

    # build the render context once — passed to every draw call.
    # When svg_transform is present the coordinate mapping is handled at the
    # SVG group level; artists draw in Cartesian, so ctx.project stays None.
    # Non-affine coords expose `ctx.warp` (pixel-space convenience closure)
    # that artists pass to `draw.*` helpers; validation upstream guaranteed
    # every artist here is declared as a supporter of this coord, so we
    # always populate `warp` when the coord is non-affine.
    def _ctx_for(a):
        if _has_svg_transform or _coord_object is None:
            proj = None
            warp = None
        else:
            proj = _coord_object(a, iw, ih)
            warp = _make_px_warp(proj, iw, ih)
        return RenderContext(
            x_scale=x_scale, y_scale=y_scale, iw=iw, ih=ih,
            color=a["_color"], defaults=_D, dash=_DASH,
            project=proj, warp=warp,
        )

    # three-pass draw: background → data → foreground.
    # Each artist's body is wrapped in <g class="plotlet-artist" ...> so
    # AI consumers can read structural attrs (type, label, color, range,
    # etc.) without parsing geometry.
    by_layer = {"background": [], "data": [], "foreground": []}
    for idx, a in enumerate(state["artists"]):
        spec = get_artist(a["type"])
        if spec is None: continue
        by_layer[spec.layer].append((idx, a))
    clip_data = state.get("clip", True)

    # For coordinate frames the clip region is the projected data area,
    # not the Cartesian rectangle. By default we emit a polygon from the
    # four corners of the (t, r) unit square (correct for affine coords).
    # A coordinate can override via `clip_path_d` for non-affine shapes
    # (e.g. an annulus for CircularCoordinate); we apply clip-rule="evenodd"
    # so multi-subpath ds (outer + inner ring) describe a hole.
    _clip_id = None
    if (_has_coord_frame or _has_svg_transform) and clip_data:
        _clip_id = f"pc{next(clip_counter)}"
        if _has_clip_d:
            d = _coord_object.clip_path_d(iw, ih)
            parts.append(f'<defs><clipPath id="{_clip_id}">'
                         f'<path d="{d}" clip-rule="evenodd"/></clipPath></defs>')
        else:
            bl_x, bl_y = _coord_project(0.0, 0.0)
            tl_x, tl_y = _coord_project(0.0, 1.0)
            br_x, br_y = _coord_project(1.0, 0.0)
            tr_x, tr_y = _coord_project(1.0, 1.0)
            pts = (f"{coord(bl_x)},{coord(bl_y)} {coord(br_x)},{coord(br_y)} "
                   f"{coord(tr_x)},{coord(tr_y)} {coord(tl_x)},{coord(tl_y)}")
            parts.append(f'<defs><clipPath id="{_clip_id}">'
                         f'<polygon points="{pts}"/></clipPath></defs>')

    for layer in ("background", "data", "foreground"):
        if not by_layer[layer]:
            continue
        # Clip the data layer to the data area so an artist drawing
        # outside the visible xlim/ylim (zoom insets, explicit xlim that
        # excludes data) can't paint over tick labels or the parent.
        # Coordinate frames use a polygon <clipPath>; others use a nested
        # <svg> with overflow="hidden" (SVG1.1-safe rectangular clip).
        # Caller can opt out via `c.clip(False)`.
        if layer == "data" and clip_data:
            if _clip_id:
                parts.append(f'<g clip-path="url(#{_clip_id})">')
            else:
                parts.append(f'<svg x="0" y="0" width="{iw:.10g}" height="{ih:.10g}" overflow="hidden">')
            if _has_svg_transform:
                xfm = _coord_object.svg_transform(_coord_project, iw, ih)
                parts.append(f'<g transform="{xfm}">')

        # Each body is emitted in user-recording z-order. Under affine
        # coords the surrounding <g transform="..."> handles the mapping;
        # under non-affine coords artists projected through ctx.warp during
        # draw. Either way the body is plain SVG — no renderer-level rewrite.
        for idx, a in by_layer[layer]:
            spec = get_artist(a["type"])
            body = spec.draw(a, _ctx_for(a))
            parts.append(_wrap_artist(a, idx, body))

        if layer == "data" and clip_data:
            if _has_svg_transform:
                parts.append('</g>')
            parts.append('</g>' if _clip_id else '</svg>')

    parts.extend(_chrome.emit_chrome(
        state=state, inp=inp, iw=iw, ih=ih,
        coord_object=_coord_object, coord_project=_coord_project,
        has_coord_frame=_has_coord_frame, has_x_frame=_has_x_frame,
        has_x_sector_chrome=_has_x_sector_chrome,
        x_sec=_x_sec, y_sec=_y_sec,
    ))

    # Tick font + text color — used by the inline-legend block below
    # (colorbar tick labels, swatch labels). label_bands and chrome are
    # reused from the up-front label_band_sizes call.
    tick_size = _FONTSPEC["tick_size"]
    text_color = _FONTSPEC["color"]
    top_legend_outset = (leg["lh"] + legend_gap
                         if inner_gap_top is not None else 0)
    bottom_legend_outset = (leg["lh"] + legend_gap
                            if legend_pos == "bottom" else 0)
    parts.extend(_chrome.emit_frame_labels(
        state, inp, iw, ih, chrome, top_legend_outset=top_legend_outset,
        bottom_legend_outset=bottom_legend_outset,
    ))

    # legend — gather entries from every artist's legend_entries(a) and
    # gradient descriptors from legend_gradient(a). Multi-entry artists
    # (sankey, mosaic, ...) contribute one row per category; continuous
    # artists (imshow, hexbin, ...) contribute a vertical gradient strip
    # with ticks (inline colorbar).
    if leg is not None:
        lw = leg["lw"]
        lh = leg["lh"]
        horizontal = leg["horizontal"]
        disc = leg["disc"]
        cont = leg["cont"]
        row_h = _LEGSPEC["row_height"]
        pad_x = _LEGSPEC["pad_x"]
        pad_y = _LEGSPEC["pad_y"]
        sw    = _LEGSPEC["swatch_width"]
        pos = legend_pos
        gap = legend_gap
        if pos in ("right", "left", "top", "bottom"):
            # `top` puts the legend *between* the title (outer edge) and
            # data (inner edge); other sides put it beyond the axis
            # band. Hidden sides naturally collapse via `_chrome.label_band_sizes`
            # — when a side's title/labels are dropped (joined share-pair
            # or unset), the band shrinks and the legend moves inward.
            if pos == "right":
                lx, ly = iw + label_bands["right"] + gap, (ih - lh) / 2
            elif pos == "left":
                lx, ly = -(label_bands["left"] + gap + lw), (ih - lh) / 2
            elif pos == "top":
                lx, ly = (iw - lw) / 2, -(inner_gap_top + lh)
            else:  # "bottom"
                lx, ly = (iw - lw) / 2, ih + label_bands["bottom"] + gap
        else:
            # Inside-corner / center tokens — overlay the data area.
            off = _LEGSPEC["border_offset"]
            right_x = iw - lw - off
            bottom_y = ih - lh - off
            mid_x = (iw - lw) / 2
            mid_y = (ih - lh) / 2
            lx, ly = {
                "top-right":    (right_x, off),
                "top-left":     (off,     off),
                "bottom-right": (right_x, bottom_y),
                "bottom-left":  (off,     bottom_y),
                "center":       (mid_x,   mid_y),
            }[pos]
        transform = f'translate({coord(lx)},{coord(ly)})'
        parts.append(f'<g transform="{transform}">')
        # The translate puts the body's panel-local coords onto the
        # sink so chrome bboxes tagged inside `_render_discrete_entry`
        # / `_render_continuous_entry` (and the sub-header text_path
        # in the body) land at outer-SVG positions.
        with _regions.translate(lx, ly):
            parts.append(_emit_inline_legend_body(
                lw, lh, pos, cont, disc, horizontal, leg["gradient_h"],
                leg["ncols"], pad_x, pad_y, row_h, sw, tick_size,
                text_color, _ctx_for))
        parts.append('</g>')

    # Inset axes — render each as its own SVG fragment positioned by
    # axes-fraction within this leaf's data area. Drawn last so they
    # sit on top of the data layer (and on top of the legend). Wrapped
    # in a data-area clip so the inset's canvas can't paint over the
    # parent's title/labels if its own margins overhang.
    insets = state.get("insets") or []
    if insets:
        parts.append(f'<svg x="0" y="0" width="{iw:.10g}" height="{ih:.10g}" overflow="hidden">')
    for inset_rect, inset_chart in insets:
        x_frac, y_frac, w_frac, h_frac = inset_rect
        # Emit the inset from its cached resolution. Every inset reaching
        # emit is a rehydrated node carrying `_resolved_plan` (stamped by
        # `resolved_ir._rehydrate_panel`) — there is no other emit path. The
        # sink is suppressed because the translate offset isn't known
        # until this render finishes — regions are recorded by the
        # re-render below.
        from ._layout_engine import _emit_plan
        with _regions.suppressed():
            inset_svg = _emit_plan(inset_chart._resolved_plan)
        inset_M = inset_chart._last_M_eff or {"left": 0, "right": 0, "top": 0, "bottom": 0}
        # Bottom-left origin: y-frac 0 = bottom of data, 1 = top.
        # Subtract the inset's own margin so its data region (not its
        # canvas) lands at the requested fraction of the parent's data.
        tx = x_frac * iw - inset_M["left"]
        ty = (1 - y_frac - h_frac) * ih - inset_M["top"]
        if _regions.active():
            # Regions-only re-render at the now-known offset; rendering
            # is deterministic, so the emission matches `inset_svg` and
            # is discarded. Only runs under `regions()` collection.
            with _regions.translate(tx, ty):
                _emit_plan(inset_chart._resolved_plan)
        # Opaque background covering the inset's data area only — tick
        # labels in the inset's margins stay transparent.
        bg_x = inset_M["left"]
        bg_y = inset_M["top"]
        bg_w = inset_chart._data_width
        bg_h = inset_chart._data_height
        parts.append(f'<g transform="translate({coord(tx)},{coord(ty)})" '
                      f'data-plotlet-kind="inset">'
                      + rect(bg_x, bg_y, bg_w, bg_h,
                             fill=SPEC["figure"]["background"])
                      + f'{inset_svg}</g>')
    if insets:
        parts.append('</svg>')

    return "".join(parts)
