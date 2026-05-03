"""Artist registry — the extension point.

Every plot type (built-in or user-added) is an `ArtistSpec` registered here.
A spec bundles the four things `_render` needs to know about a plot type:

  - `record(args, kwargs) -> dict`
        Convert positional/keyword args from the recorder into the artist
        dict that gets stored in `Figure._calls`. Pure data — no scales yet.

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
    legend_swatch: Callable[[dict, "RenderContext", float, float], str] | None = None
    legend_gradient: Callable[[dict], dict | None] | None = None


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
