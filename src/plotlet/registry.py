"""Artist registry — the extension point.

Every plot type (built-in or user-added) is an `ArtistSpec` registered here.
A spec bundles the four things `_render` needs to know about a plot type:

  - `record(args, kwargs) -> dict`
        Convert positional/keyword args from the recorder into the artist
        dict that gets stored in `Chart._calls`. Pure data — no scales yet.

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

from dataclasses import dataclass, field
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
    # Each entry: {"label": str, "color": str, "paint"?: callable, "_a"?: dict}
    # `paint(a, ctx, x0, y_mid) -> str` is optional; default is a colored rect
    # swatch using entry["color"]. `_a` is auto-attached by the harvester so
    # paint functions have the original recorded artist for context (linewidth,
    # alpha, marker kind, etc.).
    legend_entries: Callable[[dict], list[dict]] | None = None
    legend_gradient: Callable[[dict], dict | None] | None = None
    data_attrs: Callable[[dict], dict | None] | None = None
    flips_y_axis: Callable[[dict], bool] | None = None
    tight_domain: bool = False
    # Anchor an axis to zero: when the artist contributes to autoscaling and
    # data lo > 0, push lo down to 0 so the visual sits on the baseline. Also
    # suppresses the default `expand` on that side so bars don't float below
    # zero. Built-in `bar` and `hist` set `force_zero_y=True`; recipes that
    # implement bar-like artists (numeric_bar, horizontal_bar, ...) opt in.
    force_zero_x: bool = False
    force_zero_y: bool = False
    axis_order: Callable[[dict], dict | None] | None = None
    frame_defaults: Callable[[list, dict], list | None] | None = None


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


_REGISTRY: dict[str, ArtistSpec] = {}


def add_artist(spec: ArtistSpec) -> None:
    """Register a plot type. Overwrites if the name already exists."""
    _REGISTRY[spec.name] = spec


def get_artist(name: str) -> ArtistSpec | None:
    return _REGISTRY.get(name)


def all_artist_names() -> list[str]:
    return list(_REGISTRY.keys())
