"""Continuous colormap registry — value in [0, 1] → (R, G, B) ints in [0, 255].

The LUT data is vendored from matplotlib via `scripts/extract_cmaps.py`.
Each entry is a 768-byte buffer (256 RGB triples). Lookup quantizes to the
nearest of 256 levels — visually indistinguishable from full interpolation
for any LUT this fine.

    cm = plotlet.colormaps.colormap("viridis")
    r, g, b = cm(0.5)        # → ints in [0, 255]
"""
from __future__ import annotations

from typing import Callable

from ._cm_data import LUTS


def colormap(name: str) -> Callable[[float], tuple[int, int, int]]:
    """Look up a colormap by name. Raises ValueError if unknown."""
    if name not in LUTS:
        raise ValueError(
            f"unknown colormap {name!r}. "
            f"Use plotlet.list_colormaps() for the full list."
        )
    lut = LUTS[name]

    def _cmap(v: float) -> tuple[int, int, int]:
        if v != v:
            return (0, 0, 0)
        if v < 0.0: v = 0.0
        elif v > 1.0: v = 1.0
        i = int(v * 255 + 0.5) * 3
        return (lut[i], lut[i + 1], lut[i + 2])

    return _cmap


def colormap_lut(name: str) -> bytes:
    """Raw 768-byte LUT for a colormap, for callers that want to index directly."""
    if name not in LUTS:
        raise ValueError(
            f"unknown colormap {name!r}. "
            f"Use plotlet.list_colormaps() for the full list."
        )
    return LUTS[name]


def list_colormaps() -> list[str]:
    """Sorted list of all registered colormap names."""
    return sorted(LUTS.keys())
