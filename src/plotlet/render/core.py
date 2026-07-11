"""Render engine — pure functions over Chart state.

The deferred-render pipeline:
  1. A `Chart` (defined in `chart.py`) records user calls into `_calls`.
  2. `Chart.to_svg()` delegates to `_layout_engine._render_layout`.
  3. That runs the layout pre-pass (`_build_panel_opts`, share
     coordination, margin resolution) then, per placement, opens a
     panel `<g>` via `_panel_open` and fills it via `_render_inner`.
  4. `_render_inner` does: pre-process → domain → scales → grid →
     artists → spines/ticks → labels/title → legend.

A lone chart runs the exact same pipeline as a 1x1 grid — there is no
separate standalone path.

Every function here takes its state explicitly — there's no class to
hold it. Adding a new plot type means calling `add_artist(...)` from
outside; no monkey-patching, no editing this file.
"""
from __future__ import annotations

import datetime
import html
import json
import math
from dataclasses import dataclass
from importlib.metadata import version as _pkg_version
from types import SimpleNamespace

from .._spec import (
    SPEC, _MARGIN_FLOOR, _FRAME, _GRIDSPEC, _FONTSPEC, _LEGSPEC,
    _LAYOUTSPEC, _PADSPEC, _D, _DASH,
)
_SECTORSPEC = SPEC["sectors"]
from ..draw import resolve_color, TAB10
from ..scales import (_nice_domain, _fmt_tick, _to_epoch,
                      _coerce_time_lim, _AxisDescriptor)
from ..sectors import SectoredValue
from ..draw import measure_text, text_block_height
from ..draw import coord, rect, segment, text_path
from .. import _regions
from . import _chrome
from ..utils import (hist_bin_edges, hist_bin_counts, hist_transform,
                     collect_categories)
from ..registry import RenderContext, get_artist, _COORD_SUPPORT

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
# still import it from `.core`.


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

    Signature: xticks(ticks=None, labels=None, *, rotation=0, fontsize=None,
    fontstyle=None, fontweight=None, ...).
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
            # labels would crowd a different label (e.g. a sector name
            # as xlabel under per-sector tick marks).
            st[f"{axis}_show_labels"] = False
        else:
            st[f"{axis}_labels"] = list(v) if v is not None else None
    if "rotation" in kw:  st[f"{axis}_rotation"]  = kw["rotation"]
    if "fontsize" in kw:  st[f"{axis}_fontsize"]  = kw["fontsize"]
    if "fontstyle" in kw: st[f"{axis}_fontstyle"] = kw["fontstyle"]
    if "fontweight" in kw: st[f"{axis}_fontweight"] = kw["fontweight"]
    if "decoration" in kw: st[f"{axis}_decoration"] = kw["decoration"]
    if "direction" in kw: st[f"{axis}_direction"] = kw["direction"]
    if "marks" in kw:     st[f"{axis}_marks"]     = bool(kw["marks"])
    if "format" in kw:    st[f"{axis}_format"]    = kw["format"]
    if "minor" in kw:     st[f"{axis}_minor"]     = kw["minor"]
    if "step" in kw:      st[f"{axis}_step"]      = float(kw["step"])
    if "count" in kw:     st[f"{axis}_count"]     = int(kw["count"])
    # Primary axis placement. Matches plotly's `side`, ggplot2's `position`,
    # d3's axisTop/axisRight. Moves the spine, ticks, labels and the
    # xlabel/ylabel as a single block to the named edge.
    if "side" in kw:
        valid = {"x": ("bottom", "top"), "y": ("left", "right")}[axis]
        if kw["side"] not in valid:
            raise ValueError(f"{axis}ticks(side=...) must be one of {valid}, "
                             f"got {kw['side']!r}")
        st[f"{axis}_side"] = kw["side"]


# Conversion factors to pixels, CSS standard: 1 in = 96 px, 1 in = 2.54 cm,
# 1 in = 72 pt. Internal layout math is always pixels — string units are
# parsed once at the constructor boundary and stored as ints.
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


def _sector_remap_data(call_kw, st):
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
        sec     = st[f"{axis}_sectors"]
        sec_col = st[f"{axis}_sector_column"]
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
    "xscale", "yscale", "grid", "legend",
    "xticks", "yticks", "spines", "theme", "font",
    "x_expand", "y_expand", "clip", "facecolor",
    "coordinate", "sectors", "aspect",
})


def _replay(calls):
    """Walk a Chart's recorded calls into a state dict consumed by the
    renderer. Pure function of `calls` and the artist registry — same input
    + same registry → same output."""
    st = {
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
        "x_direction": _FRAME["tick_direction"], "x_marks": True,
        "x_show_labels": True,
        "x_side": _FRAME["x_side"],
        "x_format": None, "x_minor": None,
        "x_step": None, "x_count": None,
        "y_ticks": None, "y_labels": None, "y_rotation": 0, "y_fontsize": None,
        "y_fontstyle": None, "y_fontweight": None, "y_decoration": None,
        "y_direction": _FRAME["tick_direction"], "y_marks": True,
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
    }
    # Stable-sort sectors entries to the front. Sectors set the state
    # `_sector_remap_data` reads while processing artist calls; an
    # ordering bug would silently no-op the remap (every row stacked into
    # the first sector). Two-pass dispatch enforces the invariant
    # independent of recording order, so:
    #   - `c.coordinate(...).sectors(...)` chained on a Chart (where
    #     `coordinate` returns self, so the trailing `.sectors()` lands
    #     after any prior artist) still applies its sectors.
    #   - Ancestor sector entries prepended by the parent-cascade walk
    #     (in `_build_panel_opts`) still apply, then a leaf-level
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
            # Pass fresh copies so a `kw.pop(...)` inside `record()` doesn't
            # corrupt the stored call dict — re-renders walk the same list.
            # `record()` returns a single dict for one-series artists or a
            # list of dicts for long-form expansions (line, scatter split
            # by color/group/linestyle levels).
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
            if st["x_sectors"] is not None or st["y_sectors"] is not None:
                call_kw = _sector_remap_data(call_kw, st)
            result = spec.record(call_args, call_kw)
            if isinstance(result, list):
                st["artists"].extend(result)
            else:
                st["artists"].append(result)
        elif name == "title":  st["title"] = args[0]
        elif name == "subtitle": st["subtitle"] = args[0]
        elif name == "caption":  st["caption"] = args[0]
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
            # Top-level color/width/linestyle = base style, inherited by
            # any side and by walls unless overridden. Per-target value
            # (top=, walls=, etc.) is a bool (toggles visibility) or a
            # dict ({color, width, linestyle, visible}, visible defaults
            # True). "walls" is the inter-sector wall target.
            for k in ("color", "width", "linestyle"):
                if k in kw: st[f"spine_base_{k}"] = kw[k]
            for target in ("top", "right", "bottom", "left", "walls"):
                if target not in kw: continue
                v = kw[target]
                if isinstance(v, dict):
                    st[f"spine_{target}"] = bool(v.get("visible", True))
                    for attr in ("color", "width", "linestyle"):
                        if attr in v: st[f"spine_{target}_{attr}"] = v[attr]
                else:
                    st[f"spine_{target}"] = bool(v)
        elif name == "grid":
            # c.grid() / c.grid(False) toggle; c.grid("both") or
            # c.grid(which="minor") select which tick set draws lines.
            v = args[0] if args else True
            if isinstance(v, str):
                st["grid"] = True
                st["grid_which"] = v
            else:
                st["grid"] = bool(v)
            if "which" in kw:
                st["grid_which"] = kw["which"]
            if st["grid_which"] not in ("major", "minor", "both"):
                raise ValueError(
                    f"c.grid(which={st['grid_which']!r}) — pass \"major\", "
                    f"\"minor\", or \"both\"."
                )
        elif name == "legend":
            st["legend"] = (args[0] if args else True)
            if "position" in kw:
                st["legend_position"] = kw["position"]
            if "ncols" in kw:
                st["legend_ncols"] = kw["ncols"]
            if "reverse" in kw:
                st["legend_reverse"] = kw["reverse"]
            if "entries" in kw:
                st["legend_manual"] = kw["entries"]
        elif name == "clip":   st["clip"] = bool(args[0]) if args else True
        elif name == "facecolor": st["facecolor"] = args[0] if args else None
        elif name == "aspect":
            v = args[0] if args else 1.0
            if v == "equal":
                v = 1.0
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or v <= 0):
                raise ValueError(
                    f"c.aspect({v!r}) — pass \"equal\" or a positive "
                    f"number (pixel length of one y unit per one x unit)."
                )
            st["aspect"] = float(v)
        elif name == "coordinate":
            st["coordinate"] = args[0]
            # Coord-supplied `y_ticks` default (Cartesian: no attribute →
            # skipped). `is None` check respects any user-set value
            # regardless of call order.
            _cyt = getattr(args[0], "y_ticks", None)
            if _cyt is not None and st.get("y_ticks") is None:
                st["y_ticks"] = _cyt
        elif name == "sectors":
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
            st[f"{axis}_sectors"] = sec
            st[f"{axis}_sector_column"] = col
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
        sec = st[f"{axis}_sectors"]
        if (sec is not None and sec.kind == "continuous"
                and st[f"{axis}lim"] is None):
            st[f"{axis}lim"] = (0.0, sec.total())
    return st


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
    scanning. All groups of one call share bin edges so the bars are
    comparable (and stack/dodge/fill positions line up). Idempotent
    (guarded by `_bin_groups` presence)."""
    for a in st["artists"]:
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


def _x_descriptor(st) -> _AxisDescriptor:
    """Compute this panel's natural x-axis descriptor from its own state.

    Categorical cat-order precedence (sectors' ``groups=`` derives splits
    in the final cat order, so split positions are correct under any
    ordering source — only the cat list itself contends):
      1. user-explicit ``c.xscale("category", order=[...])`` → that exact order
      2. an artist's ``axis_order`` hook (e.g. dendrogram's leaf order)
      3. an artist ``frame_defaults`` ``xscale(order=[...])`` (e.g. heatmap's
         first-seen clustered order) → x_order_default
      4. categorical ``c.sectors(...)`` on x → flat sector-member order
      5. ``collect_categories`` → first-appearance of unique x values
    """
    _prebin_hist(st)
    artists = st["artists"]
    sec = st["x_sectors"]
    sec_cat = sec is not None and sec.kind == "categorical"
    explicit_cat = st["xscale"] == "category"
    auto_cat = _is_categorical_axis(artists, "x")

    if sec_cat or explicit_cat or auto_cat:
        if st["x_order"] is not None:
            cats = list(st["x_order"])
        else:
            order = _artist_axis_order(artists, "x") or st["x_order_default"]
            if order:
                cats = order
            elif sec_cat:
                cats = list(sec.cats())
            else:
                cats = collect_categories(artists, "x")
        if sec_cat:
            groups, split_gap = _categorical_sector_extras(sec)
            splits = None
        else:
            splits, groups = st["x_splits"], st["x_groups"]
            split_gap = st["x_split_gap"]
        padding = _D["category_padding"] if st["x_padding"] is None else st["x_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding,
                               splits=splits, split_gap=split_gap,
                               groups=groups)

    is_time = st["xscale"] == "time" or _is_temporal_axis(artists, "x")
    x_scale_kind = "time" if is_time else st["xscale"]
    x_lo, x_hi = _scan_domain(artists, "x", x_scale_kind)
    x_tight = _axis_is_tight(artists, "x")
    x_force_zero = _any_artist_force_zero(artists, "x")
    xlim = _coerce_time_lim(st["xlim"]) if is_time else st["xlim"]
    x_min, x_max = _resolve_domain(x_lo, x_hi, xlim, x_scale_kind,
                                    force_zero=x_force_zero,
                                    tight=x_tight,
                                    expand=_resolve_expand(st["x_expand"], x_tight, "x"))
    # Continuous sector gap: route the px gap to _SectoredLinearScale via
    # _AxisDescriptor — same shape as how categorical does it through
    # _CategoryScale.split_gap.
    sec_lengths, sec_gap_px = _continuous_sector_extras(sec)
    return _AxisDescriptor(kind=x_scale_kind, lo=x_min, hi=x_max,
                           flip=st["x_reverse"],
                           linthresh=st["x_linthresh"],
                           exponent=st["x_exponent"],
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


def _y_descriptor(st) -> _AxisDescriptor:
    """Compute this panel's natural y-axis descriptor from its own state.

    Categorical precedence mirrors `_x_descriptor`. `force_zero` still
    fires for bar/hist so numeric y-axes anchor at 0.
    """
    _prebin_hist(st)
    artists = st["artists"]
    sec = st["y_sectors"]
    sec_cat = sec is not None and sec.kind == "categorical"
    explicit_cat = st["yscale"] == "category"
    auto_cat = _is_categorical_axis(artists, "y")

    if sec_cat or explicit_cat or auto_cat:
        if st["y_order"] is not None:
            cats = list(st["y_order"])
        else:
            order = _artist_axis_order(artists, "y") or st["y_order_default"]
            if order:
                cats = order
            elif sec_cat:
                cats = list(sec.cats())
            else:
                cats = collect_categories(artists, "y")
        if sec_cat:
            groups, split_gap = _categorical_sector_extras(sec)
            splits = None
        else:
            splits, groups = st["y_splits"], st["y_groups"]
            split_gap = st["y_split_gap"]
        padding = _D["category_padding"] if st["y_padding"] is None else st["y_padding"]
        return _AxisDescriptor(kind="category", cats=cats, padding=padding,
                               splits=splits, split_gap=split_gap,
                               groups=groups)

    is_time = st["yscale"] == "time" or _is_temporal_axis(artists, "y")
    y_scale_kind = "time" if is_time else st["yscale"]
    force_zero = _any_artist_force_zero(artists, "y")
    y_lo, y_hi = _scan_domain(artists, "y", y_scale_kind)
    y_tight = _axis_is_tight(artists, "y")
    ylim = _coerce_time_lim(st["ylim"]) if is_time else st["ylim"]
    y_min, y_max = _resolve_domain(y_lo, y_hi, ylim, y_scale_kind,
                                    force_zero=force_zero,
                                    tight=y_tight,
                                    expand=_resolve_expand(st["y_expand"], y_tight, "y"))
    sec_lengths, sec_gap_px = _continuous_sector_extras(sec)
    return _AxisDescriptor(kind=y_scale_kind, lo=y_min, hi=y_max,
                           flip=_any_artist_flips_y(artists) or st["y_reverse"],
                           linthresh=st["y_linthresh"],
                           exponent=st["y_exponent"],
                           sector_lengths=sec_lengths,
                           sector_gap_px=sec_gap_px)


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
    sec = anchor["x_sectors"]
    sec_cat = sec is not None and sec.kind == "categorical"
    explicit_cat = anchor["xscale"] == "category"
    auto_cat = _is_categorical_axis(all_artists, "x")
    if sec_cat or explicit_cat or auto_cat:
        if anchor["x_order"] is not None:
            cats = list(anchor["x_order"])
        else:
            order = (_artist_axis_order(all_artists, "x")
                     or anchor["x_order_default"])
            if order:
                cats = order
            elif sec_cat:
                cats = list(sec.cats())
            else:
                cats = collect_categories(all_artists, "x")
        if sec_cat:
            groups, split_gap = _categorical_sector_extras(sec)
            splits = None
        else:
            splits, groups = anchor["x_splits"], anchor["x_groups"]
            split_gap = anchor["x_split_gap"]
        padding = _resolve_shared_padding(states, "x_padding")
        return _AxisDescriptor(kind="category", cats=cats, padding=padding,
                               splits=splits, split_gap=split_gap,
                               groups=groups)
    is_time = anchor["xscale"] == "time" or _is_temporal_axis(all_artists, "x")
    x_scale_kind = "time" if is_time else anchor["xscale"]
    x_lo, x_hi = _scan_domain(all_artists, "x", x_scale_kind)
    x_tight = _axis_is_tight(all_artists, "x")
    x_force_zero = _any_artist_force_zero(all_artists, "x")
    xlim = _coerce_time_lim(anchor["xlim"]) if is_time else anchor["xlim"]
    x_min, x_max = _resolve_domain(x_lo, x_hi, xlim, x_scale_kind,
                                    force_zero=x_force_zero,
                                    tight=x_tight,
                                    expand=_resolve_expand(anchor["x_expand"], x_tight, "x"))
    sec_lengths, sec_gap_px = _continuous_sector_extras(sec)
    return _AxisDescriptor(kind=x_scale_kind, lo=x_min, hi=x_max,
                           flip=anchor["x_reverse"],
                           linthresh=anchor["x_linthresh"],
                           exponent=anchor["x_exponent"],
                           sector_lengths=sec_lengths,
                           sector_gap_px=sec_gap_px)


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
    sec = anchor["y_sectors"]
    sec_cat = sec is not None and sec.kind == "categorical"
    explicit_cat = anchor["yscale"] == "category"
    auto_cat = _is_categorical_axis(all_artists, "y")
    if sec_cat or explicit_cat or auto_cat:
        if anchor["y_order"] is not None:
            cats = list(anchor["y_order"])
        else:
            order = (_artist_axis_order(all_artists, "y")
                     or anchor["y_order_default"])
            if order:
                cats = order
            elif sec_cat:
                cats = list(sec.cats())
            else:
                cats = collect_categories(all_artists, "y")
        if sec_cat:
            groups, split_gap = _categorical_sector_extras(sec)
            splits = None
        else:
            splits, groups = anchor["y_splits"], anchor["y_groups"]
            split_gap = anchor["y_split_gap"]
        padding = _resolve_shared_padding(states, "y_padding")
        return _AxisDescriptor(kind="category", cats=cats, padding=padding,
                               splits=splits, split_gap=split_gap,
                               groups=groups)
    is_time = anchor["yscale"] == "time" or _is_temporal_axis(all_artists, "y")
    y_scale_kind = "time" if is_time else anchor["yscale"]
    force_zero = _any_artist_force_zero(all_artists, "y")
    y_lo, y_hi = _scan_domain(all_artists, "y", y_scale_kind)
    y_tight = _axis_is_tight(all_artists, "y")
    ylim = _coerce_time_lim(anchor["ylim"]) if is_time else anchor["ylim"]
    y_min, y_max = _resolve_domain(y_lo, y_hi, ylim, y_scale_kind,
                                    force_zero=force_zero,
                                    tight=y_tight,
                                    expand=_resolve_expand(anchor["y_expand"], y_tight, "y"))
    sec_lengths, sec_gap_px = _continuous_sector_extras(sec)
    return _AxisDescriptor(kind=y_scale_kind, lo=y_min, hi=y_max,
                           flip=_any_artist_flips_y(all_artists) or anchor["y_reverse"],
                           linthresh=anchor["y_linthresh"],
                           exponent=anchor["y_exponent"],
                           sector_lengths=sec_lengths,
                           sector_gap_px=sec_gap_px)


def _inline_legend_layout(st):
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
    sync — change geometry here, both paths follow."""
    if not st["legend"]:
        return None
    from ._legend import _legend_source_artist, _manual_entry
    disc = []
    cont = []
    for a in st["artists"]:
        spec = get_artist(a["type"])
        if spec is None:
            continue
        a = _legend_source_artist(a)
        if spec.legend_gradient is not None:
            desc = spec.legend_gradient(a)
            if desc is not None:
                cont.append((a, desc))
        if spec.legend_entries is not None:
            for entry in spec.legend_entries(a):
                disc.append((a, entry))
    for e in st.get("legend_manual") or []:
        entry = _manual_entry(e)
        disc.append((entry["_a"], entry))
    if st.get("legend_reverse"):
        disc.reverse()
    if not disc and not cont:
        return None

    requested = st.get("legend_position", "right")
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
    ncols = st.get("legend_ncols", 1)
    horizontal = pos in ("top", "bottom") and ncols == 1 and not cont

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
        lw, lh = _inline_gradient_block_size_h([d for _, d in cont])
    elif horizontal:
        # Discrete-only horizontal row. Entries arranged left-to-right.
        entry_ws = [sw + 6 + measure_text(e["label"], tick_size) for _, e in disc]
        spacer = 2 * pad_x
        lw = 2 * pad_x + sum(entry_ws) + (len(disc) - 1) * spacer
        lh = row_h + 2 * pad_y
    elif cont and not disc:
        # Gradient-only block: no background rect, no padding around the
        # block — the strip carries its own border. Sits flush against
        # the data area's outer edge (modulo legend_gap).
        from ._legend import _inline_gradient_block_size
        lw, lh = _inline_gradient_block_size([d for _, d in cont])
    else:
        # Vertical mixed (cont + disc) or discrete-only. Stack continuous
        # strips on top, discrete rows below, with section_gap between.
        # Background rect wraps everything → outer padding. Each
        # sub-group's rows spread over `ncols` columns (per-column widest
        # entry, `legend.column_gap` apart) — mirror of the paint
        # geometry in `_emit_inline_legend_body`.
        from ._legend import (_entry_columns, _inline_gradient_block_size,
                              _partition_by_group)
        label_size = _FONTSPEC["label_size"]
        sub_header_h = label_size + 4
        sub_groups = _partition_by_group(disc, lambda ae: ae[1].get("group"))
        disc_w = 0.0
        disc_h = 0.0
        for name, items in sub_groups:
            if name:
                disc_w = max(disc_w, measure_text(str(name), label_size))
                disc_h += sub_header_h
            cols = _entry_columns(items, ncols)
            block_w = sum(
                max(sw + 6 + measure_text(e["label"], tick_size) for _, e in col)
                for col in cols
            ) + (len(cols) - 1) * _LEGSPEC["column_gap"]
            disc_w = max(disc_w, block_w)
            disc_h += len(cols[0]) * row_h
        disc_h += max(0, len(sub_groups) - 1) * _LEGSPEC["section_gap"]
        cont_w, cont_h = _inline_gradient_block_size([d for _, d in cont])
        lw = max(disc_w, cont_w) + 2 * pad_x
        lh = cont_h + disc_h + 2 * pad_y
        if cont and disc:
            lh += _LEGSPEC["section_gap"]
    return {"disc": disc, "cont": cont, "lw": lw, "lh": lh,
            "horizontal": horizontal, "gradient_h": gradient_h,
            "position": pos, "ncols": ncols}


def _resolve_panel_inputs(st, *, x_scale, y_scale, dw, dh, po):
    """Resolve ticks, labels, sizes, rotations, suppress flags and hide
    flags for one panel. Shared by `_required_margin` (via
    `_chrome.label_band_sizes`) and `_render_inner` so the reservation
    and render passes walk identical numbers.

    `x_scale` / `y_scale` are caller-built: the reservation pass uses the
    per-panel descriptor (no layout coordination), the render pass uses
    `_build_xy_scales` which honors `panel_opts.x_axis` / `y_axis`. The
    rest of the resolution is identical."""
    tick_size = _FONTSPEC["tick_size"]

    # Same tick-density rule on both call sites.
    x_n = max(2, min(8, int(dw // 65)))
    y_n = max(2, min(8, int(dh // 40)))
    x_ticks = (st["x_ticks"] if st["x_ticks"] is not None
               else _auto_major_ticks(x_scale, x_n, st["x_step"], st["x_count"]))
    y_ticks = (st["y_ticks"] if st["y_ticks"] is not None
               else _auto_major_ticks(y_scale, y_n, st["y_step"], st["y_count"]))
    x_fmt = _resolve_tick_formatter(st["x_format"], x_scale)
    y_fmt = _resolve_tick_formatter(st["y_format"], y_scale)
    x_labels = (st["x_labels"] if st["x_labels"] is not None
                else [x_fmt(t) for t in x_ticks])
    y_labels = (st["y_labels"] if st["y_labels"] is not None
                else [y_fmt(t) for t in y_ticks])

    # Continuous sectors: auto ticks are meaningless on a global-offset
    # coord, so the default is none. User-supplied ticks via xticks/yticks
    # are interpreted as per-sector LOCAL positions and replicated at
    # each sector's offset.
    if st["x_sectors"] is not None and st["x_sectors"].kind == "continuous":
        x_ticks, x_labels = st["x_sectors"].expand_ticks(
            x_ticks if st["x_ticks"] is not None else [],
            x_labels if st["x_ticks"] is not None else [])
    if st["y_sectors"] is not None and st["y_sectors"].kind == "continuous":
        y_ticks, y_labels = st["y_sectors"].expand_ticks(
            y_ticks if st["y_ticks"] is not None else [],
            y_labels if st["y_ticks"] is not None else [])

    # Joined-side hide flags — drop reservations the renderer skips.
    hide_t = po.hide_top
    hide_b = po.hide_bottom
    hide_l = po.hide_left
    hide_r = po.hide_right

    # `xticks(labels=False)` joins forces with the share-pair label
    # suppression — either one drops tick labels on the corresponding
    # side. Routed by axis side so a flipped axis pulls suppression from
    # the matching joined edge (top edge for x_side="top", etc.).
    x_side = st["x_side"]
    y_side = st["y_side"]
    suppress_xt = getattr(po, f"suppress_{x_side}_labels") or not st["x_show_labels"]
    suppress_yt = getattr(po, f"suppress_{y_side}_labels") or not st["y_show_labels"]

    return SimpleNamespace(
        x_scale=x_scale, y_scale=y_scale,
        x_ticks=x_ticks, x_labels=x_labels,
        y_ticks=y_ticks, y_labels=y_labels,
        x_size=st["x_fontsize"] if st["x_fontsize"] is not None else tick_size,
        y_size=st["y_fontsize"] if st["y_fontsize"] is not None else tick_size,
        x_rot=st["x_rotation"] or 0,
        y_rot=st["y_rotation"] or 0,
        # Variant faces have their own advance widths — the margin
        # reservation must measure with the same style/weight the render
        # pass draws with.
        x_style=st["x_fontstyle"] or "normal",
        y_style=st["y_fontstyle"] or "normal",
        x_weight=st["x_fontweight"] or "normal",
        y_weight=st["y_fontweight"] or "normal",
        suppress_xt=suppress_xt, suppress_yt=suppress_yt,
        hide_t=hide_t, hide_b=hide_b, hide_l=hide_l, hide_r=hide_r,
        # Side routing pre-resolved so chrome functions don't re-derive.
        x_side=x_side, y_side=y_side,
        hide_xlabel=(x_side == "bottom" and hide_b) or (x_side == "top" and hide_t),
        hide_ylabel=(y_side == "left"   and hide_l) or (y_side == "right" and hide_r),
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
#   2. `_chrome.label_band_sizes(...)`          — pure axis band: tick marks,
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


def _required_margin(st, dw, dh, po: "_PanelOpts") -> dict:
    """Margin a body-first leaf actually needs to fit its title, axis
    labels, tick labels, and any outside-positioned in-frame legend.

    Returns a plain dict with the same keys as `_margin` — the caller
    adds this to the per-side floor. Body-first specifically: data dims
    are fixed, so tick density and labels are deterministic and the
    computation is a single pass (no chicken-and-egg with margin).

    `po` lets the formula drop reservations for content the renderer is
    going to suppress (joined share-pair sides): tick labels via
    `suppress_*_labels`, xlabel/ylabel/title via `hide_*`.

    The geometry mirrors `_render_inner`'s placement formulas — keep them
    in sync if either changes."""
    # Provisional scales at the fixed data dims — body-first means iw/ih
    # are decided up front, no iteration needed. Reservation pass uses the
    # per-panel descriptor (not the layout-coordinated one); render pass
    # picks the coordinated one via `_build_xy_scales` instead.
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
    inp = _resolve_panel_inputs(st, x_scale=x_scale, y_scale=y_scale,
                                 dw=dw, dh=dh, po=po)
    bands, _ = _chrome.label_band_sizes(st, inp, dw, dh)
    top, right, bottom, left = bands["top"], bands["right"], bands["bottom"], bands["left"]

    # Cross-side text overhang: a title / xlabel longer than `dw` is
    # centered on `iw/2`, so it sticks out past the data area on left
    # and right by `(text_w - dw) / 2`. A ylabel (rotated -90, centered
    # on `ih/2`) is the same story but vertical: text longer than `dh`
    # spills past top and bottom equally. Margins grow by the overhang
    # so the rendered text fits inside the canvas. Skip when the label
    # / title is hidden (joined side) since the renderer won't draw it.
    # Applied here (not in `_chrome.label_band_sizes`) because positioning
    # code in `_render_inner` needs the *axis band* without overhang — a
    # wide title shouldn't displace the ylabel from its natural slot.
    label_size = _FONTSPEC["label_size"]
    title_size = _FONTSPEC["title_size"]
    if st["title"]:
        title_overhang = max(0.0, (measure_text(st["title"], title_size) - dw) / 2.0)
        left  = max(left,  title_overhang)
        right = max(right, title_overhang)
    if st["subtitle"]:
        sub_overhang = max(0.0, (measure_text(st["subtitle"], _FONTSPEC["subtitle_size"]) - dw) / 2.0)
        left  = max(left,  sub_overhang)
        right = max(right, sub_overhang)
    if st["caption"]:
        # Caption band is not part of `label_band_sizes` — the bottom
        # band positions the outside-bottom legend, and the caption sits
        # past that legend (see `emit_frame_labels`). Reserve it here,
        # additively like the legend below. Anchored right at x=dw, a
        # caption wider than the data area spills left only.
        caption_size = _FONTSPEC["caption_size"]
        bottom += _PADSPEC["caption"] + text_block_height(st["caption"], caption_size)
        left = max(left, max(0.0, measure_text(st["caption"], caption_size) - dw))
    if st["xlabel"] and not inp.hide_xlabel:
        xlabel_overhang = max(0.0, (measure_text(st["xlabel"], label_size) - dw) / 2.0)
        left  = max(left,  xlabel_overhang)
        right = max(right, xlabel_overhang)
    if st["ylabel"] and not inp.hide_ylabel:
        ylabel_overhang = max(0.0, (measure_text(st["ylabel"], label_size) - dh) / 2.0)
        top    = max(top,    ylabel_overhang)
        bottom = max(bottom, ylabel_overhang)
    # Rightmost x-tick label's rotated AABB extends past x=iw by half its
    # width — a cross-axis spillover from the bottom axis. Measured in
    # `_chrome.label_band_sizes` and reported separately so an inline right
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
    leg = _inline_legend_layout(st)
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
    _margin_cobj = st.get("coordinate")
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


def _build_xy_scales(st, iw, ih, panel_opts: _PanelOpts):
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


def _figure_root_attrs() -> str:
    """Attrs for the outer `<svg>`. Every plotlet SVG carries `kind="layout"`
    — a lone chart is just a 1x1 layout, so there's no separate figure
    kind anymore."""
    return _attrs_str({
        "version": _PLOTLET_VERSION,
        "schema":  _SCHEMA_VERSION,
        "kind":    "layout",
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

def _panel_open(st, panel_opts: _PanelOpts, transform: str,
                M: dict, iw: float, ih: float,
                panel_bbox: tuple[float, float, float, float]) -> str:
    """Open a panel `<g>` with transform + structural data attrs, and emit
    any panel-level `<metadata>` children (currently x/y category lists).
    Returns a string ending mid-element — the caller appends
    `_render_inner(...)` then `</g>`."""
    x_axis = panel_opts.x_axis
    y_axis = panel_opts.y_axis
    attrs, meta = _panel_attrs_and_meta(st, M, iw, ih, x_axis, y_axis, panel_bbox)
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
    from ._legend import _entry_columns, _partition_by_group
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
        cols = _entry_columns(sub_items, ncols)
        cx = pad_x
        for col in cols:
            for i, (a, entry) in enumerate(col):
                ry = cur_y + i * row_h + row_h / 2
                parts.append(_render_discrete_entry(entry, a, ctx_for, cx, ry))
            cx += (max(sw + 6 + measure_text(e["label"], tick_size)
                       for _, e in col) + _LEGSPEC["column_gap"])
        cur_y += len(cols[0]) * row_h
        if si < len(sub_groups) - 1:
            cur_y += _LEGSPEC["section_gap"]
    return ''.join(parts)


def _render_inner(st, iw, ih, M, panel_opts: _PanelOpts, *, clip_counter):
    """Body fragment for one panel — the string appended inside the panel
    `<g>` opened by `_panel_open`. Coordinates are panel-local: data area
    at `(0,0)`→`(iw,ih)`, chrome placed relative to `M`. `panel_opts`
    supplies axis descriptors and joined-side flags. `clip_counter` is
    shared across panels so coord-clip ids stay unique in the SVG."""
    _prebin_hist(st)

    x_scale, y_scale, x_is_cat = _build_xy_scales(st, iw, ih, panel_opts)
    inp = _resolve_panel_inputs(st, x_scale=x_scale, y_scale=y_scale,
                                 dw=iw, dh=ih, po=panel_opts)
    # Label bands + raw chrome stack — both passes share the chrome dict
    # so we only compute it once per render. `label_bands` feeds the
    # inline-legend block; `chrome` feeds frame-label placement and the
    # top-legend gap below.
    label_bands, chrome = _chrome.label_band_sizes(st, inp, iw, ih)
    _x_sec = st["x_sectors"]
    _y_sec = st["y_sectors"]

    # color assignment — only color-cycle artists consume the cycle.
    # Runs before the legend harvest below: entries capture `_color` at
    # harvest time (a `legend={...}` override harvests from a *copy* of
    # the record, so later in-place stamping wouldn't reach it).
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

    # In-frame legend geometry is computed up front because a top-position
    # legend sits between the title and the data area — the title's y
    # offset depends on it. For other positions / inside / no legend, the
    # title stays at `_PADSPEC["title"]`.
    leg = _inline_legend_layout(st)
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
    _coord_object = st.get("coordinate")
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
        bad = sorted({a["type"] for a in st["artists"]
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

    if st["facecolor"] is not None:
        parts.append(rect(0, 0, iw, ih, fill=resolve_color(st["facecolor"])))

    # grid — straight Cartesian lines; suppressed when the coordinate owns
    # the x-axis (e.g. CircularCoordinate) because horizontals/verticals
    # render outside the ring after the warp would naturally apply.
    if st["grid"] and not _has_x_frame:
        gcol = _GRIDSPEC["color"]
        which = st["grid_which"]
        # Minor lines first so major lines paint on top where they meet.
        # grid(which="minor"/"both") is itself the explicit ask, so when
        # the user hasn't configured minor ticks the auto subdivisions
        # apply (ggplot behavior) — an explicit minor= list still wins.
        if which in ("minor", "both"):
            mw = _GRIDSPEC["minor_width"]; md = _GRIDSPEC["minor_dasharray"]
            if not x_is_cat:
                xm = st["x_minor"]
                for t in _chrome._resolve_minor_ticks(
                        xm if xm not in (None, False) else True,
                        x_scale, inp.x_ticks):
                    x = x_scale(t)
                    parts.append(segment(x, 0, x, ih,
                                         color=gcol, width=mw, dash=md))
            if panel_opts.y_axis.kind != "category":
                ym = st["y_minor"]
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
    for idx, a in enumerate(st["artists"]):
        spec = get_artist(a["type"])
        if spec is None: continue
        by_layer[spec.layer].append((idx, a))
    clip_data = st.get("clip", True)

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
        st=st, inp=inp, iw=iw, ih=ih,
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
        st, inp, iw, ih, chrome, top_legend_outset=top_legend_outset,
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
    insets = st.get("insets") or []
    if insets:
        parts.append(f'<svg x="0" y="0" width="{iw:.10g}" height="{ih:.10g}" overflow="hidden">')
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
        parts.append(f'<g transform="translate({coord(tx)},{coord(ty)})" '
                      f'data-plotlet-kind="inset">'
                      + rect(bg_x, bg_y, bg_w, bg_h,
                             fill=SPEC["figure"]["background"])
                      + f'{inset_svg}</g>')
    if insets:
        parts.append('</svg>')

    return "".join(parts)
