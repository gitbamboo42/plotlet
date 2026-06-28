"""Artist registry — the extension point.

Every plot type (built-in or user-added) is an `ArtistSpec` registered here.
A spec bundles the four things `_render` needs to know about a plot type:

  - `record(args, kwargs) -> dict`
        Convert positional/keyword args from the recorder into the artist
        dict that gets stored in `Chart._calls`. Pure data — no scales yet.
        `args` and `kwargs` are fresh copies on every render, so it's safe
        for `record` to `kwargs.pop(...)` or otherwise mutate them.

  - `xdomain(artist) -> Iterable[float] | None` / `ydomain(...)`
        Yield numeric values that should participate in autoscaling on each
        axis. Return `None` if this artist doesn't constrain that axis
        (e.g. axhline doesn't constrain x).

  - `draw(artist, ctx) -> str`
        Emit the SVG fragment for this artist. `ctx` carries everything the
        artist might need: x_scale, y_scale, iw, ih, color, defaults.

  - `layer`: one of "background" | "data" | "foreground"
        Render order. Spans are drawn first, normal data next, reflines last.

  - `uses_color_cycle`: bool
        Whether this artist consumes the next tab10 color (True for
        plot/scatter/bar/etc, False for axhline/axvline/imshow).

  - `data_attrs(artist) -> dict | None` (optional, 0.3.0+)
        Type-specific structural attrs for the AI-readable schema. Returned
        keys land on the artist's wrapper `<g>` as `data-plotlet-<key>`.
        Common attrs (type, index, label, color) are added by the wrapper —
        each artist contributes only its own fields (n, x-min, marker, …).

  - `axis_order(artist) -> dict | None` (optional)
        Contribute a canonical order for a categorical axis. Returns
        `{"x": [...]}` or `{"y": [...]}`. Used by artists like dendrogram
        whose leaf order is non-alphabetical and load-bearing. The user's
        explicit `xscale("category", order=...)` still wins.

  - `frame_defaults(args, kwargs) -> list[tuple] | None` (optional)
        Return a list of `(call_name, args, kwargs)` to record *before*
        the artist itself. Used by artists with strong conventional
        defaults (e.g. dendrogram hides all spines). User calls made
        after the artist still win — replay is in order.

`add_artist(name, ...)` is the public extension API. After calling it, users
can do `fig.<name>(...)` and it Just Works.
"""
from __future__ import annotations

import html
import inspect
from dataclasses import MISSING, dataclass, field, fields
from typing import Any, Callable, Iterable


@dataclass
class ArtistSpec:
    name: str
    record: Callable[[list, dict], dict]
    draw: Callable[[dict, "RenderContext"], str]
    xdomain: Callable[[dict], Iterable[float] | None] = lambda a: None
    ydomain: Callable[[dict], Iterable[float] | None] = lambda a: None
    layer: str = "data"  # "background" | "data" | "foreground"
    uses_color_cycle: bool = True
    default_color: str | None = None  # used when uses_color_cycle is False
    # Sugar for `c.<artist>(df, x="col", y="col")` → `c.<artist>(data=df, ...)`.
    # Disable on positional-only artists (matrix or single primary input) so
    # the lone positional arg isn't hoisted into `kw["data"]`.
    accepts_data_positional: bool = True
    # Returns a list of legend-entry dicts:
    #   {"label": str, "color": str, "alpha"?: float, "group"?: str,
    #    "paint"?: callable, "_a"?: dict}
    # `group` clusters entries under one header (multi-aesthetic guides).
    # `paint(a, ctx, x0, y_mid) -> str` overrides the default rect swatch;
    # `_a` is auto-attached so paint functions can read the recorded artist.
    legend_entries: Callable[[dict], list[dict]] | None = None
    legend_gradient: Callable[[dict], dict | None] | None = None
    data_attrs: Callable[[dict], dict | None] | None = None
    flips_y_axis: Callable[[dict], bool] | None = None
    tight_domain: bool = False
    # When the artist contributes to autoscaling and data lo > 0, push lo to
    # 0 so the visual sits on the baseline; also suppresses the default
    # `expand` on that side. May be a `(artist_dict) -> bool` callable so e.g.
    # a horizontal bar can force zero on x instead of y.
    force_zero_x: bool | Callable[[dict], bool] = False
    force_zero_y: bool | Callable[[dict], bool] = False
    axis_order: Callable[[dict], dict | None] | None = None
    frame_defaults: Callable[[list, dict], list | None] | None = None
    # Set True for artists whose geometry spans sector boundaries
    # (chord_links, future cross-sector ribbons). The chrome render
    # suppresses the inter-sector divider walls when any active artist
    # has this set — walls cutting through a cross-sector curve read
    # as a layering bug. Sector *labels* still render (they tell the
    # reader which sector is which).
    crosses_sectors: bool = False


@dataclass
class RenderContext:
    """Everything an artist's draw() function might need."""
    x_scale: Any
    y_scale: Any
    iw: float
    ih: float
    color: str | None
    defaults: dict
    dash: dict
    # Set by c.coordinate(...) for non-affine coords. None for Cartesian and
    # for affine coords (handled by svg_transform).
    #   project(t, r)    -> (px, py)  data-space → canvas-pixel
    #   warp(x_px, y_px) -> (px, py)  pre-warp Cartesian pixel → canvas-pixel
    # Artists opted-in to a non-affine coord via `declare_coord_support`
    # pass `warp` to `draw.*` helpers via `project=` so segments subdivide,
    # polygons curve, and markers land correctly.
    project: Any = None
    warp: Any = None


_REGISTRY: dict[str, ArtistSpec] = {}
# Parallel to _REGISTRY; auto-stamped by add_artist via stack-frame lookup.
# Surfaced by artist_table() so users can tell core/extension/user-added apart.
_ORIGINS: dict[str, str] = {}
# Maps coord short-name → set of artist names that render correctly under it.
# Populated by `declare_coord_support`; the per-coord block typically lives
# next to the coord class definition (or at the end of an extension module
# for extension artists). Queried by the renderer's gate and by
# `artist_table()` to surface the per-artist coord support set.
_COORD_SUPPORT: dict[str, set[str]] = {}


def declare_coord_support(coord_name: str, artist_names) -> None:
    """Register that `artist_names` render correctly under coord
    `coord_name` (e.g. `"Circular"` for `CircularCoordinate`).

    No upfront validation of artist names — declarations accumulate at
    import time and may run before or after the artists' `add_artist`
    calls. Missing names surface at render time via the normal coord
    gate error message."""
    _COORD_SUPPORT.setdefault(coord_name, set()).update(artist_names)


def add_artist(spec: ArtistSpec) -> None:
    """Register a plot type. Overwrites if the name already exists.

    If the artist also renders correctly under a non-affine coord, call
    ``declare_coord_support(coord_name, [spec.name])`` after this — core
    artists' opt-in lives next to the coord class definition; extension
    artists' opt-in lives right after their own ``add_artist`` call."""
    _REGISTRY[spec.name] = spec
    frame = inspect.currentframe()
    caller = frame.f_back if frame is not None else None
    mod = caller.f_globals.get("__name__", "") if caller is not None else ""
    if mod.startswith("plotlet.artists"):
        origin = "core"
    elif mod.startswith("plotlet.extensions"):
        origin = "extension"
    else:
        origin = "user"
    _ORIGINS[spec.name] = origin


def get_artist(name: str) -> ArtistSpec | None:
    return _REGISTRY.get(name)


def all_artist_names() -> list[str]:
    return list(_REGISTRY.keys())


# Curated quick-scan view. Everything else is derived live from ArtistSpec.
_DEFAULT_COLUMNS: list[str] = ["name", "origin", "layer", "coord_systems"]


def _all_columns() -> list[str]:
    # Derived from ArtistSpec so new fields auto-surface in `columns="all"`.
    # Skip fields that always render as "fn" (uninformative): required
    # callables (record/draw) and ones with a callable default
    # (xdomain/ydomain). Optional callables with `default=None` (e.g.
    # legend_entries) pass through — their fn/- state varies per artist.
    # `coord_systems` is appended separately because it's not a spec field —
    # it's derived from `_COORD_SUPPORT` at table-build time.
    cols = ["name", "origin"]
    for f in fields(ArtistSpec):
        if f.name == "name":
            continue
        if f.default is MISSING and f.default_factory is MISSING:
            continue
        if callable(f.default):
            continue
        cols.append(f.name)
    cols.append("coord_systems")
    return cols


def _cell(value) -> str:
    # Callables → "fn" (raw repr is a memory address); None → "-" so the
    # column doesn't shout "None None None". Sets of strings render as
    # `{Circular}` (sorted, no quotes); empty set → "-" (same nothing-here
    # placeholder as None). Everything else verbatim so the rendered cell
    # matches the row dict.
    if value is None:
        return "-"
    if isinstance(value, (set, frozenset)):
        if not value:
            return "-"
        if all(isinstance(v, str) for v in value):
            return "{" + ", ".join(sorted(value)) + "}"
    if callable(value):
        return "fn"
    return str(value)


class ArtistTable(list):
    """Per-artist snapshot of the registry. Iterates as a list of dicts
    carrying the **full** field set; ``__repr__`` / ``_repr_html_`` only
    display the columns selected at build time. Build via
    ``artist_table(columns=...)``."""

    def __init__(self, rows, columns=None):
        super().__init__(rows)
        if columns == "all":
            self._columns = _all_columns()
        elif columns is None:
            self._columns = list(_DEFAULT_COLUMNS)
        else:
            self._columns = list(columns)

    def __repr__(self) -> str:
        widths = []
        for key in self._columns:
            w = len(key)
            for row in self:
                w = max(w, len(_cell(row[key])))
            widths.append(w)
        fmt = "  ".join(f"{{:<{w}}}" for w in widths)
        lines = [fmt.format(*self._columns)]
        for row in self:
            lines.append(fmt.format(*(_cell(row[k]) for k in self._columns)))
        return "\n".join(lines)

    def _repr_html_(self) -> str:
        head = "".join(f"<th>{html.escape(k)}</th>" for k in self._columns)
        body_rows = []
        for row in self:
            cells = "".join(f"<td>{html.escape(_cell(row[k]))}</td>"
                            for k in self._columns)
            body_rows.append(f"<tr>{cells}</tr>")
        return (f"<table><thead><tr>{head}</tr></thead>"
                f"<tbody>{''.join(body_rows)}</tbody></table>")


def artist_table(columns=None) -> ArtistTable:
    """Snapshot of currently-registered artists.

    ``columns`` selects display: ``None`` (default) shows
    ``_DEFAULT_COLUMNS``; ``"all"`` shows every optional ArtistSpec field
    (skipping the four required plumbing callables); a list picks
    columns explicitly in the given order. Row dicts carry the **full**
    field set regardless, so programmatic filtering works on everything::

        [r for r in pt.artist_table() if r['layer'] == 'foreground']

    Origin is ``core`` (``plotlet.artists.*``), ``extension``
    (``plotlet.extensions.*``), or ``user``, auto-stamped at
    ``add_artist`` time. Re-built on each call, so artists registered
    after import are picked up."""
    rows = []
    for name in sorted(_REGISTRY.keys()):
        spec = _REGISTRY[name]
        row = {"origin": _ORIGINS.get(name, "unknown")}
        for f in fields(ArtistSpec):
            row[f.name] = getattr(spec, f.name)
        row["coord_systems"] = {c for c, a in _COORD_SUPPORT.items() if name in a}
        rows.append(row)
    return ArtistTable(rows, columns=columns)
