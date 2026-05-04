"""Figure class and render orchestrator — registry-driven version.

The deferred-render pipeline:
  1. `figure()` returns a `Figure` whose methods record into `_calls`.
  2. `Figure.to_svg()` calls `_render(_replay(), ...)`.
  3. `_render` does: pre-process → domain → scales → grid → artists → spines/ticks
     → labels/title → legend.

Every artist-specific branch is a registry lookup. Adding a new plot type
means calling `add_artist(...)` — no monkey-patching, no editing this file.

`_render_inner` accepts an optional `_PanelOpts` so the layout pre-pass in
`layout.py` can supply pre-computed axis descriptors (for share_x/share_y)
and side-suppression flags. Standalone Figure rendering passes None and
behaves as before.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from ._spec import (
    SPEC, _SIZESPEC, _MARGIN_FLOOR, _FRAME, _GRIDSPEC, _FONTSPEC, _LEGSPEC, _D, _DASH,
)
from .colors import _resolve_color, TAB10
from .scales import _LinearScale, _LogScale, _CategoryScale, _nice_domain, _fmt_tick
from .font import _measure_text, _text_path
from .artists import _histogram
from .registry import RenderContext, get_artist, all_artist_names
from . import builtin_artists  # noqa: F401  — registers built-ins on import

_TICK_LEN = _FRAME["tick_length"]
_TICK_PAD = _FRAME["tick_pad"]
_SPINE = _FRAME["color"]
_SPW = _FRAME["width"]
_GRID = _GRIDSPEC["color"]
_FONT = _FONTSPEC["family"]


# Frame metadata methods (title, xlabel, etc.) — these aren't artists,
# they're just state setters. Kept as a fixed set.
_FRAME_METHODS = {
    "title", "xlabel", "ylabel", "xlim", "ylim",
    "xscale", "yscale", "grid", "legend",
    "xticks", "yticks",
}


# ---------------------------------------------------------------------------
# Scale-share types — used by the layout pre-pass.
# ---------------------------------------------------------------------------

@dataclass
class _AxisDescriptor:
    """Domain for one axis, decoupled from any pixel range. The layout
    pre-pass builds one per share-equivalence class; each panel calls
    `build(r0, r1)` with its own pixel range to instantiate a scale."""
    kind: str           # "linear" | "log" | "category"
    lo: float = 0.0
    hi: float = 1.0
    cats: list | None = None
    padding: float = field(default_factory=lambda: _D["category_padding"])  # category only; 0 = contiguous bands

    def build(self, r0, r1):
        if self.kind == "log":
            return _LogScale(self.lo, self.hi, r0, r1)
        if self.kind == "category":
            return _CategoryScale(self.cats or [], r0, r1, padding=self.padding)
        return _LinearScale(self.lo, self.hi, r0, r1)


@dataclass
class _PanelOpts:
    """Layout-supplied render options for one leaf panel.

    `hide_*` collapses the matching margin (axis labels and title in that
    margin get dropped — they don't fit; spines and tick lines remain).
    `suppress_*_labels` drops tick labels on a side whose axis is shared
    with a neighbor that already labels it; set only on the panel that
    actually shares, never propagated by grid alignment.
    """
    x_axis: _AxisDescriptor | None = None
    y_axis: _AxisDescriptor | None = None
    hide_left:   bool = False
    hide_right:  bool = False
    hide_top:    bool = False
    hide_bottom: bool = False
    suppress_left_labels:   bool = False
    suppress_bottom_labels: bool = False


def _rotated_text(s, x, y, size, angle, axis):
    """Tick label as text-as-paths, optionally rotated.

    `angle=0` is a passthrough to `_text_path` with the unrotated anchor —
    keeps existing SVG output byte-identical when no rotation is set.
    Otherwise emits the glyph paths at origin with anchor="end", then
    wraps in `<g transform="translate(x,y) rotate(-angle)">` so the
    rotation pivots at the call-site's (x, y). The negation matches
    matplotlib's convention (positive angle = counterclockwise on screen)
    against SVG's positive-clockwise rotation."""
    if not angle:
        anchor = "middle" if axis == "x" else "end"
        return _text_path(s, x, y, size, anchor=anchor)
    text = _text_path(s, 0, 0, size, anchor="end")
    return f'<g transform="translate({x:.2f},{y:.2f}) rotate({-angle})">{text}</g>'


def _record_ticks(st, axis, args, kw):
    """Decode the matplotlib-style xticks()/yticks() call into state.

    Signature: xticks(ticks=None, labels=None, *, rotation=0, fontsize=None).
    Accepts the first arg positionally (matches `plt.xticks`); pass `[]`
    to hide. Omitted kwargs leave the corresponding state alone, so
    `c.xticks(rotation=45)` rotates without disturbing auto positions.
    """
    if args:
        st[f"{axis}_ticks"] = list(args[0]) if args[0] is not None else None
        if len(args) > 1 and args[1] is not None:
            st[f"{axis}_labels"] = list(args[1])
    if "ticks" in kw:
        v = kw["ticks"]
        st[f"{axis}_ticks"] = list(v) if v is not None else None
    if "labels" in kw:
        v = kw["labels"]
        st[f"{axis}_labels"] = list(v) if v is not None else None
    if "rotation" in kw:  st[f"{axis}_rotation"]  = kw["rotation"]
    if "fontsize" in kw:  st[f"{axis}_fontsize"]  = kw["fontsize"]
    if "direction" in kw: st[f"{axis}_direction"] = kw["direction"]
    if "marks" in kw:     st[f"{axis}_marks"]     = bool(kw["marks"])


class Figure:
    def __init__(self, width: int | None = None, height: int | None = None,
                 margin: dict | None = None):
        self._calls: list[tuple[str, list, dict]] = []
        self._width = width if width is not None else _SIZESPEC["width"]
        self._height = height if height is not None else _SIZESPEC["height"]
        self._margin = margin if margin is not None else dict(_SIZESPEC["margin"])

    def __getattr__(self, name):
        # Recordable if it's a frame method or a registered artist
        if name in _FRAME_METHODS or get_artist(name) is not None:
            def recorder(*args, **kwargs):
                self._calls.append((name, list(args), dict(kwargs)))
                return self
            return recorder
        raise AttributeError(
            f"Figure has no method {name!r}. "
            f"Registered artists: {all_artist_names()}"
        )

    def __dir__(self):
        return sorted(set(super().__dir__()) | _FRAME_METHODS | set(all_artist_names()))

    # ------------------------------------------------------------- replay
    def _replay(self):
        st = {
            "artists": [], "title": "", "xlabel": "", "ylabel": "",
            "xlim": None, "ylim": None, "xscale": "linear", "yscale": "linear",
            "x_order": None, "y_order": None,
            "x_padding": None, "y_padding": None,
            # xticks/yticks overrides (None = auto, [] = hide):
            "x_ticks": None, "x_labels": None, "x_rotation": 0, "x_fontsize": None,
            "x_direction": "in", "x_marks": True,
            "y_ticks": None, "y_labels": None, "y_rotation": 0, "y_fontsize": None,
            "y_direction": "in", "y_marks": True,
            "grid": False, "legend": False,
        }
        for name, args, kw in self._calls:
            spec = get_artist(name)
            if spec is not None:
                st["artists"].append(spec.record(args, kw))
            elif name == "title":  st["title"] = args[0]
            elif name == "xlabel": st["xlabel"] = args[0]
            elif name == "ylabel": st["ylabel"] = args[0]
            elif name == "xlim":   st["xlim"] = (args[0], args[1])
            elif name == "ylim":   st["ylim"] = (args[0], args[1])
            elif name == "xscale":
                st["xscale"] = args[0]
                if "order" in kw:   st["x_order"] = list(kw["order"])
                if "padding" in kw: st["x_padding"] = kw["padding"]
            elif name == "yscale":
                st["yscale"] = args[0]
                if "order" in kw:   st["y_order"] = list(kw["order"])
                if "padding" in kw: st["y_padding"] = kw["padding"]
            elif name == "xticks": _record_ticks(st, "x", args, kw)
            elif name == "yticks": _record_ticks(st, "y", args, kw)
            elif name == "grid":   st["grid"] = (args[0] if args else True)
            elif name == "legend": st["legend"] = (args[0] if args else True)
        return st

    # ------------------------------------------------------------- render
    def to_svg(self) -> str:
        return _render(self._replay(), self._width, self._height, self._margin)

    def to_html(self, full_page: bool = False) -> str:
        svg = self.to_svg()
        if full_page:
            return ('<!doctype html><html><head><meta charset="utf-8">'
                    '<title>plotlet</title></head>'
                    f'<body style="margin:24px">{svg}</body></html>')
        return svg

    def _repr_html_(self) -> str:
        return self.to_svg()

    def show(self):
        try:
            from IPython.display import HTML, display
        except ImportError:
            print(self.to_html(full_page=True))
            return
        display(HTML(self.to_svg()))

    def write_html(self, filename):
        Path(filename).write_text(self.to_html(full_page=True))
        return self

    def save_svg(self, filename):
        Path(filename).write_text(self.to_svg())
        return self


def figure(width: int | None = None, height: int | None = None, **opts) -> Figure:
    return Figure(width=width, height=height, **opts)


# ---------------------------------------------------------------------------
# Domain helpers — shared by the panel renderer and the layout pre-pass.
# ---------------------------------------------------------------------------

def _scan_domain(artists, axis):
    """Collect all values an artist contributes to a given axis ('x' or 'y')."""
    lo, hi = math.inf, -math.inf
    for a in artists:
        spec = get_artist(a["type"])
        if spec is None:
            continue
        fn = spec.xdomain if axis == "x" else spec.ydomain
        vals = fn(a)
        if vals is None:
            continue
        for v in vals:
            if v is None: continue
            if isinstance(v, float) and math.isnan(v): continue
            if v < lo: lo = v
            if v > hi: hi = v
    return lo, hi


def _resolve_domain(lo, hi, user_lim, scale_kind, force_zero=False):
    """Apply user override, log snapping, and nice rounding."""
    if user_lim is not None:
        return user_lim
    if math.isinf(lo):
        return (0, 1)
    if force_zero and lo > 0:
        lo = 0
    if lo == hi:
        return (lo - 0.5, hi + 0.5)
    if scale_kind == "log":
        if lo > 0 and hi > 0:
            return (10 ** math.floor(math.log10(lo)),
                    10 ** math.ceil(math.log10(hi)))
        return (lo, hi)
    return _nice_domain(lo, hi)


def _scaled_margin(M, W, H):
    """Shrink margins for small panels, with a per-side floor so tick labels
    and titles still fit. Floors live in `spec.size.margin_floor`; base
    margins (defaulted from spec, overridable via `pt.chart(margin=...)`)
    scale by `min(1, panel_size / spec_size)` per axis."""
    fw = min(1.0, W / _SIZESPEC["width"])
    fh = min(1.0, H / _SIZESPEC["height"])
    return {
        "top":    max(_MARGIN_FLOOR["top"],    int(round(M["top"]    * fh))),
        "bottom": max(_MARGIN_FLOOR["bottom"], int(round(M["bottom"] * fh))),
        "left":   max(_MARGIN_FLOOR["left"],   int(round(M["left"]   * fw))),
        "right":  max(_MARGIN_FLOOR["right"],  int(round(M["right"]  * fw))),
    }


def _prebin_hist(st):
    """Compute hist bins on `st["artists"]` so they participate in domain
    scanning. Idempotent (guarded by `_bins` presence)."""
    for a in st["artists"]:
        if a["type"] == "hist" and "_bins" not in a:
            a["_bins"] = _histogram(a["data"], a["opts"].get("bins", 10))


def _collect_categories(artists, axis):
    """Unique values an artist contributes on `axis`, alphabetically sorted."""
    seen = set()
    out = []
    for a in artists:
        spec = get_artist(a["type"])
        if spec is None: continue
        fn = spec.xdomain if axis == "x" else spec.ydomain
        vals = fn(a)
        if vals is None: continue
        for v in vals:
            if v is None: continue
            if v not in seen:
                seen.add(v); out.append(v)
    return sorted(out, key=str)


def _is_categorical_axis(artists, axis):
    """An axis is categorical when any artist contributes a string value
    (and no numeric value before it). First non-None value decides."""
    for a in artists:
        spec = get_artist(a["type"])
        if spec is None: continue
        fn = spec.xdomain if axis == "x" else spec.ydomain
        vals = fn(a)
        if vals is None: continue
        for v in vals:
            if v is None: continue
            return isinstance(v, str)
    return False


def _x_descriptor(st) -> _AxisDescriptor:
    """Compute this panel's natural x-axis descriptor from its own state.

    Categorical precedence:
      1. explicit `xscale("category", order=[...])` → that exact order
      2. `xscale("category")` with no order → alphabetical of unique x values
      3. any artist contributes string-valued x (bar, scatter on strings,
         …) → alphabetical of unique x values
      4. otherwise → linear/log path
    """
    _prebin_hist(st)
    artists = st["artists"]
    explicit_cat = st["xscale"] == "category"
    auto_cat = _is_categorical_axis(artists, "x")

    if explicit_cat or auto_cat:
        cats = (list(st["x_order"]) if st["x_order"] is not None
                else _collect_categories(artists, "x"))
        padding = _D["category_padding"] if st["x_padding"] is None else st["x_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding)

    x_lo, x_hi = _scan_domain(artists, "x")
    x_min, x_max = _resolve_domain(x_lo, x_hi, st["xlim"], st["xscale"])
    return _AxisDescriptor(kind=st["xscale"], lo=x_min, hi=x_max)


def _y_descriptor(st) -> _AxisDescriptor:
    """Compute this panel's natural y-axis descriptor from its own state.

    Categorical precedence mirrors `_x_descriptor`. `force_zero` still
    fires for bar/hist so numeric y-axes anchor at 0.
    """
    _prebin_hist(st)
    artists = st["artists"]
    explicit_cat = st["yscale"] == "category"
    auto_cat = _is_categorical_axis(artists, "y")

    if explicit_cat or auto_cat:
        cats = (list(st["y_order"]) if st["y_order"] is not None
                else _collect_categories(artists, "y"))
        padding = _D["category_padding"] if st["y_padding"] is None else st["y_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding)

    has_bar = any(a["type"] == "bar" for a in artists)
    force_zero = has_bar or any(a["type"] == "hist" for a in artists)
    y_lo, y_hi = _scan_domain(artists, "y")
    y_min, y_max = _resolve_domain(y_lo, y_hi, st["ylim"], st["yscale"], force_zero=force_zero)
    return _AxisDescriptor(kind=st["yscale"], lo=y_min, hi=y_max)


def _build_xy_scales(st, iw, ih, panel_opts: _PanelOpts):
    """Instantiate pixel-bound scales. `panel_opts.x_axis` / `y_axis` come
    from the layout pre-pass when set; otherwise we compute them from the
    panel's own state. y-category runs top-to-bottom (cats on rows);
    y-linear/log runs cartesian."""
    x_axis = panel_opts.x_axis or _x_descriptor(st)
    y_axis = panel_opts.y_axis or _y_descriptor(st)
    x_scale = x_axis.build(0, iw)
    y_scale = y_axis.build(0, ih) if y_axis.kind == "category" else y_axis.build(ih, 0)
    x_is_cat = (x_axis.kind == "category")
    return x_scale, y_scale, x_is_cat


# ---------------------------------------------------------------------------
# render orchestrator — now generic over the registry
# ---------------------------------------------------------------------------

def _render(st, W, H, M):
    M = _scaled_margin(M, W, H)
    iw = W - M["left"] - M["right"]
    ih = H - M["top"] - M["bottom"]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{_FONT}" font-size="11" '
        f'style="background:#fff">'
        f'<g transform="translate({M["left"]},{M["top"]})">'
        + _render_inner(st, iw, ih, M)
        + '</g></svg>'
    )


def _render_inner(st, iw, ih, M, panel_opts: _PanelOpts | None = None):
    """Body fragment for one panel — everything inside the outer `<svg>` and
    the outer translate-by-margin `<g>`. `panel_opts` carries layout-supplied
    axis descriptors and side flags; `None` is the standalone path."""
    _prebin_hist(st)
    if panel_opts is None:
        panel_opts = _PanelOpts()

    x_scale, y_scale, x_is_cat = _build_xy_scales(st, iw, ih, panel_opts)
    # Tick density scales with panel size: 8 looks fine on the 600×400
    # default but turns into a label crush on a 80-px-wide colorbar.
    x_n = max(2, min(8, int(iw // 65)))
    y_n = max(2, min(8, int(ih // 40)))
    x_ticks = st["x_ticks"] if st["x_ticks"] is not None else x_scale.ticks(x_n)
    y_ticks = st["y_ticks"] if st["y_ticks"] is not None else y_scale.ticks(y_n)
    x_labels = st["x_labels"] if st["x_labels"] is not None else [_fmt_tick(t) for t in x_ticks]
    y_labels = st["y_labels"] if st["y_labels"] is not None else [_fmt_tick(t) for t in y_ticks]

    hide_l, hide_r = panel_opts.hide_left, panel_opts.hide_right
    hide_t, hide_b = panel_opts.hide_top, panel_opts.hide_bottom
    suppress_yt = panel_opts.suppress_left_labels
    suppress_xt = panel_opts.suppress_bottom_labels

    # ---- emit body fragment ----
    parts = []

    # grid
    if st["grid"]:
        gw = _GRIDSPEC["width"]; gd = _GRIDSPEC["dasharray"]
        if not x_is_cat:
            for t in x_ticks:
                x = x_scale(t)
                parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="0" y2="{ih}" '
                             f'stroke="{_GRID}" stroke-width="{gw}" stroke-dasharray="{gd}"/>')
        for t in y_ticks:
            y = y_scale(t)
            parts.append(f'<line x1="0" x2="{iw}" y1="{y:.2f}" y2="{y:.2f}" '
                         f'stroke="{_GRID}" stroke-width="{gw}" stroke-dasharray="{gd}"/>')

    # color assignment — only color-cycle artists consume the cycle
    color_idx = 0
    for a in st["artists"]:
        spec = get_artist(a["type"])
        user_color = _resolve_color(a["opts"].get("color"))
        if user_color is not None:
            a["_color"] = user_color
        elif spec is not None and spec.uses_color_cycle:
            a["_color"] = TAB10[color_idx % 10]
            color_idx += 1
        else:
            a["_color"] = spec.default_color if spec else None

    # build the render context once — passed to every draw call
    def _ctx_for(a):
        return RenderContext(
            x_scale=x_scale, y_scale=y_scale, iw=iw, ih=ih,
            color=a["_color"], defaults=_D, dash=_DASH,
        )

    # three-pass draw: background → data → foreground
    by_layer = {"background": [], "data": [], "foreground": []}
    for a in st["artists"]:
        spec = get_artist(a["type"])
        if spec is None: continue
        by_layer[spec.layer].append(a)
    for layer in ("background", "data", "foreground"):
        for a in by_layer[layer]:
            spec = get_artist(a["type"])
            parts.append(spec.draw(a, _ctx_for(a)))

    # All four spines always render — joined share-pairs show two parallel
    # spines (one per panel) `inner_gap` pixels apart, by design.
    for x1, y1, x2, y2 in [(0, 0, iw, 0), (0, ih, iw, ih),
                            (0, 0, 0, ih),  (iw, 0, iw, ih)]:
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                     f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')

    tick_size = _FONTSPEC["tick_size"]
    label_size = _FONTSPEC["label_size"]
    title_size = _FONTSPEC["title_size"]

    x_size = st["x_fontsize"] if st["x_fontsize"] is not None else tick_size
    y_size = st["y_fontsize"] if st["y_fontsize"] is not None else tick_size
    x_rot = st["x_rotation"] or 0
    y_rot = st["y_rotation"] or 0
    x_dir, y_dir = st["x_direction"], st["y_direction"]
    x_marks, y_marks = st["x_marks"], st["y_marks"]

    # Tick-mark endpoints relative to the spine. "in" goes inside the data
    # area, "out" goes outside, "inout" spans both sides at full length each.
    bot_in, bot_out = ih - _TICK_LEN, ih + _TICK_LEN  # bottom spine offsets
    top_in, top_out = _TICK_LEN, -_TICK_LEN           # top spine offsets
    if x_dir == "in":      x_bot_endpoints, x_top_endpoints = (ih, bot_in),  (0, top_in)
    elif x_dir == "out":   x_bot_endpoints, x_top_endpoints = (ih, bot_out), (0, top_out)
    else:                  x_bot_endpoints, x_top_endpoints = (bot_out, bot_in), (top_out, top_in)
    left_in, left_out  = _TICK_LEN, -_TICK_LEN        # left spine offsets (x = 0)
    right_in, right_out = iw - _TICK_LEN, iw + _TICK_LEN
    if y_dir == "in":      y_left_endpoints, y_right_endpoints = (0, left_in),  (iw, right_in)
    elif y_dir == "out":   y_left_endpoints, y_right_endpoints = (0, left_out), (iw, right_out)
    else:                  y_left_endpoints, y_right_endpoints = (left_out, left_in), (right_out, right_in)

    # y-axis labels need to clear an outward/inout tick mark; x-axis labels
    # already sit far enough below the spine to clear all three modes.
    y_label_x = -_TICK_PAD if y_dir == "in" else -(_TICK_LEN + _TICK_PAD)

    for t, lbl in zip(x_ticks, x_labels):
        x = x_scale(t)
        if x_marks:
            y1, y2 = x_bot_endpoints
            parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y1}" y2="{y2}" '
                         f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')
            y1, y2 = x_top_endpoints
            parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y1}" y2="{y2}" '
                         f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')
        # Drop only labels redundant with a sharing sibling. A small label
        # overflow into a joined neighbor's collapsed margin is acceptable.
        if not suppress_xt:
            parts.append(_rotated_text(str(lbl), x, ih + _TICK_LEN + _TICK_PAD + 8,
                                       x_size, x_rot, axis="x"))

    # y ticks + labels
    for t, lbl in zip(y_ticks, y_labels):
        y = y_scale(t)
        if y_marks:
            x1, x2 = y_left_endpoints
            parts.append(f'<line x1="{x1}" x2="{x2}" y1="{y:.2f}" y2="{y:.2f}" '
                         f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')
            x1, x2 = y_right_endpoints
            parts.append(f'<line x1="{x1}" x2="{x2}" y1="{y:.2f}" y2="{y:.2f}" '
                         f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')
        if not suppress_yt:
            parts.append(_rotated_text(str(lbl), y_label_x, y + 4, y_size, y_rot, axis="y"))

    # xlabel / ylabel / title live in margin space; drop when that margin
    # is collapsed against a joined neighbor.
    if st["xlabel"] and not hide_b:
        parts.append(_text_path(st["xlabel"], iw / 2, ih + M["bottom"] - 8,
                                label_size, anchor="middle"))
    if st["ylabel"] and not hide_l:
        ylabel_path = _text_path(st["ylabel"], 0, 0, label_size, anchor="middle")
        parts.append(f'<g transform="translate({-(M["left"] - 12)},{ih/2}) rotate(-90)">'
                     f'{ylabel_path}</g>')
    if st["title"] and not hide_t:
        parts.append(_text_path(st["title"], iw / 2, -10, title_size, anchor="middle"))

    # legend — each artist's spec supplies its own swatch via legend_swatch.
    # Custom artists that don't define one fall back to a colored line.
    if st["legend"]:
        labeled = [a for a in st["artists"] if a["opts"].get("label")]
        if labeled:
            row_h = _LEGSPEC["row_height"]
            pad_x = _LEGSPEC["pad_x"]
            pad_y = _LEGSPEC["pad_y"]
            sw    = _LEGSPEC["swatch_width"]
            max_text = max(_measure_text(a["opts"]["label"], tick_size) for a in labeled)
            lw = sw + 6 + max_text + 2 * pad_x
            lh = len(labeled) * row_h + 2 * pad_y
            lx, ly = iw - lw - _LEGSPEC["border_offset"], _LEGSPEC["border_offset"]
            parts.append(f'<g transform="translate({lx:.2f},{ly})">')
            parts.append(f'<rect x="0" y="0" width="{lw:.2f}" height="{lh}" '
                         f'fill="{_LEGSPEC["background"]}" stroke="{_SPINE}" '
                         f'stroke-width="{_SPW}" opacity="{_LEGSPEC["opacity"]}"/>')
            for i, a in enumerate(labeled):
                ry = pad_y + i * row_h + row_h / 2
                spec = get_artist(a["type"])
                if spec is not None and spec.legend_swatch is not None:
                    parts.append(spec.legend_swatch(a, _ctx_for(a), pad_x, ry))
                else:
                    parts.append(f'<line x1="{pad_x}" x2="{pad_x + sw}" y1="{ry}" y2="{ry}" '
                                 f'stroke="{a["_color"]}" stroke-width="{_D["linewidth"]}"/>')
                parts.append(_text_path(a["opts"]["label"], pad_x + sw + 6, ry + 4,
                                        tick_size, anchor="start"))
            parts.append('</g>')

    return "".join(parts)
