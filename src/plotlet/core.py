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
    SPEC, _SIZESPEC, _MARGIN_FLOOR, _FRAME, _GRIDSPEC, _FONTSPEC, _LEGSPEC,
    _LAYOUTSPEC, _PADSPEC, _D, _DASH,
)
from .draw import resolve_color, TAB10
from .scales import (_LinearScale, _LogScale, _CategoryScale, _SymlogScale,
                      _PowerScale, _TimeScale, _nice_domain, _fmt_tick,
                      _to_epoch, _coerce_time_lim)
from .draw import measure_text, cap_height, descender
from .draw import text_path, segment, rect
from . import _regions
from .utils import histogram, collect_categories
from .registry import RenderContext, get_artist, all_artist_names
from . import artists  # noqa: F401  — registers built-ins on import

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
# Inline legend position tokens that overlay the data area (vs reserve
# margin space outside it). Used to drive both placement and the "draw a
# readability background?" decision — outside positions skip the rect
# (ggplot/vega-lite default); inside positions keep a translucent fill.
_INSIDE_POSITIONS = frozenset({
    "top-right", "top-left", "bottom-right", "bottom-left", "center",
})

_FRAME_METHODS = {
    "title", "xlabel", "ylabel", "xlim", "ylim",
    "xscale", "yscale", "grid", "legend",
    "xticks", "yticks", "spines", "theme",
    "x_expand", "y_expand", "clip", "facecolor",
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
    splits: list | None = None   # category only: band indices that begin a block
    split_gap: float = 0.0       # category only: px reserved before each split
    groups: dict | None = None   # category only: cat -> group label; scale derives splits

    def build(self, r0, r1):
        if self.kind == "log":
            return _LogScale(self.lo, self.hi, r0, r1)
        if self.kind == "category":
            return _CategoryScale(self.cats or [], r0, r1, padding=self.padding,
                                  splits=self.splits, gap=self.split_gap,
                                  groups=self.groups)
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


def _tick_label(s, x, y, size, angle, axis,
                fontstyle="normal", decoration="none", tag=None):
    """Render a single tick label as text-as-paths.

    Called for every tick label on every render — rotation is opt-in via
    `angle`. When `angle=0` (default) routes straight to `text_path` with
    the side-appropriate anchor; when nonzero, emits the glyphs at origin
    and wraps in `<g transform="translate(x,y) rotate(-angle)">`. The
    `angle` argument uses the convention positive = CCW on screen;
    SVG's native rotation is CW, so we negate at emission.

    Anchor direction depends on axis + rotation sign so the rotated text
    always grows AWAY from the data area: for bottom x-tick labels,
    positive rotation (CCW) uses anchor="end" (text extends downward);
    negative rotation (CW) uses anchor="start" (also extends downward —
    without this, CW rotation would push labels into the chart body).

    `fontstyle="italic"` propagates through `text_path` for synthesized
    oblique tick labels (common bio convention for gene names).
    `decoration="underline"|"overline"|"line-through"` adds a stroke line
    at the conventional offset."""
    color = _FONTSPEC["color"]
    if not angle:
        anchor = "middle" if axis == "x" else "end"
        return text_path(s, x, y, size, anchor=anchor, color=color,
                         fontstyle=fontstyle, decoration=decoration,
                         tag=tag)
    if axis == "x":
        anchor = "end" if angle > 0 else "start"
    else:
        anchor = "end"
    # Rotate via `text_path(..., rotate=angle)` so its bbox recording
    # captures the post-rotation hull. SVG-wise, rotating around the
    # anchor point (x, y) is equivalent to translating + rotating
    # around the origin; one transform attribute does both.
    return text_path(s, x, y, size, anchor=anchor, color=color,
                     fontstyle=fontstyle, decoration=decoration,
                     rotate=angle, tag=tag)


def _record_scale(st, axis, args, kw, *, from_default=False):
    """Decode an xscale()/yscale() call into state.

    `args[0]` is the scale kind ("linear", "log", "symlog", "sqrt",
    "category"). Per-kind kwargs (`order`, `padding`, `linthresh`,
    `exponent`, `reverse`) are stashed on the matching `<axis>_*`
    keys when supplied; omitted kwargs leave defaults untouched.

    `from_default=True` (only set when the call was emitted by an
    artist's `frame_defaults`) routes `order=` to `<axis>_order_default`
    instead of `<axis>_order`, so a peer artist's `axis_order` hook can
    win over an artist-suggested order while a user-explicit
    `c.xscale(order=...)` still wins over both."""
    st[f"{axis}scale"] = args[0]
    if "order" in kw:
        target = f"{axis}_order_default" if from_default else f"{axis}_order"
        st[target] = list(kw["order"])
    if "padding" in kw:   st[f"{axis}_padding"]   = kw["padding"]
    if "linthresh" in kw: st[f"{axis}_linthresh"] = float(kw["linthresh"])
    if "exponent" in kw:  st[f"{axis}_exponent"]  = float(kw["exponent"])
    if "reverse" in kw:   st[f"{axis}_reverse"]   = bool(kw["reverse"])
    if "splits" in kw:    st[f"{axis}_splits"]    = list(kw["splits"]) if kw["splits"] else None
    if "split_gap" in kw: st[f"{axis}_split_gap"] = float(kw["split_gap"])
    if "groups" in kw:    st[f"{axis}_groups"]    = dict(kw["groups"]) if kw["groups"] else None


def _record_ticks(st, axis, args, kw):
    """Decode the xticks()/yticks() call into state.

    Signature: xticks(ticks=None, labels=None, *, rotation=0, fontsize=None).
    Accepts the first arg positionally; pass `[]` to hide. Omitted
    kwargs leave the corresponding state alone, so `c.xticks(rotation=45)`
    rotates without disturbing auto positions.
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
        if v is False:
            # Symmetric counterpart to `marks=False` — keep auto tick
            # positions + tick marks, suppress the labels. Useful when
            # tick marks are meant as visual cues but their numeric
            # labels would crowd a different label (e.g. chrom name as
            # xlabel under per-chrom tick marks).
            st[f"{axis}_show_labels"] = False
        else:
            st[f"{axis}_labels"] = list(v) if v is not None else None
    if "rotation" in kw:  st[f"{axis}_rotation"]  = kw["rotation"]
    if "fontsize" in kw:  st[f"{axis}_fontsize"]  = kw["fontsize"]
    if "fontstyle" in kw: st[f"{axis}_fontstyle"] = kw["fontstyle"]
    if "decoration" in kw: st[f"{axis}_decoration"] = kw["decoration"]
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
        "x_splits": None, "y_splits": None,
        "x_split_gap": 0.0, "y_split_gap": 0.0,
        "x_groups": None, "y_groups": None,
        "x_order_default": None, "y_order_default": None,
        # Data-range expansion: extra fraction of span padded around the data.
        # None = use spec default; (lo, hi) = explicit fractions of data span.
        "x_expand": None, "y_expand": None,
        # xticks/yticks overrides (None = auto, [] = hide):
        "x_ticks": None, "x_labels": None, "x_rotation": 0, "x_fontsize": None,
        "x_fontstyle": None, "x_decoration": None,
        "x_direction": _FRAME["tick_direction"], "x_marks": True,
        "x_show_labels": True,
        "x_top":   _FRAME["tick_top"],
        "x_format": None, "x_minor": None,
        "x_step": None, "x_count": None,
        "y_ticks": None, "y_labels": None, "y_rotation": 0, "y_fontsize": None,
        "y_fontstyle": None, "y_decoration": None,
        "y_direction": _FRAME["tick_direction"], "y_marks": True,
        "y_show_labels": True,
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
        "spine_top_linestyle": None, "spine_right_linestyle": None,
        "spine_bottom_linestyle": None, "spine_left_linestyle": None,
        "grid": _GRIDSPEC.get("default_on", False), "legend": False,
        # Inline-legend placement. Outside tokens: `"right"` (default),
        # `"left"`, `"top"`, `"bottom"` — reserve margin space beside the
        # data area. Inside tokens: `"top-right"`, `"top-left"`,
        # `"bottom-right"`, `"bottom-left"`, `"center"` — overlay the data
        # area. `"inside"` is a back-compat alias for `"top-right"`.
        # Modeled on vega-lite's `legend.orient`.
        "legend_position": "right",
        # Data-area clipping on by default — artists past xlim/ylim get
        # cropped at the data boundary. Set False (`c.clip(False)`) to
        # let lines and large markers bleed into the margin space.
        "clip": True,
        "facecolor": None,
    }
    for call in calls:
        # Calls are stored as 3-tuples `(name, args, kw)` from user code
        # or 4-tuples `(name, args, kw, from_default=True)` when emitted by
        # an artist's `frame_defaults` (see Chart.__getattr__). The flag
        # lets `_record_scale` distinguish a frame-default `order=` (loses
        # to a peer artist's `axis_order` hook) from a user-explicit one.
        if len(call) == 4:
            name, args, kw, from_default = call
        else:
            name, args, kw = call
            from_default = False
        spec = get_artist(name)
        if spec is not None:
            # Pass fresh copies so a `kw.pop(...)` inside `record()` doesn't
            # corrupt the stored call dict — re-renders walk the same list.
            # `record()` returns a single dict for one-series artists or a
            # list of dicts for long-form expansions (line, scatter split
            # by color/group/linestyle levels).
            call_args = list(args)
            call_kw = dict(kw)
            # First-positional-is-data sugar: `c.line(df, x=, y=)` is the
            # same as `c.line(data=df, x=, y=)`. Opt-in via
            # `ArtistSpec.accepts_data_positional=True`. Keeps the long-form
            # call shape from carrying a `data=` keyword on every site
            # while keeping the wide-form `(xs, ys)` shape deprecated.
            if (spec.accepts_data_positional and len(call_args) == 1
                    and "data" not in call_kw):
                call_kw["data"] = call_args.pop(0)
            result = spec.record(call_args, call_kw)
            if isinstance(result, list):
                st["artists"].extend(result)
            else:
                st["artists"].append(result)
        elif name == "title":  st["title"] = args[0]
        elif name == "xlabel": st["xlabel"] = args[0]
        elif name == "ylabel": st["ylabel"] = args[0]
        elif name == "xlim":   st["xlim"] = (args[0], args[1])
        elif name == "ylim":   st["ylim"] = (args[0], args[1])
        elif name == "xscale": _record_scale(st, "x", args, kw, from_default=from_default)
        elif name == "yscale": _record_scale(st, "y", args, kw, from_default=from_default)
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
                    if "linestyle" in v: st[f"spine_{side}_linestyle"] = v["linestyle"]
                else:
                    st[f"spine_{side}"] = bool(v)
        elif name == "grid":   st["grid"] = (args[0] if args else True)
        elif name == "legend":
            st["legend"] = (args[0] if args else True)
            if "position" in kw:
                st["legend_position"] = kw["position"]
        elif name == "clip":   st["clip"] = bool(args[0]) if args else True
        elif name == "facecolor": st["facecolor"] = args[0] if args else None
        elif name == "theme":
            # `theme` is applied outside replay (by `active_theme(...)` in
            # `Chart.to_svg`) so the spec dicts are already on the right
            # values by the time we get here. No state to record.
            pass
    return st


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
    """Per-side breathing buffer for the data-region path. Returns
    `max(_MARGIN_FLOOR, M)` per side — the spec floor is the minimum
    breathing past content; a user passing `margin=` raises that buffer.
    `_compute_measured_margins` adds this to `_required_margin` (content
    size), so a labelled side gets `content + floor` and an empty side
    gets the floor alone."""
    return {
        "top":    max(_MARGIN_FLOOR["top"],    int(round(M["top"]))),
        "bottom": max(_MARGIN_FLOOR["bottom"], int(round(M["bottom"]))),
        "left":   max(_MARGIN_FLOOR["left"],   int(round(M["left"]))),
        "right":  max(_MARGIN_FLOOR["right"],  int(round(M["right"]))),
    }


def _prebin_hist(st):
    """Compute hist bins on `st["artists"]` so they participate in domain
    scanning. Multi-group overlays share bin edges. Idempotent (guarded by
    `_bin_groups` presence)."""
    for a in st["artists"]:
        if a["type"] != "hist" or "_bin_groups" in a:
            continue
        opts = a["opts"]
        bins_n = opts.get("bins", 10)
        density = opts.get("density", False)
        vals = a["vals"]
        if len(vals) <= 1:
            a["_bin_groups"] = [histogram(vals[0], bins_n, density=density)] \
                               if vals else [[]]
            continue
        all_vals = [v for g in vals for v in g
                    if v is not None and not (isinstance(v, float) and v != v)]
        if not all_vals:
            a["_bin_groups"] = [[] for _ in vals]
            continue
        lo, hi = min(all_vals), max(all_vals)
        if lo == hi: hi = lo + 1
        n = bins_n if isinstance(bins_n, int) else 10
        width = (hi - lo) / n
        edges = [lo + i * width for i in range(n + 1)]
        bin_groups = []
        for g in vals:
            counts = [0] * n
            cleaned = [v for v in g if v is not None
                       and not (isinstance(v, float) and v != v)]
            for v in cleaned:
                if v == hi:
                    counts[-1] += 1
                else:
                    i = int((v - lo) / width)
                    if 0 <= i < n:
                        counts[i] += 1
            if density:
                total = sum(counts) * width or 1
                counts = [c / total for c in counts]
            bin_groups.append([{"x0": edges[i], "x1": edges[i + 1],
                                "count": counts[i]} for i in range(n)])
        a["_bin_groups"] = bin_groups


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


def _leaf_axis_kind(st, axis):
    """Classify a leaf's natural axis kind on `axis`: 'categorical', 'numeric',
    'time', or 'empty' (no artists contributing). Explicit `*scale("category")`
    overrides artist-derived classification."""
    if st[f"{axis}scale"] == "category":
        return "categorical"
    if st[f"{axis}scale"] == "time":
        return "time"
    artists = st["artists"]
    if not artists:
        return "empty"
    has_str = has_num = False
    for a in artists:
        spec = get_artist(a["type"])
        if spec is None: continue
        fn = spec.xdomain if axis == "x" else spec.ydomain
        vals = fn(a)
        if vals is None: continue
        for v in vals:
            if v is None: continue
            if isinstance(v, str):
                has_str = True
            else:
                has_num = True
            if has_str and has_num:
                break
        if has_str and has_num:
            break
    if has_str: return "categorical"  # string wins (matches _is_categorical_axis)
    if has_num: return "numeric"
    return "empty"


def _check_share_kinds_compatible(states, axis):
    """Raise if leaves in a share class have incompatible axis kinds —
    e.g. one categorical (heatmap, bar) and another numeric (line on
    floats). Without this check, the mismatch crashes deep in
    `_scan_domain` (`'<' not supported between str and float`) or
    silently produces a category scale over mixed string/numeric values."""
    kinds = {_leaf_axis_kind(st, axis) for st in states}
    kinds.discard("empty")
    if len(kinds) <= 1:
        return
    raise TypeError(
        f"share_{axis}= mixes incompatible axis kinds {sorted(kinds)} "
        f"across the share class; all leaves must agree on categorical / "
        f"numeric / time. Cast numeric leaves with "
        f"{axis}scale('category', order=[...]) or rework the data so "
        f"every shared leaf uses the same kind."
    )


def _x_descriptor(st) -> _AxisDescriptor:
    """Compute this panel's natural x-axis descriptor from its own state.

    Categorical precedence:
      1. user-explicit `c.xscale("category", order=[...])` → that exact order
      2. an artist's `axis_order` hook (e.g. dendrogram's leaf order)
      3. an artist `frame_defaults` `xscale(order=[...])` (e.g. heatmap's
         first-seen clustered order) → x_order_default
      4. `collect_categories` → first-appearance of unique x values
    """
    _prebin_hist(st)
    artists = st["artists"]
    explicit_cat = st["xscale"] == "category"
    auto_cat = _is_categorical_axis(artists, "x")

    if explicit_cat or auto_cat:
        if st["x_order"] is not None:
            cats = list(st["x_order"])
        else:
            cats = (_artist_axis_order(artists, "x")
                    or st["x_order_default"]
                    or collect_categories(artists, "x"))
        padding = _D["category_padding"] if st["x_padding"] is None else st["x_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding,
                               splits=st["x_splits"], split_gap=st["x_split_gap"],
                               groups=st["x_groups"])

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
    `force_zero_y` on its spec) that the axis should anchor at zero.
    The spec value may be a bool or a callable `(artist_dict) -> bool`,
    so an artist like `bar` can flip its zero-axis based on orientation."""
    attr = "force_zero_x" if axis == "x" else "force_zero_y"
    for a in artists:
        spec = get_artist(a["type"])
        if spec is None: continue
        flag = getattr(spec, attr, False)
        if callable(flag):
            flag = flag(a)
        if flag:
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
            cats = (_artist_axis_order(artists, "y")
                    or st["y_order_default"]
                    or collect_categories(artists, "y"))
        padding = _D["category_padding"] if st["y_padding"] is None else st["y_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding,
                               splits=st["y_splits"], split_gap=st["y_split_gap"],
                               groups=st["y_groups"])

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


def _resolve_shared_padding(states: list[dict], key: str) -> float:
    """Category padding for a share-equivalence class.

    Anchor (`states[0]`) wins if it set padding explicitly. Otherwise pick
    the min explicit setting across the rest — a heatmap's `padding=0`
    (flush cells) propagates to siblings on the same shared scale even
    when the heatmap isn't the anchor. Falls back to the spec default.
    """
    anchor = states[0]
    if anchor[key] is not None:
        return anchor[key]
    others = [st[key] for st in states[1:] if st[key] is not None]
    if others:
        return min(others)
    return _D["category_padding"]


def _x_descriptor_multi(states: list[dict]) -> _AxisDescriptor:
    """Build an x-axis descriptor for a share-equivalence class.

    The first state in `states` is the anchor — its xscale, xlim, x_order,
    and x_padding settings win. Auto-scanned data range is the union of
    artists across all states. Single-state input is equivalent to
    `_x_descriptor(states[0])`."""
    if len(states) == 1:
        return _x_descriptor(states[0])
    _check_share_kinds_compatible(states, "x")
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
            cats = (_artist_axis_order(all_artists, "x")
                    or anchor["x_order_default"]
                    or collect_categories(all_artists, "x"))
        padding = _resolve_shared_padding(states, "x_padding")
        return _AxisDescriptor(kind="category", cats=cats, padding=padding,
                               splits=anchor["x_splits"], split_gap=anchor["x_split_gap"],
                               groups=anchor["x_groups"])
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
    _check_share_kinds_compatible(states, "y")
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
            cats = (_artist_axis_order(all_artists, "y")
                    or anchor["y_order_default"]
                    or collect_categories(all_artists, "y"))
        padding = _resolve_shared_padding(states, "y_padding")
        return _AxisDescriptor(kind="category", cats=cats, padding=padding,
                               splits=anchor["y_splits"], split_gap=anchor["y_split_gap"],
                               groups=anchor["y_groups"])
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


def _inline_legend_layout(st):
    """Geometry for the in-frame legend a leaf paints.

    Returns a dict with `disc` (list of `(artist, entry)` pairs from
    `spec.legend_entries`), `cont` (list of `(artist, descriptor)` pairs
    from `spec.legend_gradient`), block width/height (`lw`, `lh`), a
    `horizontal` flag (entries arranged left-to-right vs. stacked), and
    the resolved `position` (auto-flipped from "inside" → "right" when
    a continuous mapping is in play, since an inside colorbar inside the
    data area is incoherent). Returns `None` if there's nothing to draw.

    Continuous + horizontal-position combos raise — a horizontal gradient
    strip is its own render variant we haven't built; users on those
    positions should compose with `pt.legend(c)` instead.

    Called by `_required_margin` (to reserve outside-legend margin space)
    and by `_render_inner`'s legend block (to paint), so the two stay in
    sync — change geometry here, both paths follow."""
    if not st["legend"]:
        return None
    disc = []
    cont = []
    for a in st["artists"]:
        spec = get_artist(a["type"])
        if spec is None:
            continue
        if spec.legend_gradient is not None:
            desc = spec.legend_gradient(a)
            if desc is not None:
                cont.append((a, desc))
        if spec.legend_entries is not None:
            for entry in spec.legend_entries(a):
                disc.append((a, entry))
    if not disc and not cont:
        return None

    requested = st.get("legend_position", "right")
    if cont and requested in ("top", "bottom"):
        raise ValueError(
            f"chart.legend(position={requested!r}) with a continuous color "
            f"mapping (imshow / heatmap / hexbin) is not supported — only "
            f"'right' or 'left' work for the inline colorbar. For a "
            f"horizontal gradient strip, compose with `pt.legend(c)` "
            f"instead and place it on top or bottom of your layout."
        )
    # Auto-flip inside-corner tokens to "right" for gradient charts — an
    # overlay colorbar would float over the data area, which never reads right.
    if cont and requested in _INSIDE_POSITIONS:
        pos = "right"
    else:
        pos = requested
    horizontal = pos in ("top", "bottom")

    row_h = _LEGSPEC["row_height"]
    pad_x = _LEGSPEC["pad_x"]
    pad_y = _LEGSPEC["pad_y"]
    sw    = _LEGSPEC["swatch_width"]
    tick_size = _FONTSPEC["tick_size"]

    if horizontal:
        # Discrete-only horizontal row (gradients on top/bottom would
        # have raised above). Entries arranged left-to-right.
        entry_ws = [sw + 6 + measure_text(e["label"], tick_size) for _, e in disc]
        spacer = 2 * pad_x
        lw = 2 * pad_x + sum(entry_ws) + (len(disc) - 1) * spacer
        lh = row_h + 2 * pad_y
    elif cont and not disc:
        # Gradient-only block: no background rect, no padding around the
        # block — the strip carries its own border. Sits flush against
        # the data area's outer edge (modulo legend_gap).
        from .legend import _inline_gradient_block_size
        lw, lh = _inline_gradient_block_size([d for _, d in cont])
    else:
        # Vertical mixed (cont + disc) or discrete-only. Stack continuous
        # strips on top, discrete rows below, with section_gap between.
        # Background rect wraps everything → outer padding.
        from .legend import _inline_gradient_block_size, _partition_by_group
        disc_max_text = (max(measure_text(e["label"], tick_size) for _, e in disc)
                          if disc else 0.0)
        disc_w = sw + 6 + disc_max_text if disc else 0.0
        # Sub-group sizing: each named sub-group adds a small header row
        # plus the existing section_gap separates adjacent sub-groups.
        label_size = _FONTSPEC["label_size"]
        sub_header_h = label_size + 4
        sub_groups = _partition_by_group(disc, lambda ae: ae[1].get("group"))
        for name, _items in sub_groups:
            if name:
                disc_w = max(disc_w, measure_text(str(name), label_size))
        n_sub_headers = sum(1 for n, _ in sub_groups if n)
        n_sub_gaps = max(0, len(sub_groups) - 1)
        disc_h = (len(disc) * row_h
                  + n_sub_headers * sub_header_h
                  + n_sub_gaps * _LEGSPEC["section_gap"])
        cont_w, cont_h = _inline_gradient_block_size([d for _, d in cont])
        lw = max(disc_w, cont_w) + 2 * pad_x
        lh = cont_h + disc_h + 2 * pad_y
        if cont and disc:
            lh += _LEGSPEC["section_gap"]
    return {"disc": disc, "cont": cont, "lw": lw, "lh": lh,
            "horizontal": horizontal, "position": pos}


def _label_band_sizes(st, dw, dh, po: "_PanelOpts | None" = None) -> dict:
    """Per-side space (float px) for the axis-attached elements only —
    tick marks, tick labels, and the side-anchored label (xlabel /
    ylabel / title). Used directly by `_render_inner` to position those
    labels and the inline legend just outside the axis band.

    Cross-side overhang (a centered title wider than `dw` spilling onto
    left and right, a rotated ylabel taller than `dh` spilling onto top
    and bottom, the rightmost x-tick label's rotated AABB spilling past
    x=iw) is *not* included in the four side keys — those would displace
    axis-attached labels and outside legends from their natural slots.
    The rightmost-x-tick spillover is reported separately as
    `right_xtl_overhang` so `_required_margin` can max it in; the title
    / xlabel / ylabel overhangs are recomputed inline there. See
    `_required_margin` for the overhang application."""
    tick_size  = _FONTSPEC["tick_size"]
    label_size = _FONTSPEC["label_size"]
    title_size = _FONTSPEC["title_size"]

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
    # Only reserve clearance when marks are enabled, the direction reaches past
    # the spine, AND there's at least one tick position to actually draw.
    out_x = _FRAME["tick_length"] if (x_marks and x_ticks and x_dir != "in") else 0
    out_y = _FRAME["tick_length"] if (y_marks and y_ticks and y_dir != "in") else 0

    # Tick labels render via `text_path`, which short-circuits on empty
    # strings — so a side with all-blank labels visually contributes nothing.
    # On a joined share-pair side, `suppress_*_labels` also drops them.
    # `xticks(labels=False)` also fully suppresses them via `x_show_labels`.
    suppress_xt = (po is not None and po.suppress_bottom_labels) or not st["x_show_labels"]
    suppress_yt = (po is not None and po.suppress_left_labels)   or not st["y_show_labels"]
    has_xtl = (not suppress_xt) and any(str(l) for l in x_labels)
    if has_xtl:
        max_xtl_w = max((measure_text(str(l), x_size) for l in x_labels), default=0.0)
        first_xtl_w = measure_text(str(x_labels[0]), x_size)
        last_xtl_w = measure_text(str(x_labels[-1]), x_size)
        _, xtl_bbox_h = _rotated_label_bbox(max_xtl_w, x_size, x_rot)
        first_bbox_w, _ = _rotated_label_bbox(first_xtl_w, x_size, x_rot)
        last_bbox_w, _ = _rotated_label_bbox(last_xtl_w, x_size, x_rot)
    else:
        xtl_bbox_h = 0.0
        first_bbox_w = 0.0
        last_bbox_w = 0.0

    has_ytl = (not suppress_yt) and any(str(l) for l in y_labels)
    if has_ytl:
        max_ytl_w = max((measure_text(str(l), y_size) for l in y_labels), default=0.0)
        ytl_bbox_w, _ = _rotated_label_bbox(max_ytl_w, y_size, y_rot)
    else:
        ytl_bbox_w = 0.0

    # Joined-side hide flags — drop reservations the renderer skips.
    # `hide_*` suppresses title / xlabel / ylabel on that side; the
    # rightmost x-tick label overhang is allowed to bleed into the
    # collapsed joined neighbor on the right.
    hide_t = po is not None and po.hide_top
    hide_b = po is not None and po.hide_bottom
    hide_l = po is not None and po.hide_left
    hide_r = po is not None and po.hide_right

    # Per-side tick-mark reservation: on a hidden joined side the renderer
    # also drops the mark (along with labels/title/etc.), so the side
    # contributes no `out_x`/`out_y`.
    top_marks    = out_x if (st["x_top"]   and not hide_t) else 0
    bottom_marks = out_x if not hide_b else 0
    left_marks   = out_y if not hide_l else 0
    right_marks  = out_y if (st["y_right"] and not hide_r) else 0

    # Top: title content + outward top tick (if `xticks(top=True)`).
    # Title baseline sits at y = -pad.title (see _render_inner); the glyph
    # ascender extends ~title_size upward, so its top is at -(pad.title + title_size).
    # The caller adds `_MARGIN_FLOOR.top` past this for breathing.
    title_top = _PADSPEC["title"] + title_size if (st["title"] and not hide_t) else 0
    top = max(title_top, top_marks)

    # Bottom: each term only contributes when its element actually renders.
    # tick marks → bottom_marks; tick labels → tick_pad + xtl_bbox_h (only
    # when labels exist); xlabel → 2 px visual gap, full glyph
    # (≈ label_size), pad.xlabel.
    bottom = bottom_marks
    if has_xtl:
        bottom += _FRAME["tick_pad"] + xtl_bbox_h
    if st["xlabel"] and not hide_b:
        bottom += 2 + label_size + _PADSPEC["xlabel"]

    # Left: same shape mirrored on the y-axis.
    left = left_marks
    if has_ytl:
        left += _FRAME["tick_pad"] + ytl_bbox_w
    if st["ylabel"] and not hide_l:
        left += 2 + label_size + _PADSPEC["ylabel"]

    # Right: axis-only — outward tick stubs from `xticks(top=...)` /
    # `yticks(right=...)`. The leftmost / rightmost x-tick label's
    # overhang past x=0 / x=iw is a cross-axis spillover that lives in
    # `_required_margin`. The share of the rotated AABB that lands past
    # the spine depends on the tick-label anchor (see `_tick_label`):
    #   rot == 0  → anchor="middle"  → bbox extends w/2 each side
    #   rot >  0  → anchor="end"     → bbox extends fully LEFT  (0 right)
    #   rot <  0  → anchor="start"   → bbox extends fully RIGHT (0 left)
    # Tick-inset distance: the first/last tick sits ~dw/(2N) px inside
    # the data area (true for category scales, approx for numeric), so
    # the actual past-spine overhang is `bbox * share - tick_inset`.
    right = right_marks
    if x_rot == 0:
        left_share, right_share = 0.5, 0.5
    elif x_rot > 0:
        left_share, right_share = 1.0, 0.0
    else:
        left_share, right_share = 0.0, 1.0
    tick_inset = dw / (2 * len(x_ticks)) if x_ticks else 0.0
    left_xtl_overhang  = (0.0 if hide_l
                          else max(0.0, first_bbox_w * left_share - tick_inset))
    right_xtl_overhang = (0.0 if hide_r
                          else max(0.0, last_bbox_w * right_share - tick_inset))

    return {"top": top, "right": right, "bottom": bottom, "left": left,
            "left_xtl_overhang": left_xtl_overhang,
            "right_xtl_overhang": right_xtl_overhang}


# ---------------------------------------------------------------------------
# Margin pipeline — how a side's final margin gets built.
# ---------------------------------------------------------------------------
# The number `_render` receives as `M[side]` (and the panel transform uses)
# is composed in four pieces, each from a different function:
#
#   M[side] = floor + axis_band + text_overhang + outside_legend_reservation
#                                  └─ "inflation": everything beyond the band ─┘
#
# Pieces:
#   1. `_enforce_floors(leaf._margin)`         — per-side floor (whitespace),
#                                                in `_layout_engine.py`.
#   2. `_label_band_sizes(...)`                 — pure axis band: tick marks,
#                                                tick labels, ylabel / xlabel
#                                                / title attached to that side
#                                                (float).
#   3. + text overhang (centered title/xlabel  — applied inside `_required_margin`.
#       wider than `dw`, rotated ylabel taller
#       than `dh`)
#   4. + outside legend reservation             — also in `_required_margin`.
#
# `_required_margin` returns int (rounded) of (band + overhang + legend).
# `_compute_measured_margins` adds the floor: `M_eff = floor + M_req`.
#
# For *positioning* axis-attached labels (xlabel, ylabel) and the inline
# legend block, you usually want the axis-band edge, NOT the inflated M
# edge — a wide title or outside legend should not displace the ylabel
# from its slot just outside the y-ticks. The recipe is:
#
#     inflation[side] = max(0, M_req[side] - round(label_bands[side]))
#     # position at  M[side] - inflation[side]  ↔  floor + axis_band
#
# `_render_inner` does exactly this for xlabel / ylabel positioning.
# ---------------------------------------------------------------------------


def _required_margin(st, dw, dh, po: "_PanelOpts | None" = None) -> dict:
    """Margin a body-first leaf actually needs to fit its title, axis
    labels, tick labels, and any outside-positioned in-frame legend.

    Returns a plain dict with the same keys as `_margin` — the caller
    adds this to the per-side floor. Body-first specifically: data dims
    are fixed, so tick density and labels are deterministic and the
    computation is a single pass (no chicken-and-egg with margin).

    `po` (optional) lets the formula drop reservations for content the
    renderer is going to suppress (joined share-pair sides): tick labels
    via `suppress_*_labels`, xlabel/ylabel/title via `hide_*`. Solo and
    non-joined renders can pass `None` — no suppression applied.

    The geometry mirrors `_render_inner`'s placement formulas — keep them
    in sync if either changes."""
    bands = _label_band_sizes(st, dw, dh, po)
    top, right, bottom, left = bands["top"], bands["right"], bands["bottom"], bands["left"]

    # Cross-side text overhang: a title / xlabel longer than `dw` is
    # centered on `iw/2`, so it sticks out past the data area on left
    # and right by `(text_w - dw) / 2`. A ylabel (rotated -90, centered
    # on `ih/2`) is the same story but vertical: text longer than `dh`
    # spills past top and bottom equally. Margins grow by the overhang
    # so the rendered text fits inside the canvas. Skip when the label
    # / title is hidden (joined side) since the renderer won't draw it.
    # Applied here (not in `_label_band_sizes`) because positioning code
    # in `_render_inner` needs the *axis band* without overhang — a wide
    # title shouldn't displace the ylabel from its natural slot.
    label_size = _FONTSPEC["label_size"]
    title_size = _FONTSPEC["title_size"]
    hide_t = po is not None and po.hide_top
    hide_b = po is not None and po.hide_bottom
    hide_l = po is not None and po.hide_left
    if st["title"] and not hide_t:
        title_overhang = max(0.0, (measure_text(st["title"], title_size) - dw) / 2.0)
        left  = max(left,  title_overhang)
        right = max(right, title_overhang)
    if st["xlabel"] and not hide_b:
        xlabel_overhang = max(0.0, (measure_text(st["xlabel"], label_size) - dw) / 2.0)
        left  = max(left,  xlabel_overhang)
        right = max(right, xlabel_overhang)
    if st["ylabel"] and not hide_l:
        ylabel_overhang = max(0.0, (measure_text(st["ylabel"], label_size) - dh) / 2.0)
        top    = max(top,    ylabel_overhang)
        bottom = max(bottom, ylabel_overhang)
    # Rightmost x-tick label's rotated AABB extends past x=iw by half its
    # width — a cross-axis spillover from the bottom axis. Measured in
    # `_label_band_sizes` and reported separately so an inline right
    # legend (which positions itself at `iw + bands["right"] + gap`)
    # hugs the data area instead of being shoved out by a fat 45°-
    # rotated tick label.
    left  = max(left,  bands["left_xtl_overhang"])
    right = max(right, bands["right_xtl_overhang"])

    # Outside-legend reservation is *additive* with the label band so the
    # legend block sits beyond the title/labels rather than overlapping
    # them. "inside" paints over the data area and reserves nothing
    # extra. The effective position comes from `_inline_legend_layout`,
    # which auto-flips "inside" → "right" for charts with a continuous
    # mapping (an inside colorbar makes no sense).
    leg = _inline_legend_layout(st)
    if leg is not None and leg["position"] != "inside":
        lw, lh = leg["lw"], leg["lh"]
        pos = leg["position"]
        gap = _LAYOUTSPEC["legend_gap"]
        if pos == "right":
            right = right + gap + lw
        elif pos == "left":
            left = left + gap + lw
        elif pos == "top":
            top = top + gap + lh
        elif pos == "bottom":
            bottom = bottom + gap + lh

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
    resolved by the caller via `layout._build_panel_opts` →
    `_compute_measured_margins`. Single-panel and multi-panel paths
    share that pre-pass; this function just paints one panel into its
    own outer `<svg>`. Splitting margin resolution out of `_render` is
    what lets the data-path skip canvas-based scaling."""
    iw = W - M["left"] - M["right"]
    ih = H - M["top"] - M["bottom"]
    transform = f'translate({M["left"]},{M["top"]})'
    # Track the panel translate on the region sink so chrome bboxes land
    # in outer-SVG coords. No-op when no sink is active (normal render).
    with _regions.translate(M["left"], M["top"]):
        inner = _render_inner(st, iw, ih, M)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{_FONTSPEC["family"]}" font-size="11" '
        f'style="background:{SPEC["figure"]["background"]}"'
        f'{_figure_root_attrs("figure")}>'
        + _panel_open(st, None, transform, M, iw, ih, (0, 0, W, H))
        + inner
        + '</g></svg>'
    )


def _emit_inline_legend_body(lw, lh, pos, cont, disc, horizontal,
                              pad_x, pad_y, row_h, sw, tick_size,
                              text_color, ctx_for) -> str:
    """Render the inline legend body — the part *inside* the
    `<g transform="translate(lx, ly)">` wrapper. Lives in its own
    function so the translate ctxmgr in `_render_inner` stays a
    2-liner instead of forcing 70 lines of indentation. No behavior
    change vs the previous inline form."""
    from .legend import _render_continuous_entry, _render_discrete_entry
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
    if horizontal:
        # Discrete-only horizontal row (continuous + horizontal would
        # have raised in `_inline_legend_layout`). Entries left-to-right,
        # vertically centered. Spacer matches `_inline_legend_layout`.
        spacer = 2 * pad_x
        cx = pad_x
        ry = pad_y + row_h / 2
        for a, entry in disc:
            parts.append(_render_discrete_entry(entry, a, ctx_for, cx, ry))
            cx += sw + 6 + measure_text(entry["label"], tick_size) + spacer
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
        entry_h = (tick_size + 4 if desc.get("label") else 0) \
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
    from .legend import _partition_by_group
    sub_groups = _partition_by_group(disc, lambda ae: ae[1].get("group"))
    label_size = _FONTSPEC["label_size"]
    sub_header_h = label_size + 4
    for si, (sub_name, sub_items) in enumerate(sub_groups):
        if sub_name:
            parts.append(text_path(str(sub_name), pad_x,
                                   cur_y + label_size,
                                   label_size, anchor="start",
                                   color=text_color,
                                   tag="legend-header"))
            cur_y += sub_header_h
        for a, entry in sub_items:
            ry = cur_y + row_h / 2
            parts.append(_render_discrete_entry(entry, a, ctx_for, pad_x, ry))
            cur_y += row_h
        if si < len(sub_groups) - 1:
            cur_y += _LEGSPEC["section_gap"]
    return ''.join(parts)


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
    # `xticks(labels=False)` joins forces with the share-pair label
    # suppression — either one drops tick labels on the corresponding side.
    suppress_yt = panel_opts.suppress_left_labels   or not st["y_show_labels"]
    suppress_xt = panel_opts.suppress_bottom_labels or not st["x_show_labels"]

    # In-frame legend geometry is computed up front because a top-position
    # legend sits between the title and the data area — the title's y
    # offset depends on it. For other positions / inside / no legend, the
    # title stays at `_PADSPEC["title"]`.
    leg = _inline_legend_layout(st)
    legend_pos = leg["position"] if leg is not None else "inside"
    legend_gap = _LAYOUTSPEC["legend_gap"]
    # `inner_gap_top` is the data-side gap below the top-position legend
    # — at least `legend_gap`, but expands to clear outward top tick marks
    # when `xticks(top=True)`. None when no top legend is in play.
    inner_gap_top = None
    if leg is not None and legend_pos == "top":
        out_x_for_legend = (_FRAME["tick_length"]
                            if (st["x_marks"] and x_ticks and st["x_direction"] != "in")
                            else 0)
        top_marks_size = out_x_for_legend if (st["x_top"] and not hide_t) else 0
        inner_gap_top = max(top_marks_size, legend_gap)

    # ---- emit body fragment ----
    parts = []

    if st["facecolor"] is not None:
        parts.append(rect(0, 0, iw, ih, fill=resolve_color(st["facecolor"])))

    # grid
    if st["grid"]:
        gw = _GRIDSPEC["width"]; gd = _GRIDSPEC["dasharray"]
        if not x_is_cat:
            for t in x_ticks:
                x = x_scale(t)
                parts.append(segment(x, 0, x, ih,
                                     color=_GRIDSPEC["color"], width=gw, dash=gd))
        for t in y_ticks:
            y = y_scale(t)
            parts.append(segment(0, y, iw, y,
                                 color=_GRIDSPEC["color"], width=gw, dash=gd))

    # color assignment — only color-cycle artists consume the cycle
    color_idx = 0
    for a in st["artists"]:
        spec = get_artist(a["type"])
        # Honor either `color=` (stroke-defaulted artists) or `fill=`
        # literal (fill-defaulted artists, e.g. bar) as the artist's
        # user-set primary color — both should skip the cycle and supply
        # `_color` for the legend.
        user_color = resolve_color(a["opts"].get("color")
                                    or a["opts"].get("_color_literal")
                                    or a["opts"].get("_fill_literal"))
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
        # via `c.clip(False)` to allow artists to paint past the data area.
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
    # reads as a render bug). On a joined share-pair side (hide_*), tick
    # marks AND tick labels are dropped — the panels read as merged, with
    # only the two parallel spines remaining (separated by the per-panel
    # floor on each joined side).
    def _side_stroke(side):
        c = st[f"spine_{side}_color"]
        w = st[f"spine_{side}_width"]
        col = resolve_color(c) if c is not None else _FRAME["color"]
        return col, (w if w is not None else _FRAME["width"])

    def _side_dash(side):
        return st[f"spine_{side}_linestyle"]

    # Panel region — recorded in the sink so layout-debug consumers
    # (`chart.regions()`, layout_diagram detail mode) can ask "did
    # anything overflow this panel?". Panel-local coords: (0, 0)
    # is the inner-margin corner; (iw, ih) is the data-area extent.
    _regions.record("rect", (0, 0, iw, ih), name="panel")

    for side, (x1, y1, x2, y2) in (
        ("top",    (0, 0, iw, 0)),
        ("bottom", (0, ih, iw, ih)),
        ("left",   (0, 0, 0, ih)),
        ("right",  (iw, 0, iw, ih)),
    ):
        if not st[f"spine_{side}"]:
            continue
        col, w = _side_stroke(side)
        parts.append(segment(x1, y1, x2, y2, color=col, width=w,
                             dash=_side_dash(side), tag="spine"))

    tick_size = _FONTSPEC["tick_size"]
    label_size = _FONTSPEC["label_size"]
    title_size = _FONTSPEC["title_size"]

    x_size = st["x_fontsize"] if st["x_fontsize"] is not None else tick_size
    y_size = st["y_fontsize"] if st["y_fontsize"] is not None else tick_size
    x_rot = st["x_rotation"] or 0
    y_rot = st["y_rotation"] or 0
    x_style = st.get("x_fontstyle") or "normal"
    y_style = st.get("y_fontstyle") or "normal"
    x_decor = st.get("x_decoration") or "none"
    y_decor = st.get("y_decoration") or "none"
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
            # Hidden sides (joined share-pair) drop tick marks too — marks
            # bleeding into the inter-panel gap read as visual clutter
            # when the two panels are meant to merge.
            if st["spine_bottom"] and not hide_b:
                y1, y2 = x_bot_endpoints
                col, sw = _side_stroke("bottom")
                parts.append(segment(x, y1, x, y2, color=col, width=sw))
            if st["spine_top"] and st["x_top"] and not hide_t:
                y1, y2 = x_top_endpoints
                col, sw = _side_stroke("top")
                parts.append(segment(x, y1, x, y2, color=col, width=sw))
        # Drop only labels redundant with a sharing sibling. A small label
        # overflow into a joined neighbor's collapsed margin is acceptable.
        if not suppress_xt:
            # baseline = tick_end + tick_pad + cap_height, so the label's cap
            # top sits flush with `tick_pad` past the tick mark.
            parts.append(_tick_label(str(lbl), x,
                                     ih + _FRAME["tick_length"] + _FRAME["tick_pad"] + cap_height(x_size),
                                     x_size, x_rot, axis="x",
                                     fontstyle=x_style, decoration=x_decor,
                                     tag="tick-x"))

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
            if st["spine_bottom"] and not hide_b:
                col, sw = _side_stroke("bottom")
                if x_dir == "in":      y1, y2 = ih, ih - minor_len
                elif x_dir == "out":   y1, y2 = ih, ih + minor_len
                else:                  y1, y2 = ih + minor_len, ih - minor_len
                parts.append(segment(x, y1, x, y2, color=col, width=sw))
            if st["spine_top"] and st["x_top"] and not hide_t:
                col, sw = _side_stroke("top")
                if x_dir == "in":      y1, y2 = 0, minor_len
                elif x_dir == "out":   y1, y2 = 0, -minor_len
                else:                  y1, y2 = -minor_len, minor_len
                parts.append(segment(x, y1, x, y2, color=col, width=sw))

    # y ticks + labels
    for t, lbl in zip(y_ticks, y_labels):
        y = y_scale(t)
        if y_marks:
            if st["spine_left"] and not hide_l:
                x1, x2 = y_left_endpoints
                col, sw = _side_stroke("left")
                parts.append(segment(x1, y, x2, y, color=col, width=sw))
            if st["spine_right"] and st["y_right"] and not hide_r:
                x1, x2 = y_right_endpoints
                col, sw = _side_stroke("right")
                parts.append(segment(x1, y, x2, y, color=col, width=sw))
        if not suppress_yt:
            # `y + cap_height/2` places the baseline so the cap is vertically
            # centered on the tick line (cap top at y - cap/2, cap bottom at y + cap/2).
            parts.append(_tick_label(str(lbl), y_label_x, y + cap_height(y_size) / 2,
                                     y_size, y_rot, axis="y",
                                     fontstyle=y_style, decoration=y_decor,
                                     tag="tick-y"))

    y_minor = _resolve_minor_ticks(st["y_minor"], y_scale, y_ticks)
    if y_minor and y_marks:
        minor_len = _FRAME["tick_length"] * _FRAME["minor_tick_ratio"]
        for t in y_minor:
            y = y_scale(t)
            if not math.isfinite(y):
                continue
            if st["spine_left"] and not hide_l:
                col, sw = _side_stroke("left")
                if y_dir == "in":      x1, x2 = 0, minor_len
                elif y_dir == "out":   x1, x2 = 0, -minor_len
                else:                  x1, x2 = -minor_len, minor_len
                parts.append(segment(x1, y, x2, y, color=col, width=sw))
            if st["spine_right"] and st["y_right"] and not hide_r:
                col, sw = _side_stroke("right")
                if y_dir == "in":      x1, x2 = iw, iw - minor_len
                elif y_dir == "out":   x1, x2 = iw, iw + minor_len
                else:                  x1, x2 = iw + minor_len, iw - minor_len
                parts.append(segment(x1, y, x2, y, color=col, width=sw))

    # xlabel / ylabel / title live in margin space; drop when that margin
    # is collapsed against a joined neighbor. Positioned against the
    # axis band (`label_bands`), not the inflated margin (`M`) — so a
    # wide title, tall ylabel, or outside-positioned legend doesn't
    # shove the label away from its natural slot just outside the tick
    # labels. The inline-legend block (below) also reads `label_bands`,
    # so compute once.
    label_bands = _label_band_sizes(st, iw, ih, panel_opts)
    # See "Margin pipeline" comment block above `_required_margin`.
    # `inflation` = text overhang + outside-legend reservation; subtracting
    # it from `M[side]` snaps ylabel / xlabel to the axis-band outer edge
    # rather than floating in the inflated margin. Collapses to the old
    # canvas-edge anchored formula when inflation is 0 (no overhang, no
    # outside legend), keeping baselines byte-identical for that case.
    m_req = _required_margin(st, iw, ih, panel_opts)
    left_inflation   = max(0, m_req["left"]   - int(round(label_bands["left"])))
    bottom_inflation = max(0, m_req["bottom"] - int(round(label_bands["bottom"])))
    text_color = _FONTSPEC["color"]
    if st["xlabel"] and not hide_b:
        # Baseline sits at canvas-bottom edge (minus inflation) minus
        # pad.xlabel minus the glyph descender — visible glyph bottom
        # is exactly `pad.xlabel` above the axis band's outer edge.
        parts.append(text_path(st["xlabel"], iw / 2,
                                ih + M["bottom"] - bottom_inflation - _PADSPEC["xlabel"] - descender(label_size),
                                label_size, anchor="middle", color=text_color,
                                tag="xlabel"))
    if st["ylabel"] and not hide_l:
        # Center sits at -(M["left"] - inflation - pad.ylabel - label_size/2)
        # so the rotated text's left visible edge lands exactly `pad.ylabel`
        # inside the axis band's outer edge.  `text_path(rotate=90)` does
        # both the rotation transform and the post-rotation bbox so the
        # sink sees the standing-up bbox without a manual override.
        ylabel_cx = -(M["left"] - left_inflation - _PADSPEC["ylabel"] - label_size / 2)
        parts.append(text_path(st["ylabel"], ylabel_cx, ih / 2,
                                label_size, anchor="middle",
                                color=text_color, rotate=90, tag="ylabel"))
    if st["title"] and not hide_t:
        # Top-position legend sits between title and data, pushing the
        # title's baseline up by (legend block + outer gap to legend).
        if inner_gap_top is not None:
            title_y = -(inner_gap_top + leg["lh"] + legend_gap)
        else:
            title_y = -_PADSPEC["title"]
        parts.append(text_path(st["title"], iw / 2, title_y, title_size,
                                anchor="middle", color=text_color,
                                tag="title"))

    # legend — gather entries from every artist's legend_entries(a) and
    # gradient descriptors from legend_gradient(a). Multi-entry artists
    # (sankey, mosaic, ...) contribute one row per category; continuous
    # artists (imshow, hexbin, ...) contribute a vertical gradient strip
    # with ticks (this replaces the previous `c | pt.legend(c)` two-line
    # workaround for an inline colorbar).
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
            # band. Hidden sides naturally collapse via `_label_band_sizes`
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
        transform = f'translate({lx:.2f},{ly:.2f})'
        parts.append(f'<g transform="{transform}">')
        # The translate puts the body's panel-local coords onto the
        # sink so chrome bboxes tagged inside `_render_discrete_entry`
        # / `_render_continuous_entry` (and the sub-header text_path
        # in the body) land at outer-SVG positions.
        with _regions.translate(lx, ly):
            parts.append(_emit_inline_legend_body(
                lw, lh, pos, cont, disc, horizontal,
                pad_x, pad_y, row_h, sw, tick_size, text_color, _ctx_for))
        parts.append('</g>')

    # Inset axes — render each as its own SVG fragment positioned by
    # axes-fraction within this leaf's data area. Drawn last so they
    # sit on top of the data layer (and on top of the legend). Wrapped
    # in a data-area clip so the inset's canvas can't paint over the
    # parent's title/labels if its own margins overhang.
    insets = st.get("insets") or []
    if insets:
        parts.append(f'<svg x="0" y="0" width="{iw}" height="{ih}" overflow="hidden">')
    for inset_rect, inset_chart in insets:
        x_frac, y_frac, w_frac, h_frac = inset_rect
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
        # labels in the inset's margins stay transparent.
        bg_x = inset_M["left"]
        bg_y = inset_M["top"]
        bg_w = inset_chart._data_width
        bg_h = inset_chart._data_height
        parts.append(f'<g transform="translate({tx:.2f},{ty:.2f})" '
                      f'data-plotlet-kind="inset">'
                      + rect(bg_x, bg_y, bg_w, bg_h,
                             fill=SPEC["figure"]["background"])
                      + f'{inset_svg}</g>')
    if insets:
        parts.append('</svg>')

    return "".join(parts)
