"""Region sink — chrome bbox capture during render.

Why this exists: pixels detect visual quality but not geometric problems
(title clipped, legend over data, tick labels overlapping). The sink
captures the bboxes of *chrome* elements — title, axis labels, ticks,
legend, panel rect — during render so consumers (`chart.regions()`,
`pt.layout_diagram(...)`'s chrome overlay, overflow tests) can check
overlap / clipping deterministically.

Scope = **chrome, not data marks.** A scatter with 10k points should not
produce 10k region entries. Data is the user's job; chrome is plotlet's.
The mechanism enforces this:

  * Primitives in `draw/primitives.py` take an optional `tag=` kwarg.
    When set, the primitive records its bbox under that name. When
    unset (the default), nothing is recorded — so artist `draw()`
    bodies, which never pass `tag=`, produce no regions for free.
  * Central code (`render/_chrome.py`, `render/emit.py`,
    `render/_legend.py`)
    passes `tag="title"` /
    `"spine"` / `"tick-x"` / `"legend-text"` etc. at the chrome
    emission sites. The tag is right there in the call, grep-able,
    no contextvar magic.
  * For chrome that has no `draw.*` call to wrap (the panel
    boundary, the canonical legend swatch), central code calls
    `_regions.record(...)` directly with an explicit `name=`.

`translate(dx, dy)` is a separate context manager: it pushes coordinate
offsets onto the sink so panel-local recordings land in outer-SVG
coords. This stays a ctxmgr because it wraps multi-call blocks (a whole
panel's emission, the inline-legend body, etc.) — using a kwarg per
primitive would be much worse.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class Region:
    """One captured chrome element. `bbox` is (x, y, w, h) in outer-SVG
    coords after the sink's translate stack has been applied. `name` is
    the semantic tag the central code attached (`"title"`, `"tick-x"`,
    `"legend-mark"`, ...)."""
    kind: str
    bbox: tuple[float, float, float, float]
    name: str
    meta: dict = field(default_factory=dict)


@dataclass
class _Sink:
    regions: list[Region] = field(default_factory=list)
    # Per-panel translate offsets, pushed by central rendering code
    # before each panel's body emits. The sink applies the cumulative
    # offset to recorded bboxes so consumers receive outer-SVG coords
    # regardless of whether the chart is single- or multi-panel.
    translate_stack: list[tuple[float, float]] = field(default_factory=list)

    def _offset(self) -> tuple[float, float]:
        dx = dy = 0.0
        for tx, ty in self.translate_stack:
            dx += tx
            dy += ty
        return dx, dy

    def record(self, kind: str, bbox, *, name: str, **meta) -> None:
        dx, dy = self._offset()
        x, y, w, h = bbox
        # Rotated text and other non-axis-aligned shapes ship a precise
        # `polygon` (list of (x, y) corners) alongside the AABB. Shift
        # those corners by the same translate so they stay in sync with
        # the bbox in outer-SVG coords.
        if "polygon" in meta:
            meta["polygon"] = [(px + dx, py + dy) for px, py in meta["polygon"]]
        self.regions.append(Region(kind=kind, bbox=(x + dx, y + dy, w, h),
                                   name=name, meta=meta))


_CURRENT: contextvars.ContextVar = contextvars.ContextVar(
    "plotlet_region_sink", default=None
)


def record(kind: str, bbox, *, name: str, **meta) -> None:
    """Record a region into the active sink, if any. Called by
    `draw.*` primitives when they receive a `tag=` kwarg, and by
    central code (`render/_chrome.py`, `render/emit.py`,
    `render/_legend.py`)
    for chrome that has no
    primitive call to wrap (panel boundary, canonical legend swatch).
    No-op when no sink is active — the common render path."""
    sink = _CURRENT.get()
    if sink is not None:
        sink.record(kind, bbox, name=name, **meta)


@contextmanager
def collecting():
    """Activate a fresh sink for the duration of the block. Yields the
    sink so the caller can read `.regions` after the block exits."""
    sink = _Sink()
    token = _CURRENT.set(sink)
    try:
        yield sink
    finally:
        _CURRENT.reset(token)


def active() -> bool:
    """True when a sink is collecting — lets central code skip work
    (e.g. a regions-only re-render) on the common no-sink path."""
    return _CURRENT.get() is not None


@contextmanager
def suppressed():
    """Deactivate any active sink for the duration. Used for renders
    whose emission is measurement-only (an inset's first pass, run to
    learn its margins) so their regions don't land at the wrong
    offset."""
    token = _CURRENT.set(None)
    try:
        yield
    finally:
        _CURRENT.reset(token)


@contextmanager
def translate(dx: float, dy: float):
    """Push a translate offset onto the sink's transform stack for the
    duration of the block. Bboxes recorded inside the block land in the
    outer-SVG frame (every push contributes to the cumulative offset).
    Called by central rendering code wrapping each panel's body so
    panel-local coords become outer-SVG coords without per-artist work.
    No-op when no sink is active."""
    sink = _CURRENT.get()
    if sink is None:
        yield
        return
    sink.translate_stack.append((dx, dy))
    try:
        yield
    finally:
        sink.translate_stack.pop()
