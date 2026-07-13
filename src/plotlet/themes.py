"""Visual theme registry.

A theme is a (partial) JSON file under [`plotlet/themes/`](themes/) that
overrides values in `spec.json` — the locked default look. Loading
`"dark"` deep-merges `themes/dark.json` over `spec.json` and returns the
resolved spec dict. `"classic"` is the name for *no override* — it just
returns `spec.json` as-is. The active theme is applied per-chart at
render time by `_spec.active_theme(name)` — a context manager that
mutates the inner contents of the live spec dicts (`_D`, `_FRAME`, …) so
modules importing them see the override transparently for the duration
of one render.

Public API:

  - `load_theme(name)` — return the fully resolved spec for `name`.
  - `list_themes()` — sorted list of theme names installed.
  - `register_theme(name, spec)` — register an in-memory theme (dict or
    path to a JSON file). User-defined themes never live in the package.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

_HERE = Path(__file__).parent
_SPEC_PATH = _HERE / "spec.json"
_THEME_DIR = _HERE / "themes"

# In-memory registry — populated lazily by `load_theme` and explicitly by
# `register_theme` for user-defined themes.
_RESOLVED: dict[str, dict] = {}
_USER_OVERRIDES: dict[str, dict] = {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into a copy of `base`. Override values
    win at leaf nodes; `None` is treated like any other value (so a theme
    can set `"dasharray": null` to drop the dash from gridlines).
    """
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read_theme_file(name: str) -> dict:
    path = _THEME_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(
            f"unknown theme {name!r}; available: {list_themes()}"
        )
    return json.loads(path.read_text())


def list_themes() -> list[str]:
    """Sorted list of theme names — built-ins + user-registered. `"classic"`
    is included as the name for the default (= no override on `spec.json`)."""
    builtins = ["classic"] + sorted(p.stem for p in _THEME_DIR.glob("*.json"))
    return sorted(set(builtins) | set(_USER_OVERRIDES))


def load_theme(name: str | None) -> dict:
    """Return the fully resolved spec dict for theme `name`.

    `None` and `"classic"` both return the bundled `spec.json` — that's the
    locked default; themes are partial overrides on top. Every other theme
    is `spec.json` deep-merged with the theme's overrides.
    """
    if name is None:
        name = "classic"
    if name in _RESOLVED:
        return _RESOLVED[name]
    if name == "classic":
        spec = json.loads(_SPEC_PATH.read_text())
    elif name in _USER_OVERRIDES:
        spec = _deep_merge(load_theme("classic"), _USER_OVERRIDES[name])
    else:
        spec = _deep_merge(load_theme("classic"), _read_theme_file(name))
    _RESOLVED[name] = spec
    return spec


def register_theme(name: str, override) -> None:
    """Register a user-defined theme. `override` is either a dict
    (partial — deep-merged over classic) or a `Path` / `str` pointing at
    a JSON file. After registration, `c.theme(name)` resolves it.
    """
    if isinstance(override, (str, Path)):
        override = json.loads(Path(override).read_text())
    if not isinstance(override, dict):
        raise TypeError(
            f"register_theme: override must be dict or path, got {type(override).__name__}"
        )
    _USER_OVERRIDES[name] = override
    _RESOLVED.pop(name, None)  # invalidate cache so next load merges fresh
