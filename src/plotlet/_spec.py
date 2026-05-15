"""Visual spec — loaded from `spec.json` at import time. Internal.

The spec is the locked visual contract: colors, fonts, sizes, default alphas,
legend dimensions. Submodules read from here to avoid hardcoding literals.

`SPEC` and the per-section handles (`_D`, `_FRAME`, …) are *live dicts*:
when a chart's `theme=` is applied, [`active_theme(name)`](#active_theme)
mutates the inner contents of these dicts so every module sees the
override without an import-time refactor. The previous contents are
restored when the context exits.
"""
from __future__ import annotations

import contextlib
import copy

from .themes import load_theme


def _install(target, source) -> None:
    """Replace `target`'s contents with `source`'s, preserving identity of
    nested mutable containers (dicts AND lists). Used to swap themes
    without breaking references that other modules captured at import
    time via `from ._spec import _D, _TAB10, _COLOR_NAMES`. Nested dicts
    and lists that exist on both sides are recursed into so their
    identity survives; mismatched-type or absent-on-target values are
    deep-copied wholesale.
    """
    if isinstance(target, dict) and isinstance(source, dict):
        for k in list(target.keys()):
            if k not in source:
                del target[k]
        for k, v in source.items():
            existing = target.get(k)
            if isinstance(v, dict) and isinstance(existing, dict):
                _install(existing, v)
            elif isinstance(v, list) and isinstance(existing, list):
                _install(existing, v)
            else:
                target[k] = copy.deepcopy(v)
    elif isinstance(target, list) and isinstance(source, list):
        target.clear()
        target.extend(copy.deepcopy(item) for item in source)


# Initialize from the locked default theme. Every module that imports
# `_D`, `_FRAME`, … gets a reference to one of these dicts; their
# contents change when `active_theme(name)` is in effect.
SPEC: dict = {}
_install(SPEC, load_theme("classic"))

_TAB10 = SPEC["colors"]["tab10"]
_COLOR_NAMES = SPEC["colors"]["named"]
_DASH = SPEC["linestyles"]
_D = SPEC["defaults"]
_FRAME = SPEC["frame"]
_GRIDSPEC = SPEC["grid"]
_FONTSPEC = SPEC["font"]
_LEGSPEC = SPEC["legend"]
_SIZESPEC = SPEC["size"]
_MARGIN_FLOOR = SPEC["size"]["margin_floor"]
_LAYOUTSPEC = SPEC["layout"]
_FIGSPEC = SPEC["figure"]

_CURRENT_THEME: str = "classic"


def current_theme() -> str:
    """Name of the theme currently installed in the spec dicts."""
    return _CURRENT_THEME


def _swap_to(name: str) -> dict:
    """Install theme `name` into the live spec dicts; return the previous
    full SPEC snapshot for later restoration. `_install` recurses into
    nested dicts and lists, so module-level handles at any depth
    (`_FRAME`, `_TAB10`, `_MARGIN_FLOOR`, …) keep their identity."""
    global _CURRENT_THEME
    snapshot = copy.deepcopy(SPEC)
    prev_theme = _CURRENT_THEME
    _install(SPEC, load_theme(name))
    _CURRENT_THEME = name
    return {"spec": snapshot, "theme": prev_theme}


def _restore(snapshot: dict) -> None:
    global _CURRENT_THEME
    _install(SPEC, snapshot["spec"])
    _CURRENT_THEME = snapshot["theme"]


@contextlib.contextmanager
def active_theme(name: str | None):
    """Apply theme `name` to the live spec dicts for the duration of the
    `with` block. `None` is a passthrough — used by code paths that
    haven't decided a theme yet (e.g. parent rendering before walking
    into a leaf that may set its own).
    """
    if name is None or name == _CURRENT_THEME:
        yield
        return
    snapshot = _swap_to(name)
    try:
        yield
    finally:
        _restore(snapshot)
