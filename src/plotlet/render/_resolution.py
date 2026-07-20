"""Resolution — pure functions over Chart state.

The deferred-render pipeline:
  1. A `Chart` (defined in `chart.py`) records user calls into `_calls`.
  2. `Chart.to_svg()` lowers to the figure IR and renders it via
     `render.render_svg`.
  3. Resolution — this module plus the layout pre-pass in
     `_layout_engine.py` — replays states and decides everything:
     domains, scales, tick content, margins, colors, chrome flags.
  4. Emit (`emit.py`) transcribes those decisions into SVG: per
     placement it opens a panel `<g>` via `_panel_open` and fills it
     via `_render_inner` (grid → artists → chrome → labels → legend).

A lone chart runs the exact same pipeline as a 1x1 grid — there is no
separate standalone path.

Every function here takes its state explicitly — there's no class to
hold it. Adding a new plot type means calling `add_artist(...)` from
outside; no monkey-patching, no editing this file.
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from types import SimpleNamespace

from .._spec import (
    _MARGIN_FLOOR, _FRAME, _GRIDSPEC, _FONTSPEC, _LEGSPEC,
    _LAYOUTSPEC, _PADSPEC, _D,
)
from ..draw import resolve_color, TAB10
from ..scales import (_nice_domain, _fmt_tick, _to_epoch,
                      _coerce_time_lim, _AxisDescriptor)
from ..sectors import SectoredValue
from ..draw import measure_text, text_block_height
from . import _chrome_bands
from ._chrome_visibility import resolve_axis_chrome
from ..utils import (hist_bin_edges, hist_bin_counts, hist_transform,
                     collect_categories, group_color)
from ..registry import get_artist

# Frame metadata methods (title, xlabel, etc.) — these aren't artists,
# they're just state setters. Kept as a fixed set. `theme` joins the set
# so a chart's theme can be recorded and replayed like any other frame
# attribute; the layout engine reads it per leaf and wraps that leaf's
# emit in an `active_theme(...)` context.
# Inline legend position tokens that overlay the data area (vs reserve
# margin space outside it). Used to drive both placement and the "draw a
# readability background?" decision — outside positions skip the rect
# (ggplot/vega-lite default); inside positions keep a translucent fill.
_INSIDE_POSITIONS = frozenset({
    "top-right", "top-left", "bottom-right", "bottom-left", "center",
})

# ---------------------------------------------------------------------------
# Scale-share types — used by the layout pre-pass.
# ---------------------------------------------------------------------------
# `_AxisDescriptor` is the pre-pixel axis type; it lives in `scales.py`
# next to the scale classes it builds. Re-exported above for callers that
# still import it from `._resolution`.


@dataclass
class _PanelOpts:
    """Layout-supplied render options for one leaf panel.

    `hide_*` collapses the matching margin (axis labels and title in that
    margin get dropped — they don't fit; spines and tick lines remain).
    `suppress_*_labels` drops tick labels on a side whose axis is shared
    with a neighbor that already labels it; set only on the panel that
    actually shares, never propagated by grid alignment.
    `M_eff` is the layout-pre-pass-resolved effective margin — it has
    already incorporated measure-driven growth and per-column/row
    coordination. Populated by `_compute_measured_margins` for every
    data leaf; only data leaves get a `_PanelOpts` entry.
    """
    x_axis: _AxisDescriptor | None = None
    y_axis: _AxisDescriptor | None = None
    hide_left:   bool = False
    hide_right:  bool = False
    hide_top:    bool = False
    hide_bottom: bool = False
    suppress_left_labels:   bool = False
    suppress_right_labels:  bool = False
    suppress_top_labels:    bool = False
    suppress_bottom_labels: bool = False
    M_eff:       dict | None = None


def _record_scale(state, axis, args, kw, *, from_default=False):
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
    state[f"{axis}scale"] = args[0]
    if "order" in kw:
        target = f"{axis}_order_default" if from_default else f"{axis}_order"
        state[target] = list(kw["order"])
    if "padding" in kw:   state[f"{axis}_padding"]   = kw["padding"]
    if "linthresh" in kw: state[f"{axis}_linthresh"] = float(kw["linthresh"])
    if "exponent" in kw:  state[f"{axis}_exponent"]  = float(kw["exponent"])
    if "reverse" in kw:   state[f"{axis}_reverse"]   = bool(kw["reverse"])
    if "splits" in kw:    state[f"{axis}_splits"]    = list(kw["splits"]) if kw["splits"] else None
    if "split_gap" in kw: state[f"{axis}_split_gap"] = float(kw["split_gap"])
    if "groups" in kw:    state[f"{axis}_groups"]    = dict(kw["groups"]) if kw["groups"] else None


# xticks()/yticks() kwargs that decide tick CONTENT — which ticks exist
# and what their labels say — as opposed to styling them (rotation=,
# fontsize=, marks=, ...). `labels` is content too unless passed as the
# bool form (`labels=False`), which only toggles label visibility.
# The circular layout resolve (`_layout_circular`) checks this set to tell
# content-deciding calls from style-only ones; keep it in sync with the
# kwarg handling in `_record_ticks` below.
TICK_CONTENT_KW = frozenset({"ticks", "step", "count", "format", "minor"})


def _record_ticks(state, axis, args, kw):
    """Decode the xticks()/yticks() call into state.

    Signature: xticks(ticks=None, labels=None, *, rotation=0, fontsize=None,
    fontstyle=None, fontweight=None, ...).
    Accepts the first arg positionally; pass `[]` to hide. Omitted
    kwargs leave the corresponding state alone, so `c.xticks(rotation=45)`
    rotates without disturbing auto positions.
    """
    if args:
        state[f"{axis}_ticks"] = list(args[0]) if args[0] is not None else None
        if len(args) > 1 and args[1] is not None:
            state[f"{axis}_labels"] = list(args[1])
    if "ticks" in kw:
        v = kw["ticks"]
        state[f"{axis}_ticks"] = list(v) if v is not None else None
    if "labels" in kw:
        v = kw["labels"]
        if v is False:
            # Symmetric counterpart to `marks=False` — keep auto tick
            # positions + tick marks, suppress the labels. Useful when
            # tick marks are meant as visual cues but their numeric
            # labels would crowd a different label (e.g. a sector name
            # as xlabel under per-sector tick marks).
            state[f"{axis}_show_labels"] = False
        else:
            state[f"{axis}_labels"] = list(v) if v is not None else None
    if "rotation" in kw:  state[f"{axis}_rotation"]  = kw["rotation"]
    if "fontsize" in kw:  state[f"{axis}_fontsize"]  = kw["fontsize"]
    if "fontstyle" in kw: state[f"{axis}_fontstyle"] = kw["fontstyle"]
    if "fontweight" in kw: state[f"{axis}_fontweight"] = kw["fontweight"]
    if "decoration" in kw: state[f"{axis}_decoration"] = kw["decoration"]
    if "direction" in kw: state[f"{axis}_direction"] = kw["direction"]
    if "marks" in kw:     state[f"{axis}_marks"]     = bool(kw["marks"])
    if "format" in kw:    state[f"{axis}_format"]    = kw["format"]
    if "minor" in kw:     state[f"{axis}_minor"]     = kw["minor"]
    if "step" in kw:      state[f"{axis}_step"]      = float(kw["step"])
    if "count" in kw:     state[f"{axis}_count"]     = int(kw["count"])
    # Primary axis placement. Matches plotly's `side`, ggplot2's `position`,
    # d3's axisTop/axisRight. Moves the spine, ticks, labels and the
    # xlabel/ylabel as a single block to the named edge.
    if "side" in kw:
        valid = {"x": ("bottom", "top"), "y": ("left", "right")}[axis]
        if kw["side"] not in valid:
            raise ValueError(f"{axis}ticks(side=...) must be one of {valid}, "
                             f"got {kw['side']!r}")
        state[f"{axis}_side"] = kw["side"]


def _sector_remap_data(call_kw, state):
    """Offset an artist call's x/y values into global sector coordinates
    when continuous sectors are active on that axis.

    No-op for axes without sectors and for categorical sectors (which use
    the category-scale path).

    Passthrough (deliberate): when the data table lacks the sector tag
    column. Lets cross-sector annotations (reflines, axhline / axvline,
    `x_col=` without a sector column) coexist with sectored artists.

    Raise (typo guard): when the sector column IS present but a row's
    value isn't a known sector name. Silent remap of unknown sectors
    would corrupt the global offset and produce a wrong but plausible
    plot — strictly worse than a clear ValueError.

    Preserves pandas dtype via ``.assign`` when available.
    """
    data = call_kw.get("data")
    if data is None:
        return call_kw
    new_cols = {}
    consumed = set()      # per-endpoint sector kwargs eaten by remap
    for axis in ("x", "y"):
        sec     = state[f"{axis}_sectors"]
        sec_col = state[f"{axis}_sector_column"]
        if sec is None or sec.kind != "continuous":
            continue
        # Resolve sector names → indices once; SectoredValue carries the
        # int so the scale never needs a name table.
        name_to_idx = {n: i for i, n in enumerate(sec.names)}
        # Value kwargs the framework will remap:
        #   `x` / `y`                 — single position (scatter, line, ...)
        #   `x1` / `x2` / `y1` / `y2` — two endpoints (chord_links, segment)
        #   `x1_start` / `x1_end` /
        #     `x2_start` / `x2_end`   — interval endpoints (chord_ribbon)
        # The corresponding sector tag is whatever the base prefix carries:
        #   x1 / x1_start / x1_end → x1_sector
        # so a 4-endpoint artist still only declares two `x*_sector` cols.
        for val_kw in (axis, f"{axis}1", f"{axis}2",
                       f"{axis}1_start", f"{axis}1_end",
                       f"{axis}2_start", f"{axis}2_end"):
            val_col = call_kw.get(val_kw)
            if not isinstance(val_col, str):
                continue
            base = val_kw
            for suffix in ("_start", "_end"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
                    break
            sec_kw = f"{base}_sector"
            sec_col_here = call_kw.get(sec_kw, sec_col)
            if sec_kw in call_kw:
                consumed.add(sec_kw)
            if not isinstance(sec_col_here, str):
                continue
            try:
                has_sec = sec_col_here in data
                has_val = val_col in data
            except TypeError:
                continue
            if not (has_sec and has_val):
                continue
            secs = list(data[sec_col_here])
            vals = list(data[val_col])
            known = set(sec.names)
            unknown = [s for s in secs if s not in known]
            if unknown:
                sample = unknown[0]
                raise ValueError(
                    f"c.sectors({axis}-axis): row in data[{sec_col_here!r}] has "
                    f"value {sample!r} which is not a known sector. "
                    f"Known sectors: {list(sec.names)}"
                )
            new_cols[val_col] = [
                SectoredValue(sec.offset(s) + float(v), name_to_idx[s])
                for s, v in zip(secs, vals)
            ]
    if not new_cols and not consumed:
        return call_kw
    call_kw = dict(call_kw)
    for kw in consumed:                       # framework-only, never reach record()
        call_kw.pop(kw, None)
    if new_cols:
        # Normalize to dict-of-lists so the SectoredValue tag (a Python
        # object) survives storage — typed numeric containers would coerce
        # it back to plain float. Downstream artists read columns via
        # `to_list(data[col])`, which works the same on a dict.
        new_data = dict(data) if isinstance(data, dict) else {
            c: list(data[c]) for c in data
        }
        new_data.update(new_cols)
        call_kw["data"] = new_data
    return call_kw


def _expand_frame_defaults(calls):
    """Insert each artist's `frame_defaults` entries immediately before
    the artist call itself, tagged with a trailing `True` so
    `_record_scale` can route a default `order=` to `<axis>_order_default`
    (letting a peer artist's `axis_order` hook win over the suggested
    order without disturbing user-explicit `c.xscale(order=...)`).

    Defaults regenerate here on every replay rather than being recorded —
    `_calls` and the journal carry only user actions. Returns a new list;
    the input is never mutated."""
    out = []
    for call in calls:
        spec = get_artist(call[0])
        if spec is not None and spec.frame_defaults is not None:
            for d in spec.frame_defaults(list(call[1]), dict(call[2])) or ():
                out.append((*d, True))
        out.append(call)
    return out


# Frame-method op names `_replay` dispatches below. Mirrors the elif
# chain one-to-one — adding a branch there means adding the name here
# (and to `_FRAME_METHODS` in chart.py, the recorder's gate), or
# `render.validate` rejects the op before replay ever sees it. The full
# baseline corpus renders through validate, so a missed name fails the
# suite immediately.
_FRAME_OPS = frozenset({
    "title", "subtitle", "caption", "xlabel", "ylabel", "xlim", "ylim",
    "xscale", "yscale", "gridlines", "legend",
    "xticks", "yticks", "spines", "theme", "font",
    "x_expand", "y_expand", "clip", "facecolor",
    "coordinate", "sectors", "aspect",
})


class _PanelState(dict):
    """Panel state dict with a closed key set. The `_replay` initializer
    below defines every valid key; writing or `get`ing any other key
    raises instead of silently creating (or missing) an entry. Without
    this, a misspelled key — including a bad `f"{axis}_..."` prefix —
    renders a wrong figure with no error anywhere."""
    def __setitem__(self, key, value):
        if key not in self:
            raise KeyError(f"unknown panel state key {key!r}")
        dict.__setitem__(self, key, value)

    def get(self, key, default=None):
        if key not in self:
            raise KeyError(f"unknown panel state key {key!r}")
        return dict.__getitem__(self, key)


def _default_state() -> _PanelState:
    """Fresh panel state with every key at its default — the one
    definition of the closed key set. Defaults that read `_FRAME` / spec
    values pick up the ambient theme, so callers wrap this in
    `active_theme` / `active_font` for the panel they mean: replay does
    (via `_node_style`), and the resolved-IR projection and rehydration
    do the same so default-eliding stays symmetric."""
    return _PanelState({
        "artists": [], "title": "", "subtitle": "", "caption": "",
        "xlabel": "", "ylabel": "",
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
        "x_fontstyle": None, "x_fontweight": None, "x_decoration": None,
        "x_direction": _FRAME["tick_direction"], "x_marks": _FRAME["tick_marks"],
        "x_show_labels": True,
        "x_side": _FRAME["x_side"],
        "x_format": None, "x_minor": None,
        "x_step": None, "x_count": None,
        "y_ticks": None, "y_labels": None, "y_rotation": 0, "y_fontsize": None,
        "y_fontstyle": None, "y_fontweight": None, "y_decoration": None,
        "y_direction": _FRAME["tick_direction"], "y_marks": _FRAME["tick_marks"],
        "y_show_labels": True,
        "y_side": _FRAME["y_side"],
        "y_format": None, "y_minor": None,
        "y_step": None, "y_count": None,
        "spine_top": _FRAME["spine_top"], "spine_right": _FRAME["spine_right"],
        "spine_bottom": _FRAME["spine_bottom"], "spine_left": _FRAME["spine_left"],
        # Per-side color/width overrides; None = fall back to base (set via
        # top-level color/width on c.spines()), then to spec.json frame
        # defaults. Tick marks on a given side adopt the same side's spine
        # color/width for visual consistency.
        "spine_top_color": None, "spine_right_color": None,
        "spine_bottom_color": None, "spine_left_color": None,
        "spine_top_width": None, "spine_right_width": None,
        "spine_bottom_width": None, "spine_left_width": None,
        "spine_top_linestyle": None, "spine_right_linestyle": None,
        "spine_bottom_linestyle": None, "spine_left_linestyle": None,
        # Base style — set via top-level kwargs on c.spines(color=, width=,
        # linestyle=). Sides and walls both inherit when their own override
        # is None. None at base level falls through to _FRAME spec defaults.
        "spine_base_color": None, "spine_base_width": None,
        "spine_base_linestyle": None,
        # Walls between sectors — by default inherit the base/spec spine
        # style. c.spines(walls={...}) overrides; c.spines(walls=False) hides.
        "spine_walls": True,
        "spine_walls_color": None, "spine_walls_width": None,
        "spine_walls_linestyle": None,
        "grid": _GRIDSPEC.get("default_on", False), "grid_which": "major",
        "legend": False,
        # Inline-legend placement. Outside tokens: `"right"` (default),
        # `"left"`, `"top"`, `"bottom"` — reserve margin space beside the
        # data area. Inside tokens: `"top-right"`, `"top-left"`,
        # `"bottom-right"`, `"bottom-left"`, `"center"` — overlay the data
        # area.
        "legend_position": "right",
        # Discrete entries per legend column (down-then-across fill);
        # `"top"` / `"bottom"` render a single horizontal row when 1.
        "legend_ncols": 1,
        "legend_reverse": False,
        # Free-form manual rows (`c.legend(entries=[...])`) appended
        # after the harvested entries.
        "legend_manual": None,
        # Data-area clipping on by default — artists past xlim/ylim get
        # cropped at the data boundary. Set False (`c.clip(False)`) to
        # let lines and large markers bleed into the margin space.
        "clip": True,
        "facecolor": None,
        "coordinate": None,
        # Inset panels bound to this chart — overwritten by the resolve
        # pass right after replay (`_resolve_panels`).
        "insets": [],
        # Data-space aspect-ratio lock (mpl `set_aspect` / ggplot
        # `coord_fixed`). None = free; a number r pins one y data unit
        # to r× the pixel length of one x data unit. The layout pre-pass
        # rederives the panel's data dims from the resolved domains
        # (`_apply_share_scaling`), so the lock survives share classes
        # and `fit()`.
        "aspect": None,
        # Sector partitions of the x and y axes — named, length- or
        # member-weighted regions. Continuous sectors remap artist x/y
        # values into a single global coordinate at record time;
        # categorical sectors drive the underlying category scale's
        # cat order, split positions, and inter-block gap. ``chrome``
        # toggles dividers + center labels (off for heatmap-derived
        # sectors — clustering uses sectors purely as a layout primitive).
        "x_sectors": None,        # Sectors value
        "x_sector_column": None,  # column name on artist data for continuous
        "y_sectors": None,
        "y_sector_column": None,
    })


def _record_artist(state, spec, args, kw):
    """One artist call → record dict(s) appended to ``state["artists"]``.
    Passes fresh copies so a `kw.pop(...)` inside `record()` doesn't
    corrupt the stored call dict — re-renders walk the same list.
    `record()` returns a single dict for one-series artists or a list of
    dicts for long-form expansions (line, scatter split by
    color/group/linestyle levels)."""
    call_args = list(args)
    call_kw = dict(kw)
    if "coordinate" in call_kw:
        raise TypeError(
            "coordinate= is not accepted on artist calls. "
            "Use c.coordinate(...) once per panel instead."
        )
    # First-positional-is-data sugar: `c.line(df, x=, y=)` is the
    # same as `c.line(data=df, x=, y=)`. Opt-in via
    # `ArtistSpec.accepts_data_positional=True`. Keeps the long-form
    # call shape from carrying a `data=` keyword on every site;
    # multi-positional shapes (e.g. `(xs, ys)`) are rejected by
    # each record fn so the artist sees only long-form input.
    if (spec.accepts_data_positional and len(call_args) == 1
            and "data" not in call_kw):
        call_kw["data"] = call_args.pop(0)
    # Sector remap: when continuous sectors are active on x or y
    # and the data table has the corresponding sector column,
    # offset values into the global sector coordinate so a single
    # linear scale spans all sectors. Artists draw unchanged.
    # Silent passthrough when the data lacks the sector column
    # (cross-sector annotations like reflines or single-value
    # artists).
    if state["x_sectors"] is not None or state["y_sectors"] is not None:
        call_kw = _sector_remap_data(call_kw, state)
    result = spec.record(*call_args, **call_kw)
    if isinstance(result, list):
        state["artists"].extend(result)
    else:
        state["artists"].append(result)


def _record_spines(state, kw):
    """Top-level color/width/linestyle = base style, inherited by
    any side and by walls unless overridden. Per-target value
    (top=, walls=, etc.) is a bool (toggles visibility) or a
    dict ({color, width, linestyle, visible}, visible defaults
    True). "walls" is the inter-sector wall target."""
    for k in ("color", "width", "linestyle"):
        if k in kw: state[f"spine_base_{k}"] = kw[k]
    for target in ("top", "right", "bottom", "left", "walls"):
        if target not in kw: continue
        v = kw[target]
        if isinstance(v, dict):
            state[f"spine_{target}"] = bool(v.get("visible", True))
            for attr in ("color", "width", "linestyle"):
                if attr in v: state[f"spine_{target}_{attr}"] = v[attr]
        else:
            state[f"spine_{target}"] = bool(v)


def _record_gridlines(state, args, kw):
    """c.gridlines() / c.gridlines(False) toggle; c.gridlines("both")
    or c.gridlines(which="minor") select which tick set draws lines."""
    v = args[0] if args else True
    if isinstance(v, str):
        state["grid"] = True
        state["grid_which"] = v
    else:
        state["grid"] = bool(v)
    if "which" in kw:
        state["grid_which"] = kw["which"]
    if state["grid_which"] not in ("major", "minor", "both"):
        raise ValueError(
            f"c.gridlines(which={state['grid_which']!r}) — pass "
            f"\"major\", \"minor\", or \"both\"."
        )


def _record_legend(state, args, kw):
    state["legend"] = (args[0] if args else True)
    if "position" in kw:
        state["legend_position"] = kw["position"]
    if "ncols" in kw:
        state["legend_ncols"] = kw["ncols"]
    if "reverse" in kw:
        state["legend_reverse"] = kw["reverse"]
    if "entries" in kw:
        state["legend_manual"] = kw["entries"]


def _record_aspect(state, args):
    v = args[0] if args else 1.0
    if v == "equal":
        v = 1.0
    if (isinstance(v, bool) or not isinstance(v, (int, float))
            or v <= 0):
        raise ValueError(
            f"c.aspect({v!r}) — pass \"equal\" or a positive "
            f"number (pixel length of one y unit per one x unit)."
        )
    state["aspect"] = float(v)


def _record_coordinate(state, args):
    state["coordinate"] = args[0]
    # Coord-supplied `y_ticks` default (Cartesian: no attribute →
    # skipped). `is None` check respects any user-set value
    # regardless of call order.
    _cyt = getattr(args[0], "y_ticks", None)
    if _cyt is not None and state.get("y_ticks") is None:
        state["y_ticks"] = _cyt


def _record_sectors(state, args, kw):
    from ..sectors import Sectors
    col  = kw.get("column")
    axis = kw.get("axis", "x")
    # Forward only display kwargs the user explicitly set, so a
    # pre-built `pt.Sectors(...)` keeps its own settings unless
    # overridden — silent-drop would be a footgun.
    extra = {k: kw[k] for k in ("divider", "label", "gap") if k in kw}
    if axis not in ("x", "y"):
        raise ValueError(
            f"c.sectors(axis=): expected 'x' or 'y'; got {axis!r}"
        )
    sec = Sectors.coerce(args[0], name_col=col, **extra)
    # `column=` is the default sector tag for single-position
    # artists (scatter, line, bar, …). Required even for
    # multi-position artists (chord_links) — those override per
    # endpoint via `x1_sector=` / `x2_sector=`, but the typo
    # guard is worth keeping: silently no-op'd remap is a
    # footgun. For cross-sector chord_links, pass one of the
    # endpoint columns as the default.
    if sec.kind == "continuous" and col is None:
        raise TypeError(
            "c.sectors(...): continuous sectors need column= "
            "(name of the sector tag on each data row)."
        )
    # `gap=` is in **pixels** for both kinds. Categorical: routed
    # to `_CategoryScale.split_gap`. Continuous: routed to the
    # `_SectoredLinearScale` via `_AxisDescriptor.sector_gap_px`
    # — both paths absorb the gap at scale-construction time.
    state[f"{axis}_sectors"] = sec
    state[f"{axis}_sector_column"] = col


def _replay(calls):
    """Walk a Chart's recorded calls into a state dict consumed by the
    renderer. Pure function of `calls` and the artist registry — same input
    + same registry → same output. One branch per op below; every branch
    is a one-line state write or a delegate to its `_record_*` handler."""
    state = _default_state()
    # Stable-sort sectors entries to the front. Sectors set the state
    # `_sector_remap_data` reads while processing artist calls; an
    # ordering bug would silently no-op the remap (every row stacked into
    # the first sector). Two-pass dispatch enforces the invariant
    # independent of recording order, so:
    #   - `c.coordinate(...).sectors(...)` chained on a Chart (where
    #     `coordinate` returns self, so the trailing `.sectors()` lands
    #     after any prior artist) still applies its sectors.
    #   - Ancestor sector entries prepended by the parent-cascade walk
    #     (in `_resolve_panels`) still apply, then a leaf-level
    #     `c.sectors(...)` later in the list overwrites (last-write-wins).
    # Sort is stable, so cascade order is preserved among sectors.
    calls = sorted(_expand_frame_defaults(calls),
                   key=lambda c: c[0] != "sectors")
    for call in calls:
        # Entries are 3-tuples `(name, args, kw)` from recorded user code
        # or 4-tuples `(name, args, kw, True)` synthesized just above by
        # `_expand_frame_defaults`. The flag lets `_record_scale`
        # distinguish a frame-default `order=` (loses to a peer artist's
        # `axis_order` hook) from a user-explicit one.
        if len(call) == 4:
            name, args, kw, from_default = call
        else:
            name, args, kw = call
            from_default = False
        spec = get_artist(name)
        if spec is not None:
            _record_artist(state, spec, args, kw)
        elif name == "title":  state["title"] = args[0]
        elif name == "subtitle": state["subtitle"] = args[0]
        elif name == "caption":  state["caption"] = args[0]
        elif name == "xlabel": state["xlabel"] = args[0]
        elif name == "ylabel": state["ylabel"] = args[0]
        elif name == "xlim":   state["xlim"] = (args[0], args[1])
        elif name == "ylim":   state["ylim"] = (args[0], args[1])
        elif name == "xscale": _record_scale(state, "x", args, kw, from_default=from_default)
        elif name == "yscale": _record_scale(state, "y", args, kw, from_default=from_default)
        elif name == "xticks": _record_ticks(state, "x", args, kw)
        elif name == "yticks": _record_ticks(state, "y", args, kw)
        elif name == "x_expand": state["x_expand"] = _normalize_expand(args)
        elif name == "y_expand": state["y_expand"] = _normalize_expand(args)
        elif name == "spines":    _record_spines(state, kw)
        elif name == "gridlines": _record_gridlines(state, args, kw)
        elif name == "legend":    _record_legend(state, args, kw)
        elif name == "clip":   state["clip"] = bool(args[0]) if args else True
        elif name == "facecolor": state["facecolor"] = args[0] if args else None
        elif name == "aspect":     _record_aspect(state, args)
        elif name == "coordinate": _record_coordinate(state, args)
        elif name == "sectors":    _record_sectors(state, args, kw)
        elif name in ("theme", "font"):
            # Applied outside replay (`_layout_engine` wraps each leaf's
            # measurement and render in `_node_style(...)` — theme +
            # font scoping) so the spec dicts are already on the right
            # values by the time we get here. No state to record.
            pass
    # When continuous sectors are active and the user didn't supply an
    # explicit lim, span the full sector range so every partition is
    # visible. Categorical sectors land on a category scale where ``lim``
    # isn't meaningful — skip them here.
    for axis in ("x", "y"):
        sec = state[f"{axis}_sectors"]
        if (sec is not None and sec.kind == "continuous"
                and state[f"{axis}lim"] is None):
            state[f"{axis}lim"] = (0.0, sec.total())
    return state


# ---------------------------------------------------------------------------
# Domain helpers — shared by the panel renderer and the layout pre-pass.
# ---------------------------------------------------------------------------

def _scan_domain(artists, axis, scale_kind="linear"):
    """Collect all values an artist contributes to a given axis ('x' or 'y').

    `datetime.date` / `datetime.datetime` values are coerced to POSIX seconds
    (UTC) so the rest of the autoscaling pipeline can stay numeric. On a log
    scale, an artist's `*domain_log` hook (when set) replaces the plain one."""
    lo, hi = math.inf, -math.inf
    for a in artists:
        spec = get_artist(a["type"])
        if spec is None:
            continue
        fn = spec.xdomain if axis == "x" else spec.ydomain
        if scale_kind == "log":
            log_fn = spec.xdomain_log if axis == "x" else spec.ydomain_log
            if log_fn is not None:
                fn = log_fn
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
    scale's own `format_tick` > the package default `_fmt_tick`.

    `format=` accepts a string only. If the string names a registered
    formatter (see `pt.list_formatters()`), that formatter is used;
    otherwise the string is treated as a Python format spec (wrapped
    via `str.format`). Callables aren't accepted — pass a registered
    formatter name, a format spec, or explicit `labels=[...]`."""
    if user_fmt is None:
        return getattr(scale, "format_tick", _fmt_tick)
    if isinstance(user_fmt, str):
        from ..formatters import get_formatter
        named = get_formatter(user_fmt)
        if named is not None:
            return named
        return user_fmt.format
    raise TypeError(
        f"xticks/yticks(format=) expects a string (registered formatter "
        f"name or Python format spec); got {type(user_fmt).__name__}. "
        f"See pt.list_formatters() for registered names, or use "
        f"labels=[...] for explicit tick labels."
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
        if scale_kind == "log" and lo > 0:
            # linear ±0.5 padding can push the domain nonpositive for
            # values < 0.5; a decade each way stays positive.
            return (lo / 10, hi * 10)
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


def _prebin_hist(state):
    """Compute hist bins on `state["artists"]` so they participate in domain
    scanning. All groups of one call share bin edges so the bars are
    comparable (and stack/dodge/fill positions line up). Idempotent
    (guarded by `_bin_groups` presence)."""
    for a in state["artists"]:
        if a["type"] != "hist" or "_bin_groups" in a:
            continue
        opts = a["opts"]
        vals = a["vals"]
        wgts = a.get("weights")
        all_vals = [v for g in vals for v in g
                    if v is not None and not (isinstance(v, float) and v != v)]
        if not all_vals:
            a["_bin_groups"] = [[] for _ in vals]
            continue
        edges = hist_bin_edges(all_vals,
                               bins=opts.get("bins", 10),
                               binwidth=opts.get("binwidth"),
                               binrange=opts.get("binrange"))
        bin_groups = []
        for j, g in enumerate(vals):
            counts = hist_bin_counts(g, edges,
                                     weights=wgts[j] if wgts else None)
            counts = hist_transform(counts, edges,
                                    density=opts.get("density", False),
                                    cumulative=opts.get("cumulative", False))
            bin_groups.append([{"x0": edges[i], "x1": edges[i + 1],
                                "count": counts[i]}
                               for i in range(len(counts))])
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


def _leaf_axis_kind(state, axis):
    """Classify a leaf's natural axis kind on `axis`: 'categorical', 'numeric',
    'time', or 'empty' (no artists contributing). Explicit `*scale("category")`
    overrides artist-derived classification."""
    if state[f"{axis}scale"] == "category":
        return "categorical"
    if state[f"{axis}scale"] == "time":
        return "time"
    artists = state["artists"]
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
    kinds = {_leaf_axis_kind(state, axis) for state in states}
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


def _categorical_sector_extras(sec):
    """Translate a categorical Sectors into descriptor extras.

    Returns ``(groups, split_gap)``. Splits are left for ``_CategoryScale``
    to derive from ``groups`` in the final cat order — that way a higher-
    priority order source (user ``x_order``, an artist's ``axis_order``)
    can reorder cats and the splits still land where each group changes.
    """
    groups = sec.cat_to_group()
    split_gap = (_D["category_split_gap"] if sec.gap is None else sec.gap)
    return groups, split_gap


def _continuous_sector_extras(sec):
    """Translate a continuous Sectors into descriptor extras for
    ``_SectoredLinearScale``. Returns ``(sector_lengths, sector_gap_px)``
    or ``(None, 0.0)`` when the descriptor should fall back to the
    plain ``_LinearScale`` (no sectors or gap == 0)."""
    if sec is None or sec.kind != "continuous":
        return None, 0.0
    if sec.gap is None or sec.gap <= 0:
        return None, 0.0
    return tuple(sec.lengths), float(sec.gap)


def _axis_descriptor(states: list[dict], axis: str) -> _AxisDescriptor:
    """Compute the descriptor for `axis` ("x" or "y") over a share-
    equivalence class of panel states; a standalone panel passes a list
    of one.

    The first state is the anchor — its scale, lim, order, padding,
    reverse/linthresh/exponent, and sectors win for policy. The
    auto-scanned data range is the union of artists across all states,
    so `force_zero` (bar/hist) and `flips_y_axis` fire if any leaf in
    the class contributes such an artist.

    Categorical cat-order precedence (sectors' ``groups=`` derives splits
    in the final cat order, so split positions are correct under any
    ordering source — only the cat list itself contends):
      1. user-explicit ``c.xscale("category", order=[...])`` → that exact order
      2. an artist's ``axis_order`` hook (e.g. dendrogram's leaf order)
      3. an artist ``frame_defaults`` ``xscale(order=[...])`` (e.g. heatmap's
         first-seen clustered order) → x_order_default
      4. categorical ``c.sectors(...)`` on the axis → flat sector-member order
      5. ``collect_categories`` → first-appearance of unique values
    """
    if len(states) > 1:
        _check_share_kinds_compatible(states, axis)
    for state in states:
        _prebin_hist(state)
    anchor = states[0]
    artists = [a for state in states for a in state["artists"]]
    sec = anchor[f"{axis}_sectors"]
    sec_cat = sec is not None and sec.kind == "categorical"
    explicit_cat = anchor[f"{axis}scale"] == "category"
    auto_cat = _is_categorical_axis(artists, axis)

    if sec_cat or explicit_cat or auto_cat:
        if anchor[f"{axis}_order"] is not None:
            cats = list(anchor[f"{axis}_order"])
        else:
            order = (_artist_axis_order(artists, axis)
                     or anchor[f"{axis}_order_default"])
            if order:
                cats = order
            elif sec_cat:
                cats = list(sec.cats())
            else:
                cats = collect_categories(artists, axis)
        if sec_cat:
            groups, split_gap = _categorical_sector_extras(sec)
            splits = None
        else:
            splits, groups = anchor[f"{axis}_splits"], anchor[f"{axis}_groups"]
            split_gap = anchor[f"{axis}_split_gap"]
        padding = _resolve_shared_padding(states, f"{axis}_padding")
        return _AxisDescriptor(kind="category", cats=cats, padding=padding,
                               splits=splits, split_gap=split_gap,
                               groups=groups)

    is_time = anchor[f"{axis}scale"] == "time" or _is_temporal_axis(artists, axis)
    scale_kind = "time" if is_time else anchor[f"{axis}scale"]
    lo, hi = _scan_domain(artists, axis, scale_kind)
    tight = _axis_is_tight(artists, axis)
    force_zero = _any_artist_force_zero(artists, axis)
    lim = anchor[f"{axis}lim"]
    if is_time:
        lim = _coerce_time_lim(lim)
    lo, hi = _resolve_domain(lo, hi, lim, scale_kind,
                             force_zero=force_zero,
                             tight=tight,
                             expand=_resolve_expand(anchor[f"{axis}_expand"], tight, axis))
    flip = anchor[f"{axis}_reverse"]
    if axis == "y":
        flip = _any_artist_flips_y(artists) or flip
    # Continuous sector gap: route the px gap to _SectoredLinearScale via
    # _AxisDescriptor — same shape as how categorical does it through
    # _CategoryScale.split_gap.
    sec_lengths, sec_gap_px = _continuous_sector_extras(sec)
    return _AxisDescriptor(kind=scale_kind, lo=lo, hi=hi,
                           flip=flip,
                           linthresh=anchor[f"{axis}_linthresh"],
                           exponent=anchor[f"{axis}_exponent"],
                           sector_lengths=sec_lengths,
                           sector_gap_px=sec_gap_px)


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
    others = [state[key] for state in states[1:] if state[key] is not None]
    if others:
        return min(others)
    return _D["category_padding"]


def _inline_legend_layout(state, env=None):
    """Geometry for the in-frame legend a leaf paints.

    Returns a dict with `disc` (list of `(artist, entry)` pairs from
    `spec.legend_entries`), `cont` (list of `(artist, descriptor)` pairs
    from `spec.legend_gradient`), block width/height (`lw`, `lh`), a
    `horizontal` flag (entries arranged left-to-right vs. stacked),
    `ncols` (discrete entries per column, from `c.legend(ncols=)`), and
    the resolved `position` (auto-flipped from inside-corner tokens →
    "right" when a continuous mapping is in play, since an inside
    colorbar inside the data area is incoherent). Returns `None` if
    there's nothing to draw.

    Gradient-only sources on "top"/"bottom" get the horizontal colorbar
    variant (`gradient_h` flag). Continuous + discrete mixed on those
    positions raises — the two blocks only stack on "right"/"left".

    Called by `_required_margin` (to reserve outside-legend margin space)
    and by `_render_inner`'s legend block (to paint), so the two stay in
    sync — change geometry here, both paths follow.

    `env` carries the panel's scales and data dims (x_scale, y_scale,
    iw, ih), stamped onto the artist copy as `_env` so a gradient hook
    whose range depends on render geometry (hexbin's pixel-space bin
    counts) can label exactly what draw will paint. The standalone
    `pt.legend()` leaf harvests without a panel and passes no env."""
    if not state["legend"]:
        return None
    disc, cont = _legend_sources(state, env)
    if not disc and not cont:
        return None
    pos, gradient_h, horizontal, ncols = _legend_position(state, disc, cont)
    lw, lh = _legend_block_size(disc, cont, gradient_h, horizontal, ncols)
    return {"disc": disc, "cont": cont, "lw": lw, "lh": lh,
            "horizontal": horizontal, "gradient_h": gradient_h,
            "position": pos, "ncols": ncols}


def _legend_sources(state, env):
    """Harvest a leaf's legend sources: `disc` (artist, entry) pairs
    from `spec.legend_entries`, `cont` (artist, descriptor) pairs from
    `spec.legend_gradient`, manual `entries=` rows appended last, and
    `reverse=` applied per section."""
    from ._legend import _legend_source_artist, _manual_entry
    disc = []
    cont = []
    for a in state["artists"]:
        spec = get_artist(a["type"])
        if spec is None:
            continue
        a = _legend_source_artist(a)
        if spec.legend_gradient is not None:
            if env is not None:
                a = {**a, "_env": env}
            desc = spec.legend_gradient(a)
            if desc is not None:
                cont.append((a, desc))
        if spec.legend_entries is not None:
            for entry in spec.legend_entries(a):
                disc.append((a, entry))
    manual = []
    for e in state.get("legend_manual") or []:
        entry = _manual_entry(e)
        manual.append((entry["_a"], entry))
    if state.get("legend_reverse"):
        # Mirror the pt.legend() leaf: reverse= flips each section
        # internally; manual rows stay appended after the harvested ones.
        disc.reverse()
        manual.reverse()
    disc.extend(manual)
    return disc, cont


def _legend_position(state, disc, cont):
    """Resolve the requested position into `(pos, gradient_h,
    horizontal, ncols)`."""
    requested = state.get("legend_position", "right")
    if cont and disc and requested in ("top", "bottom"):
        raise ValueError(
            f"chart.legend(position={requested!r}) mixing a continuous "
            f"color mapping with discrete entries is not supported — only "
            f"'right' or 'left' stack the two. A gradient-only chart gets "
            f"a horizontal colorbar on 'top'/'bottom'."
        )
    # Auto-flip inside-corner tokens to "right" for gradient charts — an
    # overlay colorbar would float over the data area, which never reads right.
    if cont and requested in _INSIDE_POSITIONS:
        pos = "right"
    else:
        pos = requested
    # Gradient-only on an outside top/bottom position → horizontal
    # colorbar (strip runs vmin-left → vmax-right, ticks below).
    gradient_h = bool(cont) and pos in ("top", "bottom")
    # `ncols > 1` switches top/bottom from the single-row layout to the
    # same N-column grid the vertical positions use (ggplot2: setting
    # ncol overrides the horizontal direction's one-row default).
    ncols = state.get("legend_ncols", 1)
    horizontal = pos in ("top", "bottom") and ncols == 1 and not cont
    return pos, gradient_h, horizontal, ncols


def _disc_grid_size(disc, ncols):
    """Width/height of the discrete rows spread over `ncols` columns
    (per-column widest entry, `legend.column_gap` apart), including
    sub-group headers — mirror of the paint geometry in
    `_emit_inline_legend_body`."""
    from ._legend import _entry_columns, _partition_by_group
    row_h = _LEGSPEC["row_height"]
    sw    = _LEGSPEC["swatch_width"]
    tick_size = _FONTSPEC["tick_size"]
    label_size = _FONTSPEC["label_size"]
    sub_header_h = label_size + _LEGSPEC["header_pad"]
    sub_groups = _partition_by_group(disc, lambda ae: ae[1].get("group"))
    disc_w = 0.0
    disc_h = 0.0
    for name, items in sub_groups:
        if name:
            disc_w = max(disc_w, measure_text(str(name), label_size))
            disc_h += sub_header_h
        cols = _entry_columns(items, ncols)
        block_w = sum(
            max(sw + _LEGSPEC["swatch_label_gap"] + measure_text(e["label"], tick_size) for _, e in col)
            for col in cols
        ) + (len(cols) - 1) * _LEGSPEC["column_gap"]
        disc_w = max(disc_w, block_w)
        disc_h += len(cols[0]) * row_h
    disc_h += max(0, len(sub_groups) - 1) * _LEGSPEC["section_gap"]
    return disc_w, disc_h


def _legend_block_size(disc, cont, gradient_h, horizontal, ncols):
    """Block width/height `(lw, lh)` for the resolved legend layout."""
    row_h = _LEGSPEC["row_height"]
    pad_x = _LEGSPEC["pad_x"]
    pad_y = _LEGSPEC["pad_y"]
    sw    = _LEGSPEC["swatch_width"]
    tick_size = _FONTSPEC["tick_size"]

    if gradient_h:
        # Horizontal gradient-only block: like the vertical gradient-only
        # case, no background rect and no padding — the strip borders
        # itself and sits flush against the data area (modulo legend_gap).
        from ._legend import _inline_gradient_block_size_h
        return _inline_gradient_block_size_h([d for _, d in cont])
    if horizontal:
        # Discrete-only horizontal row. Entries arranged left-to-right.
        entry_ws = [sw + _LEGSPEC["swatch_label_gap"] + measure_text(e["label"], tick_size) for _, e in disc]
        spacer = 2 * pad_x
        lw = 2 * pad_x + sum(entry_ws) + (len(disc) - 1) * spacer
        lh = row_h + 2 * pad_y
        return lw, lh
    if cont and not disc:
        # Gradient-only block: no background rect, no padding around the
        # block — the strip carries its own border. Sits flush against
        # the data area's outer edge (modulo legend_gap).
        from ._legend import _inline_gradient_block_size
        return _inline_gradient_block_size([d for _, d in cont])
    # Vertical mixed (cont + disc) or discrete-only. Stack continuous
    # strips on top, discrete rows below, with section_gap between.
    # Background rect wraps everything → outer padding.
    from ._legend import _inline_gradient_block_size
    disc_w, disc_h = _disc_grid_size(disc, ncols)
    cont_w, cont_h = _inline_gradient_block_size([d for _, d in cont])
    lw = max(disc_w, cont_w) + 2 * pad_x
    lh = cont_h + disc_h + 2 * pad_y
    if cont and disc:
        lh += _LEGSPEC["section_gap"]
    return lw, lh


def _descriptor_scale(state, axis, span):
    """Provisional per-panel scale at a fixed pixel span — the
    reservation-pass scale. Body-first reservation (`_required_margin`)
    and the circular radial reservation (`_chrome_circular.chrome_pad`)
    both build scales this way; the render pass uses the
    layout-coordinated `_build_xy_scales` instead."""
    ax = _axis_descriptor([state], axis)
    inverted = (ax.kind != "category"
                and (ax.flip if axis == "x" else not ax.flip))
    return ax.build(span, 0) if inverted else ax.build(0, span)


def _axis_ticks_labels(state, axis, scale, span):
    """Resolved tick positions + label strings for one axis: the
    density rule, auto ticks, formatter, and continuous-sector
    expansion, in one place. Shared by `_derive_panel_inputs` (both
    the reservation and render passes) and by the circular radial
    reservation (`_chrome_circular.chrome_pad`) — every consumer
    walks identical numbers.

    Continuous sectors: auto ticks are meaningless on a global-offset
    coord, so the default is none. User-supplied ticks via xticks/yticks
    are interpreted as per-sector LOCAL positions and replicated at
    each sector's offset."""
    n = max(2, min(8, int(span // _FRAME[f"tick_density_{axis}_px"])))
    ticks = (state[f"{axis}_ticks"] if state[f"{axis}_ticks"] is not None
             else _auto_major_ticks(scale, n, state[f"{axis}_step"],
                                    state[f"{axis}_count"]))
    fmt = _resolve_tick_formatter(state[f"{axis}_format"], scale)
    labels = (state[f"{axis}_labels"] if state[f"{axis}_labels"] is not None
              else [fmt(t) for t in ticks])
    sec = state[f"{axis}_sectors"]
    if sec is not None and sec.kind == "continuous":
        ticks, labels = sec.expand_ticks(
            ticks if state[f"{axis}_ticks"] is not None else [],
            labels if state[f"{axis}_ticks"] is not None else [])
    return ticks, labels


def _derive_panel_inputs(state, *, x_scale, y_scale, dw, dh, layout_opts):
    """Derive ticks, labels, sizes, rotations, suppress flags and hide
    flags for one panel — a pure function of resolved state, scales,
    and pixel dims; no new decisions. Shared by `_required_margin` (via
    `_chrome_bands.label_band_sizes`) and `_render_inner` so the reservation
    and render passes walk identical numbers.

    `x_scale` / `y_scale` are caller-built: the reservation pass uses the
    per-panel descriptor (no layout coordination), the render pass uses
    `_build_xy_scales` which honors `panel_opts.x_axis` / `y_axis`. The
    rest of the resolution is identical."""
    tick_size = _FONTSPEC["tick_size"]

    x_ticks, x_labels = _axis_ticks_labels(state, "x", x_scale, dw)
    y_ticks, y_labels = _axis_ticks_labels(state, "y", y_scale, dh)

    # Joined-side hide flags — drop reservations the renderer skips.
    hide_t = layout_opts.hide_top
    hide_b = layout_opts.hide_bottom
    hide_l = layout_opts.hide_left
    hide_r = layout_opts.hide_right

    # Decided chrome visibility — the one place state and layout flags
    # combine into "draw it?" booleans (see `_chrome_visibility`). `xticks
    # (labels=False)` joins forces with the share-pair label suppression
    # there — either one drops tick labels on the corresponding side,
    # routed by axis side so a flipped axis pulls suppression from the
    # matching joined edge (top edge for x_side="top", etc.).
    chrome = resolve_axis_chrome(state, layout_opts)

    return SimpleNamespace(
        chrome=chrome,
        x_scale=x_scale, y_scale=y_scale,
        x_ticks=x_ticks, x_labels=x_labels,
        y_ticks=y_ticks, y_labels=y_labels,
        x_size=state["x_fontsize"] if state["x_fontsize"] is not None else tick_size,
        y_size=state["y_fontsize"] if state["y_fontsize"] is not None else tick_size,
        x_rot=state["x_rotation"] or 0,
        y_rot=state["y_rotation"] or 0,
        # Variant faces have their own advance widths — the margin
        # reservation must measure with the same style/weight the render
        # pass draws with.
        x_style=state["x_fontstyle"] or "normal",
        y_style=state["y_fontstyle"] or "normal",
        x_weight=state["x_fontweight"] or "normal",
        y_weight=state["y_fontweight"] or "normal",
        hide_t=hide_t, hide_b=hide_b, hide_l=hide_l, hide_r=hide_r,
    )


# ---------------------------------------------------------------------------
# Margin pipeline — how a side's final margin gets built.
# ---------------------------------------------------------------------------
# The number the panel transform uses as `M[side]`
# is composed in four pieces, each from a different function:
#
#   M[side] = floor + axis_band + text_overhang + outside_legend_reservation
#                                  └─ "inflation": everything beyond the band ─┘
#
# Pieces:
#   1. `_enforce_floors(leaf._margin)`         — per-side floor (whitespace),
#                                                in `_layout_engine.py`.
#   2. `_chrome_bands.label_band_sizes(...)`          — pure axis band: tick marks,
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


def _required_margin(state, dw, dh, layout_opts: "_PanelOpts") -> dict:
    """Margin a body-first leaf actually needs to fit its title, axis
    labels, tick labels, and any outside-positioned in-frame legend.

    Returns a plain dict with the same keys as `_margin` — the caller
    adds this to the per-side floor. Body-first specifically: data dims
    are fixed, so tick density and labels are deterministic and the
    computation is a single pass (no chicken-and-egg with margin).

    `layout_opts` lets the formula drop reservations for content the renderer is
    going to suppress (joined share-pair sides): tick labels via
    `suppress_*_labels`, xlabel/ylabel/title via `hide_*`.

    The geometry mirrors `_render_inner`'s placement formulas — keep them
    in sync if either changes."""
    # Provisional scales at the fixed data dims — body-first means iw/ih
    # are decided up front, no iteration needed.
    x_scale = _descriptor_scale(state, "x", dw)
    y_scale = _descriptor_scale(state, "y", dh)
    inp = _derive_panel_inputs(state, x_scale=x_scale, y_scale=y_scale,
                               dw=dw, dh=dh, layout_opts=layout_opts)
    bands, _ = _chrome_bands.label_band_sizes(state, inp, dw, dh)
    top, right, bottom, left = bands["top"], bands["right"], bands["bottom"], bands["left"]

    # Cross-side text overhang: a title / xlabel longer than `dw` is
    # centered on `iw/2`, so it sticks out past the data area on left
    # and right by `(text_w - dw) / 2`. A ylabel (rotated -90, centered
    # on `ih/2`) is the same story but vertical: text longer than `dh`
    # spills past top and bottom equally. Margins grow by the overhang
    # so the rendered text fits inside the canvas. Skip when the label
    # / title is hidden (joined side) since the renderer won't draw it.
    # Applied here (not in `_chrome_bands.label_band_sizes`) because positioning
    # code in `_render_inner` needs the *axis band* without overhang — a
    # wide title shouldn't displace the ylabel from its natural slot.
    label_size = _FONTSPEC["label_size"]
    title_size = _FONTSPEC["title_size"]
    if state["title"]:
        title_overhang = max(0.0, (measure_text(state["title"], title_size) - dw) / 2.0)
        left  = max(left,  title_overhang)
        right = max(right, title_overhang)
    if state["subtitle"]:
        sub_overhang = max(0.0, (measure_text(state["subtitle"], _FONTSPEC["subtitle_size"]) - dw) / 2.0)
        left  = max(left,  sub_overhang)
        right = max(right, sub_overhang)
    if state["caption"]:
        # Caption band is not part of `label_band_sizes` — the bottom
        # band positions the outside-bottom legend, and the caption sits
        # past that legend (see `emit_frame_labels`). Reserve it here,
        # additively like the legend below. Anchored right at x=dw, a
        # caption wider than the data area spills left only.
        caption_size = _FONTSPEC["caption_size"]
        bottom += _PADSPEC["caption"] + text_block_height(state["caption"], caption_size)
        left = max(left, max(0.0, measure_text(state["caption"], caption_size) - dw))
    if inp.chrome["x"]["draw_axis_label"]:
        xlabel_overhang = max(0.0, (measure_text(state["xlabel"], label_size) - dw) / 2.0)
        left  = max(left,  xlabel_overhang)
        right = max(right, xlabel_overhang)
    if inp.chrome["y"]["draw_axis_label"]:
        ylabel_overhang = max(0.0, (measure_text(state["ylabel"], label_size) - dh) / 2.0)
        top    = max(top,    ylabel_overhang)
        bottom = max(bottom, ylabel_overhang)
    # Rightmost x-tick label's rotated AABB extends past x=iw by half its
    # width — a cross-axis spillover from the bottom axis. Measured in
    # `_chrome_bands.label_band_sizes` and reported separately so an inline right
    # legend (which positions itself at `iw + bands["right"] + gap`)
    # hugs the data area instead of being shoved out by a fat 45°-
    # rotated tick label. The y-tick mirror (top/bottom) keeps the
    # cap-top / descender of the first/last horizontal y-tick label from
    # bleeding past the panel edges or figure boundary.
    left  = max(left,  bands["left_xtl_overhang"])
    right = max(right, bands["right_xtl_overhang"])
    top    = max(top,    bands["top_ytl_overhang"])
    bottom = max(bottom, bands["bottom_ytl_overhang"])

    # Outside-legend reservation is *additive* with the label band so the
    # legend block sits beyond the title/labels rather than overlapping
    # them. Inside-corner positions paint over the data area and reserve
    # nothing extra.
    leg = _inline_legend_layout(state, env=SimpleNamespace(
        x_scale=x_scale, y_scale=y_scale, iw=dw, ih=dh))
    if leg is not None and leg["position"] not in _INSIDE_POSITIONS:
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

    # Coordinate-aware frame: the projected parallelogram may extend outside
    # the data area.  Inflate each side by however far the frame sticks out.
    _margin_cobj = state.get("coordinate")
    if (_margin_cobj is not None
            and (hasattr(_margin_cobj, "draw_frame")
                 or hasattr(_margin_cobj, "svg_transform"))):
        _proj = _margin_cobj({}, dw, dh)
        _bl_x, _bl_y = _proj(0.0, 0.0)
        _tl_x, _tl_y = _proj(0.0, 1.0)
        _br_x, _br_y = _proj(1.0, 0.0)
        _tr_x, _tr_y = _proj(1.0, 1.0)
        _xs = [_bl_x, _tl_x, _br_x, _tr_x]
        _ys = [_bl_y, _tl_y, _br_y, _tr_y]
        left   = max(left,   max(0.0, -min(_xs)))
        right  = max(right,  max(0.0,  max(_xs) - dw))
        top    = max(top,    max(0.0, -min(_ys)))
        bottom = max(bottom, max(0.0,  max(_ys) - dh))

    return {"top":    int(round(top)),
            "right":  int(round(right)),
            "bottom": int(round(bottom)),
            "left":   int(round(left))}

# ---------------------------------------------------------------------------
# color assignment — decided at resolve time, stamped on the records
# ---------------------------------------------------------------------------

def _stamp_artist_colors(state) -> None:
    """Stamp each artist record's final `_color` — only color-cycle
    artists consume the cycle. Deterministic and idempotent; called at
    resolve time (`_resolve_panels`) so the resolved IR carries final
    colors, and again defensively at draw."""
    color_idx = 0
    for a in state["artists"]:
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
        elif "_j" in a:
            # Fan-out group member — one record per level of a `color=`
            # column, carrying the grouping symbolically (`groups`, `_j`,
            # `opts["palette"]`). The per-level color resolves at draw
            # context, not at record time; siblings are one logical
            # artist, so the cycle is never consumed.
            a["_color"] = group_color(a["groups"], a["opts"].get("palette"),
                                      a["_j"], None)
        elif spec is not None and spec.uses_color_cycle:
            a["_color"] = TAB10[color_idx % 10]
            color_idx += 1
        else:
            a["_color"] = spec.default_color if spec else None
