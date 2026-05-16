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

import datetime
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
from .draw.colors import _resolve_color, TAB10
from .scales import (_LinearScale, _LogScale, _CategoryScale, _SymlogScale,
                      _PowerScale, _TimeScale, _nice_domain, _fmt_tick,
                      _to_epoch, _coerce_time_lim)
from .draw.font import _measure_text
from .draw import text_path, segment
from .utils import histogram, collect_categories
from .registry import RenderContext, get_artist, all_artist_names
from . import builtin_artists  # noqa: F401  — registers built-ins on import

# AI-readable SVG attrs — see docs/AI_ATTRS.md. Every plotlet SVG carries
# `data-plotlet-*` attributes describing plot type, axes, scales, ranges,
# and series labels. Schema is semver-stable, declared via
# `data-plotlet-schema` on the root.
_SCHEMA_VERSION = "2"
# Read from package metadata (pyproject.toml) so there's a single source
# of truth for the version. Independent of `__init__.__version__` to
# avoid a circular import.
_PLOTLET_VERSION = _pkg_version("plotlet")

# Frame metadata methods (title, xlabel, etc.) — these aren't artists,
# they're just state setters. Kept as a fixed set. `theme` joins the set
# so a chart's theme can be recorded and replayed like any other frame
# attribute; `_render` reads it before drawing and wraps the rest of the
# pipeline in an `active_theme(...)` context.
_FRAME_METHODS = {
    "title", "xlabel", "ylabel", "xlim", "ylim",
    "xscale", "yscale", "grid", "legend",
    "xticks", "yticks", "spines", "theme",
    "x_expand", "y_expand", "clip",
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
    kind: str           # "linear" | "log" | "category" | "symlog" | "power" | "sqrt" | "time"
    lo: float = 0.0
    hi: float = 1.0
    cats: list | None = None
    padding: float = field(default_factory=lambda: _D["category_padding"])  # category only; 0 = contiguous bands
    flip: bool = False
    linthresh: float = 1.0  # symlog only
    exponent: float = 1.0   # power only

    def build(self, r0, r1):
        if self.kind == "log":
            return _LogScale(self.lo, self.hi, r0, r1)
        if self.kind == "category":
            return _CategoryScale(self.cats or [], r0, r1, padding=self.padding)
        if self.kind == "symlog":
            return _SymlogScale(self.lo, self.hi, r0, r1, linthresh=self.linthresh)
        if self.kind == "power":
            return _PowerScale(self.lo, self.hi, r0, r1, exponent=self.exponent)
        if self.kind == "sqrt":
            return _PowerScale(self.lo, self.hi, r0, r1, exponent=0.5)
        if self.kind == "time":
            return _TimeScale(self.lo, self.hi, r0, r1)
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
    for a data leaf — it has already incorporated measure-driven growth
    and per-column/row coordination. Non-data leaves (legend, diagram)
    leave this `None` and use their own render paths.
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
    color = _FONTSPEC["color"]
    if not angle:
        anchor = "middle" if axis == "x" else "end"
        return text_path(s, x, y, size, anchor=anchor, color=color)
    text = text_path(s, 0, 0, size, anchor="end", color=color)
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
    if "format" in kw:    st[f"{axis}_format"]    = kw["format"]
    if "minor" in kw:     st[f"{axis}_minor"]     = kw["minor"]
    if "step" in kw:      st[f"{axis}_step"]      = float(kw["step"])
    if "count" in kw:     st[f"{axis}_count"]     = int(kw["count"])
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


def _replay(calls):
    """Walk a Chart's recorded calls into a state dict consumed by the
    renderer. Pure function of `calls` and the artist registry — same input
    + same registry → same output."""
    st = {
        "artists": [], "title": "", "xlabel": "", "ylabel": "",
        "xlim": None, "ylim": None, "xscale": "linear", "yscale": "linear",
        "x_order": None, "y_order": None,
        "x_padding": None, "y_padding": None,
        "x_linthresh": 1.0, "y_linthresh": 1.0,
        "x_exponent": 1.0, "y_exponent": 1.0,
        "x_reverse": False, "y_reverse": False,
        # Data-range expansion (matches matplotlib `axes.xmargin` / ggplot `expand`).
        # None = use spec default; (lo, hi) = explicit fractions of data span.
        "x_expand": None, "y_expand": None,
        # xticks/yticks overrides (None = auto, [] = hide):
        "x_ticks": None, "x_labels": None, "x_rotation": 0, "x_fontsize": None,
        "x_direction": _FRAME["tick_direction"], "x_marks": True,
        "x_top":   _FRAME["tick_top"],
        "x_format": None, "x_minor": None,
        "x_step": None, "x_count": None,
        "y_ticks": None, "y_labels": None, "y_rotation": 0, "y_fontsize": None,
        "y_direction": _FRAME["tick_direction"], "y_marks": True,
        "y_right": _FRAME["tick_right"],
        "y_format": None, "y_minor": None,
        "y_step": None, "y_count": None,
        "spine_top": _FRAME["spine_top"], "spine_right": _FRAME["spine_right"],
        "spine_bottom": _FRAME["spine_bottom"], "spine_left": _FRAME["spine_left"],
        # Per-side color/width overrides; None = inherit spec.json frame defaults.
        # Tick marks on a given side adopt the same side's spine color/width
        # for visual consistency.
        "spine_top_color": None, "spine_right_color": None,
        "spine_bottom_color": None, "spine_left_color": None,
        "spine_top_width": None, "spine_right_width": None,
        "spine_bottom_width": None, "spine_left_width": None,
        "grid": _GRIDSPEC.get("default_on", False), "legend": False,
        # Data-area clipping on by default — artists past xlim/ylim get
        # cropped at the data boundary. Set False (`c.clip(False)`) for
        # matplotlib-default behavior where lines and large markers can
        # bleed into the margin space.
        "clip": True,
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
            if "order" in kw:     st["x_order"] = list(kw["order"])
            if "padding" in kw:   st["x_padding"] = kw["padding"]
            if "linthresh" in kw: st["x_linthresh"] = float(kw["linthresh"])
            if "exponent" in kw:  st["x_exponent"] = float(kw["exponent"])
            if "reverse" in kw:   st["x_reverse"] = bool(kw["reverse"])
        elif name == "yscale":
            st["yscale"] = args[0]
            if "order" in kw:     st["y_order"] = list(kw["order"])
            if "padding" in kw:   st["y_padding"] = kw["padding"]
            if "linthresh" in kw: st["y_linthresh"] = float(kw["linthresh"])
            if "exponent" in kw:  st["y_exponent"] = float(kw["exponent"])
            if "reverse" in kw:   st["y_reverse"] = bool(kw["reverse"])
        elif name == "xticks": _record_ticks(st, "x", args, kw)
        elif name == "yticks": _record_ticks(st, "y", args, kw)
        elif name == "x_expand": st["x_expand"] = _normalize_expand(args)
        elif name == "y_expand": st["y_expand"] = _normalize_expand(args)
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
        elif name == "clip":   st["clip"] = bool(args[0]) if args else True
        elif name == "theme":
            # `theme` is applied outside replay (by `active_theme(...)` in
            # `Chart.to_svg`) so the spec dicts are already on the right
            # values by the time we get here. No state to record.
            pass
    return st


def _effective_margin(leaf, st=None) -> dict:
    """Margin used at render time. Reads dimension state directly off the
    leaf Chart.

    Combines `_enforce_floors(spec/user margin)` with the content-driven
    `_required_margin(st, data_w, data_h)` by taking the per-side max —
    so the canvas grows as needed to fit long tick labels, titles, and
    axis labels rather than letting them overflow. Caller passes the
    replayed `st`; callers without one get only the floor-applied spec
    margin."""
    M_floor = _enforce_floors(leaf._margin)
    if st is None:
        return M_floor
    M_req = _required_margin(st, leaf._data_width, leaf._data_height)
    return {side: max(M_floor[side], M_req[side]) for side in M_floor}




# ---------------------------------------------------------------------------
# Domain helpers — shared by the panel renderer and the layout pre-pass.
# ---------------------------------------------------------------------------

def _scan_domain(artists, axis):
    """Collect all values an artist contributes to a given axis ('x' or 'y').

    `datetime.date` / `datetime.datetime` values are coerced to POSIX seconds
    (UTC) so the rest of the autoscaling pipeline can stay numeric."""
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
            if isinstance(v, (datetime.date, datetime.datetime)):
                v = _to_epoch(v)
            if v < lo: lo = v
            if v > hi: hi = v
    return lo, hi


def _is_temporal_axis(artists, axis):
    """True when the first non-None value an artist contributes on `axis`
    is a `datetime.date` or `datetime.datetime`. Mirrors the
    `_is_categorical_axis` first-value-wins rule."""
    for a in artists:
        spec = get_artist(a["type"])
        if spec is None: continue
        fn = spec.xdomain if axis == "x" else spec.ydomain
        vals = fn(a)
        if vals is None: continue
        for v in vals:
            if v is None: continue
            return isinstance(v, (datetime.date, datetime.datetime))
    return False


def _resolve_tick_formatter(user_fmt, scale):
    """Pick the formatter for tick labels on `scale`.

    Precedence: user-supplied `format=` (from `xticks(format=...)`) >
    scale's own `format_tick` > the package default `_fmt_tick`. A user
    format-string is wrapped in a callable; a callable is used directly."""
    if user_fmt is None:
        return getattr(scale, "format_tick", _fmt_tick)
    if callable(user_fmt):
        return user_fmt
    if isinstance(user_fmt, str):
        return user_fmt.format
    raise TypeError(
        f"xticks/yticks(format=) expects a format string or a callable; "
        f"got {type(user_fmt).__name__}"
    )


def _auto_major_ticks(scale, n, step, count):
    """Major-tick positions for `scale`, with optional overrides.

    `step` (numeric) forces a fixed step starting at `ceil(scale.d0 / step)
    * step`. `count` (int) replaces the heuristic `n` (panel-size-derived)
    with an exact tick count. Both default to None, meaning fall through
    to the scale's own `ticks(n)` behavior."""
    if step is not None:
        lo, hi = (scale.d0, scale.d1) if scale.d0 <= scale.d1 else (scale.d1, scale.d0)
        eps = abs(step) * 1e-9
        start = math.ceil(lo / step - 1e-9) * step
        out, t = [], start
        # Guard runaway loops on bad inputs.
        for _ in range(10000):
            if t > hi + eps:
                break
            out.append(round(t, 10))
            t += step
        return out
    if count is not None:
        return scale.ticks(max(2, count))
    return scale.ticks(n)


def _auto_minor_ticks(scale, major_ticks):
    """Default minor-tick positions for `scale`. Linear-shaped scales:
    4 subdivisions between adjacent majors; log: integer multipliers
    (2..9) within each decade."""
    kind = type(scale).__name__
    out = []
    if kind == "_LogScale":
        a = math.floor(scale.l0)
        b = math.ceil(scale.l1)
        for k in range(int(a), int(b) + 1):
            decade = 10 ** k
            for m in range(2, 10):
                v = m * decade
                if scale.d0 <= v <= scale.d1:
                    out.append(v)
        return out
    if len(major_ticks) < 2:
        return []
    nums = [float(t) for t in major_ticks]
    for i in range(len(nums) - 1):
        a, b = nums[i], nums[i + 1]
        step = (b - a) / 5
        for j in range(1, 5):
            out.append(a + step * j)
    return out


def _resolve_minor_ticks(user_minor, scale, major_ticks):
    """Map the user's `minor=` setting to a list of minor positions.
    None/False → none; True → auto from `_auto_minor_ticks`; sequence →
    use as-is."""
    if user_minor is None or user_minor is False:
        return []
    if user_minor is True:
        return _auto_minor_ticks(scale, major_ticks)
    return list(user_minor)


def _normalize_expand(args):
    """Normalize x_expand/y_expand call args into `(lo, hi)` fractions.
    Accepts a single number (symmetric) or two numbers (lo, hi)."""
    if len(args) == 1:
        v = float(args[0])
        return (v, v)
    if len(args) == 2:
        return (float(args[0]), float(args[1]))
    raise TypeError(
        f"x_expand/y_expand expects 1 or 2 numbers, got {len(args)}"
    )


def _resolve_expand(st_value, tight, axis):
    """Effective `(lo, hi)` expand fractions for an axis.
    None state → spec default for non-tight axes, zero for tight (so imshow
    stays tight by default). Explicit user value wins in all cases."""
    if st_value is not None:
        return st_value
    if tight:
        return (0.0, 0.0)
    return tuple(_D["x_expand" if axis == "x" else "y_expand"])


def _resolve_domain(lo, hi, user_lim, scale_kind, force_zero=False, tight=False,
                    expand=(0.0, 0.0)):
    """Apply user override, log snapping, then either nice-rounding OR
    expand padding (not both — they solve the same 'breathing room' problem
    and stacking double-counts).

    `tight=True` skips the nice path. `expand=(lo, hi)` adds a precise
    symmetric buffer in data space; `force_zero` with `lo==0` skips
    `expand_lo` so bars stay sat on the y=0 baseline."""
    if user_lim is not None:
        return user_lim
    if math.isinf(lo):
        return (0, 1)
    if force_zero and lo > 0:
        lo = 0
    if lo == hi:
        return (lo - 0.5, hi + 0.5)
    expand_lo, expand_hi = expand
    has_expand = expand_lo != 0.0 or expand_hi != 0.0
    if scale_kind == "log":
        if lo > 0 and hi > 0:
            if has_expand:
                lo_n, hi_n = lo, hi
            else:
                lo_n = 10 ** math.floor(math.log10(lo))
                hi_n = 10 ** math.ceil(math.log10(hi))
            log_span = math.log10(hi_n) - math.log10(lo_n)
            if log_span > 0:
                if not (force_zero and lo_n <= 0):
                    lo_n = lo_n / (10 ** (expand_lo * log_span))
                hi_n = hi_n * (10 ** (expand_hi * log_span))
            return (lo_n, hi_n)
        return (lo, hi)
    if tight or has_expand:
        lo_n, hi_n = lo, hi
    else:
        lo_n, hi_n = _nice_domain(lo, hi)
    span = hi_n - lo_n
    if not (force_zero and lo_n == 0):
        lo_n -= expand_lo * span
    hi_n += expand_hi * span
    return (lo_n, hi_n)


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


def _prebin_hist(st):
    """Compute hist bins on `st["artists"]` so they participate in domain
    scanning. Idempotent (guarded by `_bins` presence)."""
    for a in st["artists"]:
        if a["type"] == "hist" and "_bins" not in a:
            a["_bins"] = histogram(a["data"], a["opts"].get("bins", 10))


def _artist_axis_order(artists, axis):
    """Return the first artist-supplied order for `axis`, or None."""
    for a in artists:
        spec = get_artist(a["type"])
        if spec is None or spec.axis_order is None:
            continue
        hint = spec.axis_order(a)
        if hint and axis in hint:
            return list(hint[axis])
    return None


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
      2. an artist's `axis_order` hook (e.g. dendrogram's leaf order)
      3. `xscale("category")` with no order → alphabetical of unique x values
      4. any artist contributes string-valued x (bar, scatter on strings,
         …) → alphabetical of unique x values
      5. otherwise → linear/log path
    """
    _prebin_hist(st)
    artists = st["artists"]
    explicit_cat = st["xscale"] == "category"
    auto_cat = _is_categorical_axis(artists, "x")

    if explicit_cat or auto_cat:
        if st["x_order"] is not None:
            cats = list(st["x_order"])
        else:
            cats = _artist_axis_order(artists, "x") or collect_categories(artists, "x")
        padding = _D["category_padding"] if st["x_padding"] is None else st["x_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding)

    is_time = st["xscale"] == "time" or _is_temporal_axis(artists, "x")
    x_lo, x_hi = _scan_domain(artists, "x")
    x_tight = _axis_is_tight(artists, "x")
    x_force_zero = _any_artist_force_zero(artists, "x")
    xlim = _coerce_time_lim(st["xlim"]) if is_time else st["xlim"]
    x_scale_kind = "time" if is_time else st["xscale"]
    x_min, x_max = _resolve_domain(x_lo, x_hi, xlim, x_scale_kind,
                                    force_zero=x_force_zero,
                                    tight=x_tight,
                                    expand=_resolve_expand(st["x_expand"], x_tight, "x"))
    return _AxisDescriptor(kind=x_scale_kind, lo=x_min, hi=x_max,
                           flip=st["x_reverse"],
                           linthresh=st["x_linthresh"],
                           exponent=st["x_exponent"])


def _any_artist_flips_y(artists) -> bool:
    """True if any artist on the panel declares (via its `flips_y_axis`
    spec hook) that the y-axis should render inverted."""
    for a in artists:
        spec = get_artist(a["type"])
        if spec is not None and spec.flips_y_axis is not None and spec.flips_y_axis(a):
            return True
    return False


def _any_artist_force_zero(artists, axis: str) -> bool:
    """True if any artist on the panel declares (via `force_zero_x` /
    `force_zero_y` on its spec) that the axis should anchor at zero."""
    attr = "force_zero_x" if axis == "x" else "force_zero_y"
    for a in artists:
        spec = get_artist(a["type"])
        if spec is not None and getattr(spec, attr, False):
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
        if st["y_order"] is not None:
            cats = list(st["y_order"])
        else:
            cats = _artist_axis_order(artists, "y") or collect_categories(artists, "y")
        padding = _D["category_padding"] if st["y_padding"] is None else st["y_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding)

    is_time = st["yscale"] == "time" or _is_temporal_axis(artists, "y")
    force_zero = _any_artist_force_zero(artists, "y")
    y_lo, y_hi = _scan_domain(artists, "y")
    y_tight = _axis_is_tight(artists, "y")
    ylim = _coerce_time_lim(st["ylim"]) if is_time else st["ylim"]
    y_scale_kind = "time" if is_time else st["yscale"]
    y_min, y_max = _resolve_domain(y_lo, y_hi, ylim, y_scale_kind,
                                    force_zero=force_zero,
                                    tight=y_tight,
                                    expand=_resolve_expand(st["y_expand"], y_tight, "y"))
    return _AxisDescriptor(kind=y_scale_kind, lo=y_min, hi=y_max,
                           flip=_any_artist_flips_y(artists) or st["y_reverse"],
                           linthresh=st["y_linthresh"],
                           exponent=st["y_exponent"])


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
        if anchor["x_order"] is not None:
            cats = list(anchor["x_order"])
        else:
            cats = _artist_axis_order(all_artists, "x") or collect_categories(all_artists, "x")
        padding = _D["category_padding"] if anchor["x_padding"] is None else anchor["x_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding)
    is_time = anchor["xscale"] == "time" or _is_temporal_axis(all_artists, "x")
    x_lo, x_hi = _scan_domain(all_artists, "x")
    x_tight = _axis_is_tight(all_artists, "x")
    x_force_zero = _any_artist_force_zero(all_artists, "x")
    xlim = _coerce_time_lim(anchor["xlim"]) if is_time else anchor["xlim"]
    x_scale_kind = "time" if is_time else anchor["xscale"]
    x_min, x_max = _resolve_domain(x_lo, x_hi, xlim, x_scale_kind,
                                    force_zero=x_force_zero,
                                    tight=x_tight,
                                    expand=_resolve_expand(anchor["x_expand"], x_tight, "x"))
    return _AxisDescriptor(kind=x_scale_kind, lo=x_min, hi=x_max,
                           flip=anchor["x_reverse"],
                           linthresh=anchor["x_linthresh"],
                           exponent=anchor["x_exponent"])


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
        if anchor["y_order"] is not None:
            cats = list(anchor["y_order"])
        else:
            cats = _artist_axis_order(all_artists, "y") or collect_categories(all_artists, "y")
        padding = _D["category_padding"] if anchor["y_padding"] is None else anchor["y_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding)
    is_time = anchor["yscale"] == "time" or _is_temporal_axis(all_artists, "y")
    force_zero = _any_artist_force_zero(all_artists, "y")
    y_lo, y_hi = _scan_domain(all_artists, "y")
    y_tight = _axis_is_tight(all_artists, "y")
    ylim = _coerce_time_lim(anchor["ylim"]) if is_time else anchor["ylim"]
    y_scale_kind = "time" if is_time else anchor["yscale"]
    y_min, y_max = _resolve_domain(y_lo, y_hi, ylim, y_scale_kind,
                                    force_zero=force_zero,
                                    tight=y_tight,
                                    expand=_resolve_expand(anchor["y_expand"], y_tight, "y"))
    return _AxisDescriptor(kind=y_scale_kind, lo=y_min, hi=y_max,
                           flip=_any_artist_flips_y(all_artists) or anchor["y_reverse"],
                           linthresh=anchor["y_linthresh"],
                           exponent=anchor["y_exponent"])


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
    if x_axis.kind == "category" or not x_axis.flip:
        x_scale = x_axis.build(0, dw)
    else:
        x_scale = x_axis.build(dw, 0)
    if y_axis.kind == "category" or y_axis.flip:
        y_scale = y_axis.build(0, dh)
    else:
        y_scale = y_axis.build(dh, 0)

    # Same tick-density rule as `_render_inner`.
    x_n = max(2, min(8, int(dw // 65)))
    y_n = max(2, min(8, int(dh // 40)))
    x_ticks  = (st["x_ticks"] if st["x_ticks"] is not None
                else _auto_major_ticks(x_scale, x_n, st["x_step"], st["x_count"]))
    y_ticks  = (st["y_ticks"] if st["y_ticks"] is not None
                else _auto_major_ticks(y_scale, y_n, st["y_step"], st["y_count"]))
    x_fmt = _resolve_tick_formatter(st["x_format"], x_scale)
    y_fmt = _resolve_tick_formatter(st["y_format"], y_scale)
    x_labels = (st["x_labels"] if st["x_labels"] is not None
                else [x_fmt(t) for t in x_ticks])
    y_labels = (st["y_labels"] if st["y_labels"] is not None
                else [y_fmt(t) for t in y_ticks])

    x_size = st["x_fontsize"] if st["x_fontsize"] is not None else tick_size
    y_size = st["y_fontsize"] if st["y_fontsize"] is not None else tick_size
    x_rot  = st["x_rotation"] or 0
    y_rot  = st["y_rotation"] or 0
    x_dir, y_dir = st["x_direction"], st["y_direction"]
    x_marks, y_marks = st["x_marks"], st["y_marks"]

    # Outward / inout tick marks reach past the spine; "in" is internal only.
    out_x = _FRAME["tick_length"] if x_marks and x_dir != "in" else 0
    out_y = _FRAME["tick_length"] if y_marks and y_dir != "in" else 0

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
    bottom = out_x + _FRAME["tick_pad"] + 8 + xtl_bbox_h
    if st["xlabel"]:
        bottom += label_size + 8

    # Left: outward tick + tick_pad + tick label bbox + ylabel allowance.
    # ylabel sits at canvas-left + 12 px (rotated -90), so it occupies
    # roughly `label_size` in the horizontal direction.
    left = out_y + _FRAME["tick_pad"] + ytl_bbox_w
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


# ---------------------------------------------------------------------------
# AI-readable SVG attrs — schema and helpers
# ---------------------------------------------------------------------------
# Every plotlet SVG carries `data-plotlet-*` attributes describing plot type,
# axes, scales, ranges, and series labels. Schema is semver-stable, declared
# via `data-plotlet-schema` on the root.

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
        attrs["xlim"] = f"{x_axis.lo:.12g},{x_axis.hi:.12g}"
    if y_axis.kind != "category":
        attrs["ylim"] = f"{y_axis.lo:.12g},{y_axis.hi:.12g}"
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
        f'viewBox="0 0 {W} {H}" font-family="{_FONTSPEC["family"]}" font-size="11" '
        f'style="background:{SPEC["figure"]["background"]}"'
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
    x_ticks = (st["x_ticks"] if st["x_ticks"] is not None
               else _auto_major_ticks(x_scale, x_n, st["x_step"], st["x_count"]))
    y_ticks = (st["y_ticks"] if st["y_ticks"] is not None
               else _auto_major_ticks(y_scale, y_n, st["y_step"], st["y_count"]))
    x_fmt = _resolve_tick_formatter(st["x_format"], x_scale)
    y_fmt = _resolve_tick_formatter(st["y_format"], y_scale)
    x_labels = st["x_labels"] if st["x_labels"] is not None else [x_fmt(t) for t in x_ticks]
    y_labels = st["y_labels"] if st["y_labels"] is not None else [y_fmt(t) for t in y_ticks]

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
                             f'stroke="{_GRIDSPEC["color"]}" stroke-width="{gw}" stroke-dasharray="{gd}"/>')
        for t in y_ticks:
            y = y_scale(t)
            parts.append(f'<line x1="0" x2="{iw}" y1="{y:.2f}" y2="{y:.2f}" '
                         f'stroke="{_GRIDSPEC["color"]}" stroke-width="{gw}" stroke-dasharray="{gd}"/>')

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
    clip_data = st.get("clip", True)
    for layer in ("background", "data", "foreground"):
        if not by_layer[layer]:
            continue
        # Clip the data layer to the data area so an artist drawing
        # outside the visible xlim/ylim (zoom insets, explicit xlim that
        # excludes data) can't paint over tick labels or the parent.
        # Nested <svg> with overflow="hidden" establishes the clip; SVG2
        # makes that the default for nested-svg but SVG1.1 viewers leave
        # overflow visible, so we set it explicitly. Caller can opt out
        # via `c.clip(False)` for matplotlib-default no-clip behavior.
        if layer == "data" and clip_data:
            parts.append(f'<svg x="0" y="0" width="{iw}" height="{ih}" overflow="hidden">')
        for idx, a in by_layer[layer]:
            spec = get_artist(a["type"])
            body = spec.draw(a, _ctx_for(a))
            parts.append(_wrap_artist(a, idx, body))
        if layer == "data" and clip_data:
            parts.append('</svg>')

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
        col = _resolve_color(c) if c is not None else _FRAME["color"]
        return col, (w if w is not None else _FRAME["width"])

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
    bot_in, bot_out = ih - _FRAME["tick_length"], ih + _FRAME["tick_length"]  # bottom spine offsets
    top_in, top_out = _FRAME["tick_length"], -_FRAME["tick_length"]           # top spine offsets
    if x_dir == "in":      x_bot_endpoints, x_top_endpoints = (ih, bot_in),  (0, top_in)
    elif x_dir == "out":   x_bot_endpoints, x_top_endpoints = (ih, bot_out), (0, top_out)
    else:                  x_bot_endpoints, x_top_endpoints = (bot_out, bot_in), (top_out, top_in)
    left_in, left_out  = _FRAME["tick_length"], -_FRAME["tick_length"]        # left spine offsets (x = 0)
    right_in, right_out = iw - _FRAME["tick_length"], iw + _FRAME["tick_length"]
    if y_dir == "in":      y_left_endpoints, y_right_endpoints = (0, left_in),  (iw, right_in)
    elif y_dir == "out":   y_left_endpoints, y_right_endpoints = (0, left_out), (iw, right_out)
    else:                  y_left_endpoints, y_right_endpoints = (left_out, left_in), (right_out, right_in)

    # y-axis labels need to clear an outward/inout tick mark; x-axis labels
    # already sit far enough below the spine to clear all three modes.
    # When marks are suppressed there are no ticks to clear — sit tight
    # against the spine regardless of direction.
    y_label_x = -_FRAME["tick_pad"] if (y_dir == "in" or not y_marks) else -(_FRAME["tick_length"] + _FRAME["tick_pad"])

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
            parts.append(_rotated_text(str(lbl), x, ih + _FRAME["tick_length"] + _FRAME["tick_pad"] + 8,
                                       x_size, x_rot, axis="x"))

    # Minor ticks — shorter than majors (frame.minor_tick_ratio), no
    # labels. Emit only when the user opted in via xticks(minor=True) or
    # xticks(minor=[...]).
    x_minor = _resolve_minor_ticks(st["x_minor"], x_scale, x_ticks)
    if x_minor and x_marks:
        minor_len = _FRAME["tick_length"] * _FRAME["minor_tick_ratio"]
        for t in x_minor:
            x = x_scale(t)
            if not math.isfinite(x):
                continue
            if st["spine_bottom"]:
                col, sw = _side_stroke("bottom")
                if x_dir == "in":      y1, y2 = ih, ih - minor_len
                elif x_dir == "out":   y1, y2 = ih, ih + minor_len
                else:                  y1, y2 = ih + minor_len, ih - minor_len
                parts.append(segment(x, y1, x, y2, color=col, width=sw))
            if st["spine_top"] and st["x_top"]:
                col, sw = _side_stroke("top")
                if x_dir == "in":      y1, y2 = 0, minor_len
                elif x_dir == "out":   y1, y2 = 0, -minor_len
                else:                  y1, y2 = -minor_len, minor_len
                parts.append(segment(x, y1, x, y2, color=col, width=sw))

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

    y_minor = _resolve_minor_ticks(st["y_minor"], y_scale, y_ticks)
    if y_minor and y_marks:
        minor_len = _FRAME["tick_length"] * _FRAME["minor_tick_ratio"]
        for t in y_minor:
            y = y_scale(t)
            if not math.isfinite(y):
                continue
            if st["spine_left"]:
                col, sw = _side_stroke("left")
                if y_dir == "in":      x1, x2 = 0, minor_len
                elif y_dir == "out":   x1, x2 = 0, -minor_len
                else:                  x1, x2 = -minor_len, minor_len
                parts.append(segment(x1, y, x2, y, color=col, width=sw))
            if st["spine_right"] and st["y_right"]:
                col, sw = _side_stroke("right")
                if y_dir == "in":      x1, x2 = iw, iw - minor_len
                elif y_dir == "out":   x1, x2 = iw, iw + minor_len
                else:                  x1, x2 = iw + minor_len, iw - minor_len
                parts.append(segment(x1, y, x2, y, color=col, width=sw))

    # xlabel / ylabel / title live in margin space; drop when that margin
    # is collapsed against a joined neighbor.
    text_color = _FONTSPEC["color"]
    if st["xlabel"] and not hide_b:
        parts.append(text_path(st["xlabel"], iw / 2, ih + M["bottom"] - 8,
                                label_size, anchor="middle", color=text_color))
    if st["ylabel"] and not hide_l:
        ylabel_path = text_path(st["ylabel"], 0, 0, label_size,
                                anchor="middle", color=text_color)
        parts.append(f'<g transform="translate({-(M["left"] - 12)},{ih/2}) rotate(-90)">'
                     f'{ylabel_path}</g>')
    if st["title"] and not hide_t:
        parts.append(text_path(st["title"], iw / 2, -10, title_size,
                                anchor="middle", color=text_color))

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
                         f'fill="{_LEGSPEC["background"]}" stroke="{_FRAME["color"]}" '
                         f'stroke-width="{_FRAME["width"]}" opacity="{_LEGSPEC["opacity"]}"/>')
            for i, a in enumerate(labeled):
                ry = pad_y + i * row_h + row_h / 2
                spec = get_artist(a["type"])
                if spec is not None and spec.legend_swatch is not None:
                    parts.append(spec.legend_swatch(a, _ctx_for(a), pad_x, ry))
                else:
                    parts.append(f'<line x1="{pad_x}" x2="{pad_x + sw}" y1="{ry}" y2="{ry}" '
                                 f'stroke="{a["_color"]}" stroke-width="{_D["linewidth"]}"/>')
                parts.append(text_path(a["opts"]["label"], pad_x + sw + 6, ry + 4,
                                        tick_size, anchor="start", color=text_color))
            parts.append('</g>')

    # Inset axes — render each as its own SVG fragment positioned by
    # axes-fraction within this leaf's data area. Drawn last so they
    # sit on top of the data layer (and on top of the legend). Wrapped
    # in a data-area clip so the inset's canvas can't paint over the
    # parent's title/labels if its own margins overhang.
    insets = st.get("insets") or []
    if insets:
        parts.append(f'<svg x="0" y="0" width="{iw}" height="{ih}" overflow="hidden">')
    for rect, inset_chart in insets:
        x_frac, y_frac, w_frac, h_frac = rect
        # Render the inset first; this populates `_last_M_eff` so we can
        # offset the translate to align the inset's data region (not its
        # canvas) with the requested axes-fraction rect.
        inset_svg = inset_chart._to_svg_unchecked()
        inset_M = inset_chart._last_M_eff or {"left": 0, "right": 0, "top": 0, "bottom": 0}
        # Bottom-left origin: y-frac 0 = bottom of data, 1 = top.
        # Subtract the inset's own margin so its data region (not its
        # canvas) lands at the requested fraction of the parent's data.
        tx = x_frac * iw - inset_M["left"]
        ty = (1 - y_frac - h_frac) * ih - inset_M["top"]
        # Opaque background covering the inset's data area only — tick
        # labels in the inset's margins stay transparent (matches
        # matplotlib Axes facecolor and ggplot panel.background defaults).
        bg_x = inset_M["left"]
        bg_y = inset_M["top"]
        bg_w = inset_chart._data_width
        bg_h = inset_chart._data_height
        parts.append(f'<g transform="translate({tx:.2f},{ty:.2f})" '
                      f'data-plotlet-kind="inset">'
                      f'<rect x="{bg_x}" y="{bg_y}" width="{bg_w}" height="{bg_h}" '
                      f'fill="{SPEC["figure"]["background"]}"/>'
                      f'{inset_svg}</g>')
    if insets:
        parts.append('</svg>')

    return "".join(parts)
