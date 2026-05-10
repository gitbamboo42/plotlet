"""Render engine — pure functions over Chart state.

The deferred-render pipeline:
  1. A `Chart` (defined in `chart.py`) records user calls into `_calls`.
  2. `Chart.to_svg()` calls `_render(_replay(calls), W, H, margin)`.
  3. `_render` does: pre-process → domain → scales → grid → artists →
     spines/ticks → labels/title → legend.

Every function here takes its state explicitly — there's no class to
hold it. Adding a new plot type means calling `add_artist(...)` from
outside; no monkey-patching, no editing this file.

`_render_inner` accepts an optional `_PanelOpts` so the layout pre-pass
in `layout.py` can supply pre-computed axis descriptors (for
share_x/share_y) and side-suppression flags. Standalone single-panel
rendering passes None and behaves as before.
"""
from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass, field
from importlib.metadata import version as _pkg_version
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

# AI-readable SVG attrs — see docs/AI_ATTRS.md. Every plotlet SVG carries
# `data-plotlet-*` attributes describing plot type, axes, scales, ranges,
# and series labels. Schema is semver-stable from 0.3.0 forward, declared
# via `data-plotlet-schema` on the root.
_SCHEMA_VERSION = "1"
# Read from package metadata (pyproject.toml) so there's a single source
# of truth for the version. Independent of `__init__.__version__` to
# avoid a circular import.
_PLOTLET_VERSION = _pkg_version("plotlet")

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
    "xticks", "yticks", "spines",
}


# ---------------------------------------------------------------------------
# Scale-share types — used by the layout pre-pass.
# ---------------------------------------------------------------------------

@dataclass
class _AxisDescriptor:
    """Domain for one axis, decoupled from any pixel range. The layout
    pre-pass builds one per share-equivalence class; each panel calls
    `build(r0, r1)` with its own pixel range to instantiate a scale.

    `flip=True` means the panel renderer swaps `(r0, r1)` when calling
    `build()`, inverting the axis."""
    kind: str           # "linear" | "log" | "category"
    lo: float = 0.0
    hi: float = 1.0
    cats: list | None = None
    padding: float = field(default_factory=lambda: _D["category_padding"])  # category only; 0 = contiguous bands
    flip: bool = False

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
    `M_eff`, when set, is the layout-pre-pass-resolved effective margin
    for a body-first leaf — it has already incorporated measure-driven
    growth and per-column/row coordination. Canvas-first leaves leave
    this `None` and fall through to `_scaled_margin` at render time.
    """
    x_axis: _AxisDescriptor | None = None
    y_axis: _AxisDescriptor | None = None
    hide_left:   bool = False
    hide_right:  bool = False
    hide_top:    bool = False
    hide_bottom: bool = False
    suppress_left_labels:   bool = False
    suppress_bottom_labels: bool = False
    M_eff:       dict | None = None


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
    # Per-side opt-in for the secondary tick side: xticks(top=True) on the
    # x-axis, yticks(right=True) on the y-axis. Both default off so the
    # standard look is bottom + left only.
    if axis == "x" and "top"   in kw: st["x_top"]   = bool(kw["top"])
    if axis == "y" and "right" in kw: st["y_right"] = bool(kw["right"])


# Conversion factors to pixels, CSS standard: 1 in = 96 px, 1 in = 2.54 cm,
# 1 in = 72 pt. Internal layout math is always pixels — string units are
# parsed once at the constructor boundary and stored as ints, so SVG output
# stays byte-identical regardless of input form.
_UNIT_PX = {
    "px": 1.0,
    "in": 96.0,
    "cm": 96.0 / 2.54,
    "mm": 96.0 / 25.4,
    "pt": 96.0 / 72.0,
}
_DIM_RE = re.compile(r"^\s*([+-]?\d*\.?\d+)\s*([a-zA-Z]*)\s*$")


def _to_px(value):
    """Resolve a dim value to integer pixels.

    Accepts:
      - `int` / `float`: bare pixels.
      - `str`: a number with an optional unit suffix
        (`"4in"`, `"10cm"`, `"100mm"`, `"72pt"`, `"30px"` or `"30"`).
        Whitespace and case insensitive (`"5 IN"` works).
      - `None`: passthrough (constructors interpret as "use default").
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # Guard against `True`/`False` slipping through `int` — almost never
        # what the user meant for a dimension.
        raise TypeError(f"dim value cannot be bool; got {value!r}")
    if isinstance(value, (int, float)):
        return int(round(value))
    if not isinstance(value, str):
        raise TypeError(
            f"dim value must be int, float, or str; got {type(value).__name__}"
        )
    m = _DIM_RE.match(value)
    if not m:
        raise ValueError(
            f"could not parse dim value {value!r}; expected '<number>[unit]' "
            f"where unit is one of: {', '.join(sorted(_UNIT_PX))}"
        )
    num = float(m.group(1))
    unit = m.group(2).lower() or "px"
    if unit not in _UNIT_PX:
        raise ValueError(
            f"unknown unit {unit!r} in {value!r}; expected one of: "
            f"{', '.join(sorted(_UNIT_PX))}"
        )
    return int(round(num * _UNIT_PX[unit]))


def _spec_canvas_dims() -> tuple[int, int]:
    """Spec-default canvas size, derived from data region + spec margin.

    The dimensional primitive is the data region (`spec.size.data_width` /
    `data_height`); this helper rebuilds the implied canvas size so legacy
    canvas-based math (`_scaled_margin`, layout allocation) keeps a single
    well-defined reference point."""
    M = _SIZESPEC["margin"]
    return (_SIZESPEC["data_width"]  + M["left"] + M["right"],
            _SIZESPEC["data_height"] + M["top"]  + M["bottom"])


def _replay(calls):
    """Walk a Chart's recorded calls into a state dict consumed by the
    renderer. Pure function of `calls` and the artist registry — same input
    + same registry → same output."""
    st = {
        "artists": [], "title": "", "xlabel": "", "ylabel": "",
        "xlim": None, "ylim": None, "xscale": "linear", "yscale": "linear",
        "x_order": None, "y_order": None,
        "x_padding": None, "y_padding": None,
        # xticks/yticks overrides (None = auto, [] = hide):
        "x_ticks": None, "x_labels": None, "x_rotation": 0, "x_fontsize": None,
        "x_direction": _FRAME["tick_direction"], "x_marks": True,
        "x_top":   _FRAME["tick_top"],
        "y_ticks": None, "y_labels": None, "y_rotation": 0, "y_fontsize": None,
        "y_direction": _FRAME["tick_direction"], "y_marks": True,
        "y_right": _FRAME["tick_right"],
        "spine_top": True, "spine_right": True,
        "spine_bottom": True, "spine_left": True,
        # Per-side color/width overrides; None = inherit spec.json frame defaults.
        # Tick marks on a given side adopt the same side's spine color/width
        # for visual consistency.
        "spine_top_color": None, "spine_right_color": None,
        "spine_bottom_color": None, "spine_left_color": None,
        "spine_top_width": None, "spine_right_width": None,
        "spine_bottom_width": None, "spine_left_width": None,
        "grid": False, "legend": False,
    }
    for name, args, kw in calls:
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
        elif name == "spines":
            # Per-side value: bool toggles visibility only; dict accepts
            # {"color": ..., "width": ..., "visible": ...} and implies
            # visible=True unless visible is set explicitly.
            for side in ("top", "right", "bottom", "left"):
                if side not in kw: continue
                v = kw[side]
                if isinstance(v, dict):
                    st[f"spine_{side}"] = bool(v.get("visible", True))
                    if "color" in v: st[f"spine_{side}_color"] = v["color"]
                    if "width" in v: st[f"spine_{side}_width"] = v["width"]
                else:
                    st[f"spine_{side}"] = bool(v)
        elif name == "grid":   st["grid"] = (args[0] if args else True)
        elif name == "legend": st["legend"] = (args[0] if args else True)
    return st


def _effective_margin(leaf, st=None) -> dict:
    """Margin used at render time. Reads dimension state directly off the
    leaf Chart.

    Canvas path: scales by canvas dims (legacy 0.1.x behavior); text
    overflow is the user's responsibility because canvas size is promised
    exactly.

    Data path: combines `_enforce_floors(spec/user margin)` with the
    content-driven `_required_margin(st, data_w, data_h)` by taking the
    per-side max — so the canvas grows as needed to fit long tick labels,
    titles, and axis labels rather than letting them overflow. Caller
    passes the replayed `st`; callers without one get only the
    floor-applied spec margin."""
    if leaf._canvas_explicit:
        return _scaled_margin(leaf._margin, leaf._canvas_width, leaf._canvas_height)
    M_floor = _enforce_floors(leaf._margin)
    if st is None:
        return M_floor
    M_req = _required_margin(st, leaf._data_width, leaf._data_height)
    return {side: max(M_floor[side], M_req[side]) for side in M_floor}




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


def _resolve_domain(lo, hi, user_lim, scale_kind, force_zero=False, tight=False):
    """Apply user override, log snapping, and nice rounding.

    `tight=True` skips the nice-numbers padding — for artists with hard
    rectangular bounds (e.g. imshow) where extending the axis past the
    data just leaves dead space."""
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
    if tight:
        return (lo, hi)
    return _nice_domain(lo, hi)


def _enforce_floors(M):
    """Apply per-side margin floors without any scaling. Used by the
    data-region path: the user (or spec) declared the margin in absolute
    pixels, so we just round and floor — never shrink."""
    return {
        "top":    max(_MARGIN_FLOOR["top"],    int(round(M["top"]))),
        "bottom": max(_MARGIN_FLOOR["bottom"], int(round(M["bottom"]))),
        "left":   max(_MARGIN_FLOOR["left"],   int(round(M["left"]))),
        "right":  max(_MARGIN_FLOOR["right"],  int(round(M["right"]))),
    }


def _scaled_margin(M, W, H):
    """Shrink margins for small canvases, with a per-side floor so tick
    labels and titles still fit. Used by the canvas-explicit path
    (`Chart(canvas_width=…)` and the layout's per-panel allocation),
    where the canvas size is fixed and margins must scale to fit. Floors
    live in `spec.size.margin_floor`; the reference canvas is derived
    from `spec.size.data_width/height + spec margin`."""
    spec_W, spec_H = _spec_canvas_dims()
    fw = min(1.0, W / spec_W)
    fh = min(1.0, H / spec_H)
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
    x_min, x_max = _resolve_domain(x_lo, x_hi, st["xlim"], st["xscale"],
                                    tight=_axis_is_tight(artists, "x"))
    return _AxisDescriptor(kind=st["xscale"], lo=x_min, hi=x_max)


def _any_artist_flips_y(artists) -> bool:
    """True if any artist on the panel declares (via its `flips_y_axis`
    spec hook) that the y-axis should render inverted."""
    for a in artists:
        spec = get_artist(a["type"])
        if spec is not None and spec.flips_y_axis is not None and spec.flips_y_axis(a):
            return True
    return False


def _axis_is_tight(artists, axis: str) -> bool:
    """True when every artist that contributes to autoscaling on this axis
    declares `tight_domain=True`. Artists that don't autoscale (xdomain or
    ydomain returns None — e.g. axhline) don't get a vote. Returns False
    when no artist contributes (nothing to be tight about)."""
    saw_contributor = False
    for a in artists:
        spec = get_artist(a["type"])
        if spec is None:
            continue
        fn = spec.xdomain if axis == "x" else spec.ydomain
        if fn(a) is None:
            continue
        saw_contributor = True
        if not spec.tight_domain:
            return False
    return saw_contributor


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
    y_min, y_max = _resolve_domain(y_lo, y_hi, st["ylim"], st["yscale"],
                                    force_zero=force_zero,
                                    tight=_axis_is_tight(artists, "y"))
    return _AxisDescriptor(kind=st["yscale"], lo=y_min, hi=y_max,
                           flip=_any_artist_flips_y(artists))


def _x_descriptor_multi(states: list[dict]) -> _AxisDescriptor:
    """Build an x-axis descriptor for a share-equivalence class.

    The first state in `states` is the anchor — its xscale, xlim, x_order,
    and x_padding settings win. Auto-scanned data range is the union of
    artists across all states. Single-state input is equivalent to
    `_x_descriptor(states[0])`."""
    if len(states) == 1:
        return _x_descriptor(states[0])
    for st in states:
        _prebin_hist(st)
    anchor = states[0]
    all_artists = [a for st in states for a in st["artists"]]
    explicit_cat = anchor["xscale"] == "category"
    auto_cat = _is_categorical_axis(all_artists, "x")
    if explicit_cat or auto_cat:
        cats = (list(anchor["x_order"]) if anchor["x_order"] is not None
                else _collect_categories(all_artists, "x"))
        padding = _D["category_padding"] if anchor["x_padding"] is None else anchor["x_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding)
    x_lo, x_hi = _scan_domain(all_artists, "x")
    x_min, x_max = _resolve_domain(x_lo, x_hi, anchor["xlim"], anchor["xscale"],
                                    tight=_axis_is_tight(all_artists, "x"))
    return _AxisDescriptor(kind=anchor["xscale"], lo=x_min, hi=x_max)


def _y_descriptor_multi(states: list[dict]) -> _AxisDescriptor:
    """y-axis counterpart to `_x_descriptor_multi`. force_zero fires if any
    leaf in the share class plots bar or hist artists."""
    if len(states) == 1:
        return _y_descriptor(states[0])
    for st in states:
        _prebin_hist(st)
    anchor = states[0]
    all_artists = [a for st in states for a in st["artists"]]
    explicit_cat = anchor["yscale"] == "category"
    auto_cat = _is_categorical_axis(all_artists, "y")
    if explicit_cat or auto_cat:
        cats = (list(anchor["y_order"]) if anchor["y_order"] is not None
                else _collect_categories(all_artists, "y"))
        padding = _D["category_padding"] if anchor["y_padding"] is None else anchor["y_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding)
    force_zero = any(a["type"] in ("bar", "hist") for a in all_artists)
    y_lo, y_hi = _scan_domain(all_artists, "y")
    y_min, y_max = _resolve_domain(y_lo, y_hi, anchor["ylim"], anchor["yscale"],
                                    force_zero=force_zero,
                                    tight=_axis_is_tight(all_artists, "y"))
    return _AxisDescriptor(kind=anchor["yscale"], lo=y_min, hi=y_max,
                           flip=_any_artist_flips_y(all_artists))


def _rotated_label_bbox(label_w: float, label_h: float, rot_deg: float) -> tuple[float, float]:
    """Bounding-box (width, height) of a rotated text label. Conservative —
    uses the simple `|cos|·w + |sin|·h` envelope, which is exact for the
    AABB of an axis-aligned rectangle rotated by any angle."""
    if rot_deg == 0:
        return label_w, label_h
    rad = math.radians(abs(rot_deg))
    sin_r = math.sin(rad)
    cos_r = math.cos(rad)
    return (label_w * cos_r + label_h * sin_r,
            label_w * sin_r + label_h * cos_r)


def _required_margin(st, dw, dh) -> dict:
    """Margin a body-first leaf actually needs to fit its title, axis
    labels, and tick labels without overflow.

    Returns a plain dict with the same keys as `_margin` — the caller
    combines this with the user/spec margin (and the per-side floor) by
    taking max per side. Body-first specifically: data dims are fixed,
    so tick density and labels are deterministic and the computation is
    a single pass (no chicken-and-egg with margin).

    The geometry mirrors `_render_inner`'s placement formulas — keep them
    in sync if either changes."""
    tick_size  = _FONTSPEC["tick_size"]
    label_size = _FONTSPEC["label_size"]
    title_size = _FONTSPEC["title_size"]

    # Title sits at y = -10 from the data top (see _render_inner), so it
    # needs ≥ title_size + ~4 px of top margin to clear.
    top = title_size + 6 if st["title"] else 0

    # Provisional scales at the fixed data dims — body-first means iw/ih
    # are decided up front, no iteration needed.
    x_axis = _x_descriptor(st)
    y_axis = _y_descriptor(st)
    x_scale = x_axis.build(0, dw)
    if y_axis.kind == "category" or y_axis.flip:
        y_scale = y_axis.build(0, dh)
    else:
        y_scale = y_axis.build(dh, 0)

    # Same tick-density rule as `_render_inner`.
    x_n = max(2, min(8, int(dw // 65)))
    y_n = max(2, min(8, int(dh // 40)))
    x_ticks  = st["x_ticks"]  if st["x_ticks"]  is not None else x_scale.ticks(x_n)
    y_ticks  = st["y_ticks"]  if st["y_ticks"]  is not None else y_scale.ticks(y_n)
    x_labels = (st["x_labels"] if st["x_labels"] is not None
                else [_fmt_tick(t) for t in x_ticks])
    y_labels = (st["y_labels"] if st["y_labels"] is not None
                else [_fmt_tick(t) for t in y_ticks])

    x_size = st["x_fontsize"] if st["x_fontsize"] is not None else tick_size
    y_size = st["y_fontsize"] if st["y_fontsize"] is not None else tick_size
    x_rot  = st["x_rotation"] or 0
    y_rot  = st["y_rotation"] or 0
    x_dir, y_dir = st["x_direction"], st["y_direction"]
    x_marks, y_marks = st["x_marks"], st["y_marks"]

    # Outward / inout tick marks reach past the spine; "in" is internal only.
    out_x = _TICK_LEN if x_marks and x_dir != "in" else 0
    out_y = _TICK_LEN if y_marks and y_dir != "in" else 0

    # X-tick label bbox (after rotation).
    if x_labels:
        max_xtl_w = max((_measure_text(str(l), x_size) for l in x_labels), default=0.0)
        last_xtl_w = _measure_text(str(x_labels[-1]), x_size)
        _, xtl_bbox_h = _rotated_label_bbox(max_xtl_w, x_size, x_rot)
        last_bbox_w, _ = _rotated_label_bbox(last_xtl_w, x_size, x_rot)
    else:
        xtl_bbox_h = 0.0
        last_bbox_w = 0.0

    # Y-tick label width (after rotation).
    if y_labels:
        max_ytl_w = max((_measure_text(str(l), y_size) for l in y_labels), default=0.0)
        ytl_bbox_w, _ = _rotated_label_bbox(max_ytl_w, y_size, y_rot)
    else:
        ytl_bbox_w = 0.0

    # Bottom: outward tick + tick_pad + 8 px buffer + tick label bbox + xlabel.
    # The "+8" mirrors the literal in _render_inner's tick-label baseline y.
    bottom = out_x + _TICK_PAD + 8 + xtl_bbox_h
    if st["xlabel"]:
        bottom += label_size + 8

    # Left: outward tick + tick_pad + tick label bbox + ylabel allowance.
    # ylabel sits at canvas-left + 12 px (rotated -90), so it occupies
    # roughly `label_size` in the horizontal direction.
    left = out_y + _TICK_PAD + ytl_bbox_w
    if st["ylabel"]:
        left += label_size + 8

    # Right: outward tick OR the rightmost x-tick label's overhang past
    # the spine (centered text extends half its width past the tick).
    # Right ticks default off (publication look); only reserve tick
    # clearance when the user opted back in via `yticks(right=True)`.
    right_overhang = last_bbox_w / 2.0
    right = max(out_y if st["y_right"] else 0, right_overhang)

    # Long-text overflow: a title / xlabel longer than `dw` is centered on
    # `iw/2`, so it sticks out past the data area on both left and right
    # by `(text_w - dw) / 2`. A ylabel (rotated -90, centered on `ih/2`)
    # is the same story but vertical: text longer than `dh` spills past
    # top and bottom equally. Margins grow by the overhang amount so the
    # rendered text fits inside the canvas.
    if st["title"]:
        title_overhang = max(0.0, (_measure_text(st["title"], title_size) - dw) / 2.0)
        left  = max(left,  title_overhang)
        right = max(right, title_overhang)
    if st["xlabel"]:
        xlabel_overhang = max(0.0, (_measure_text(st["xlabel"], label_size) - dw) / 2.0)
        left  = max(left,  xlabel_overhang)
        right = max(right, xlabel_overhang)
    if st["ylabel"]:
        ylabel_overhang = max(0.0, (_measure_text(st["ylabel"], label_size) - dh) / 2.0)
        top    = max(top,    ylabel_overhang)
        bottom = max(bottom, ylabel_overhang)

    return {"top":    int(round(top)),
            "right":  int(round(right)),
            "bottom": int(round(bottom)),
            "left":   int(round(left))}


def _build_xy_scales(st, iw, ih, panel_opts: _PanelOpts):
    """Instantiate pixel-bound scales. `panel_opts.x_axis` / `y_axis` come
    from the layout pre-pass when set; otherwise we compute them from the
    panel's own state. y-category runs top-to-bottom (cats on rows);
    y-linear/log runs cartesian unless the descriptor requested a flip."""
    x_axis = panel_opts.x_axis or _x_descriptor(st)
    y_axis = panel_opts.y_axis or _y_descriptor(st)
    x_scale = x_axis.build(0, iw)
    if y_axis.kind == "category":
        y_scale = y_axis.build(0, ih)
    elif y_axis.flip:
        y_scale = y_axis.build(0, ih)
    else:
        y_scale = y_axis.build(ih, 0)
    x_is_cat = (x_axis.kind == "category")
    return x_scale, y_scale, x_is_cat


# ---------------------------------------------------------------------------
# AI-readable SVG attrs — schema and helpers (0.3.0)
# ---------------------------------------------------------------------------
# Every plotlet SVG carries `data-plotlet-*` attributes describing plot type,
# axes, scales, ranges, and series labels. Schema is semver-stable from 0.3.0
# forward, declared via `data-plotlet-schema="1"` on the root.

def _attr_str(v) -> str:
    """Stringify a value for a data-plotlet-* attribute. floats use repr()
    to round-trip exactly; ints, strings stringify naturally; bools are
    "true"/"false". Lists are not supported here — they go in <metadata>."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
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
    `>` `&` without XML escaping; `json.dumps` won't produce `]]>`."""
    body = json.dumps(list(cats), ensure_ascii=False, separators=(",", ":"))
    return (f'<metadata data-plotlet-payload="{name}">'
            f'<![CDATA[{body}]]></metadata>')


def _figure_root_attrs(kind: str) -> str:
    """Attrs for the outer `<svg>`. `kind` is "figure" (single panel) or
    "layout" (multi-panel composition)."""
    return _attrs_str({
        "version": _PLOTLET_VERSION,
        "schema":  _SCHEMA_VERSION,
        "kind":    kind,
    })


def _panel_attrs_and_meta(st, M, iw, ih, x_axis, y_axis,
                          panel_bbox: tuple[float, float, float, float]
                          ) -> tuple[str, str]:
    """Build (attrs, metadata) for one panel <g>. `attrs` is the attribute
    string spliced into the open tag; `metadata` is one or more <metadata>
    children placed at the start of the <g> body (currently: x/y category
    lists)."""
    attrs = {"kind": "panel"}
    if st["title"]:  attrs["title"]  = st["title"]
    if st["xlabel"]: attrs["xlabel"] = st["xlabel"]
    if st["ylabel"]: attrs["ylabel"] = st["ylabel"]
    attrs["xscale"] = x_axis.kind
    attrs["yscale"] = y_axis.kind

    if x_axis.kind != "category":
        attrs["xlim"] = f"{repr(x_axis.lo)},{repr(x_axis.hi)}"
    if y_axis.kind != "category":
        attrs["ylim"] = f"{repr(y_axis.lo)},{repr(y_axis.hi)}"
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
    attrs["data-area"] = f'{M["left"]},{M["top"]},{int(round(iw))},{int(round(ih))}'

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
# render orchestrator — now generic over the registry
# ---------------------------------------------------------------------------

def _panel_open(st, panel_opts: _PanelOpts | None, transform: str,
                M: dict, iw: float, ih: float,
                panel_bbox: tuple[float, float, float, float]) -> str:
    """Open a panel `<g>` with transform + structural data attrs, and emit
    any panel-level `<metadata>` children (currently x/y category lists).
    Used by both standalone `_render` and layout's `_render_layout` so the
    two paths stay in sync. Returns a string ending mid-element — the
    caller appends `_render_inner(...)` then `</g>`."""
    x_axis = (panel_opts.x_axis if panel_opts and panel_opts.x_axis
              else _x_descriptor(st))
    y_axis = (panel_opts.y_axis if panel_opts and panel_opts.y_axis
              else _y_descriptor(st))
    attrs, meta = _panel_attrs_and_meta(st, M, iw, ih, x_axis, y_axis, panel_bbox)
    return f'<g transform="{transform}"{attrs}>{meta}'


def _render(st, W, H, M):
    """Emit one SVG. (W, H) = canvas dims; M = effective margin already
    resolved by the caller (`_effective_margin` for single-panel,
    `layout._effective_margin` for multi-panel). Splitting margin
    resolution out of `_render` is what lets the data-path skip
    canvas-based scaling."""
    iw = W - M["left"] - M["right"]
    ih = H - M["top"] - M["bottom"]
    transform = f'translate({M["left"]},{M["top"]})'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{_FONT}" font-size="11" '
        f'style="background:#fff"'
        f'{_figure_root_attrs("figure")}>'
        + _panel_open(st, None, transform, M, iw, ih, (0, 0, W, H))
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

    # three-pass draw: background → data → foreground.
    # Each artist's body is wrapped in <g class="plotlet-artist" ...> so
    # AI consumers can read structural attrs (type, label, color, range,
    # etc.) without parsing geometry.
    by_layer = {"background": [], "data": [], "foreground": []}
    for idx, a in enumerate(st["artists"]):
        spec = get_artist(a["type"])
        if spec is None: continue
        by_layer[spec.layer].append((idx, a))
    for layer in ("background", "data", "foreground"):
        for idx, a in by_layer[layer]:
            spec = get_artist(a["type"])
            body = spec.draw(a, _ctx_for(a))
            parts.append(_wrap_artist(a, idx, body))

    # Spines — toggleable per side via `c.spines(top=False, right=False, ...)`,
    # restylable via `c.spines(top={"color": "red", "width": 1.5})`.
    # Tick marks on a hidden side are dropped too (an unanchored tick mark
    # reads as a render bug). Tick *labels* are independent — hiding a
    # spine doesn't remove the labels that side carries.
    # Joined share-pairs show two parallel spines (one per panel)
    # `inner_gap` pixels apart, by design.
    def _side_stroke(side):
        c = st[f"spine_{side}_color"]
        w = st[f"spine_{side}_width"]
        col = _resolve_color(c) if c is not None else _SPINE
        return col, (w if w is not None else _SPW)

    for side, (x1, y1, x2, y2) in (
        ("top",    (0, 0, iw, 0)),
        ("bottom", (0, ih, iw, ih)),
        ("left",   (0, 0, 0, ih)),
        ("right",  (iw, 0, iw, ih)),
    ):
        if not st[f"spine_{side}"]:
            continue
        col, w = _side_stroke(side)
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                     f'stroke="{col}" stroke-width="{w}"/>')

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
    # When marks are suppressed there are no ticks to clear — sit tight
    # against the spine regardless of direction.
    y_label_x = -_TICK_PAD if (y_dir == "in" or not y_marks) else -(_TICK_LEN + _TICK_PAD)

    for t, lbl in zip(x_ticks, x_labels):
        x = x_scale(t)
        if x_marks:
            if st["spine_bottom"]:
                y1, y2 = x_bot_endpoints
                col, sw = _side_stroke("bottom")
                parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y1}" y2="{y2}" '
                             f'stroke="{col}" stroke-width="{sw}"/>')
            if st["spine_top"] and st["x_top"]:
                y1, y2 = x_top_endpoints
                col, sw = _side_stroke("top")
                parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y1}" y2="{y2}" '
                             f'stroke="{col}" stroke-width="{sw}"/>')
        # Drop only labels redundant with a sharing sibling. A small label
        # overflow into a joined neighbor's collapsed margin is acceptable.
        if not suppress_xt:
            parts.append(_rotated_text(str(lbl), x, ih + _TICK_LEN + _TICK_PAD + 8,
                                       x_size, x_rot, axis="x"))

    # y ticks + labels
    for t, lbl in zip(y_ticks, y_labels):
        y = y_scale(t)
        if y_marks:
            if st["spine_left"]:
                x1, x2 = y_left_endpoints
                col, sw = _side_stroke("left")
                parts.append(f'<line x1="{x1}" x2="{x2}" y1="{y:.2f}" y2="{y:.2f}" '
                             f'stroke="{col}" stroke-width="{sw}"/>')
            if st["spine_right"] and st["y_right"]:
                x1, x2 = y_right_endpoints
                col, sw = _side_stroke("right")
                parts.append(f'<line x1="{x1}" x2="{x2}" y1="{y:.2f}" y2="{y:.2f}" '
                             f'stroke="{col}" stroke-width="{sw}"/>')
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
