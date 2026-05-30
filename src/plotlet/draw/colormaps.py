"""Continuous colormap registry — value in [0, 1] → (R, G, B) ints in [0, 255].

The LUT data is vendored from matplotlib via `scripts/extract_cmaps.py`.
Each entry is a 768-byte buffer (256 RGB triples). Lookup quantizes to the
nearest of 256 levels — visually indistinguishable from full interpolation
for any LUT this fine.

    cm = plotlet.colormaps.colormap("viridis")
    r, g, b = cm(0.5)        # → ints in [0, 255]
"""
from __future__ import annotations

import math
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


# ---------------------------------------------------------------------------
# Continuous norm — value → unit interval [0, 1], for color lookup.
#
# Three modes:
#   linear (default)        — t = (v - vmin) / (vmax - vmin)
#   log                     — t = (log v - log vmin) / (log vmax - log vmin)
#   center=c (TwoSlopeNorm) — piecewise: vmin..c maps to [0, 0.5];
#                              c..vmax maps to [0.5, 1]. Symmetric around c
#                              even when |vmin - c| != |vmax - c|.
#
# Used by imshow for cell coloring and by the layout-level legend for
# tick positioning on the gradient strip.
# ---------------------------------------------------------------------------

class ContinuousNorm:
    def __init__(self, vmin: float, vmax: float,
                 kind: str = "linear", center: float | None = None):
        if kind == "log" and (vmin <= 0 or vmax <= 0):
            raise ValueError(
                f"norm='log' requires strictly positive vmin and vmax "
                f"(got vmin={vmin}, vmax={vmax}). Filter or shift the data, "
                f"or set vmin=/vmax= explicitly to a positive range."
            )
        if kind not in ("linear", "log"):
            raise ValueError(f"unknown norm {kind!r}; use 'linear' or 'log'")
        self.vmin = float(vmin)
        self.vmax = float(vmax)
        self.kind = kind
        self.center = None if center is None else float(center)

    def to_unit(self, v: float) -> float:
        if v != v:
            return float("nan")
        if self.kind == "log":
            if v <= 0:
                return 0.0
            l0 = math.log10(self.vmin); l1 = math.log10(self.vmax)
            t = (math.log10(v) - l0) / (l1 - l0) if l1 != l0 else 0.0
        elif self.center is not None:
            c = self.center
            if v <= c:
                t = 0.5 * (v - self.vmin) / (c - self.vmin) if c != self.vmin else 0.0
            else:
                t = 0.5 + 0.5 * (v - c) / (self.vmax - c) if self.vmax != c else 1.0
        else:
            span = (self.vmax - self.vmin) or 1.0
            t = (v - self.vmin) / span
        if t < 0.0: return 0.0
        if t > 1.0: return 1.0
        return t

    def ticks(self, n: int = 8) -> list[float]:
        from ..scales import _LogScale, _nice_ticks
        if self.kind == "log":
            return _LogScale(self.vmin, self.vmax, 0, 1).ticks(n)
        ticks = _nice_ticks(self.vmin, self.vmax, n)
        if self.center is not None and self.vmin <= self.center <= self.vmax:
            if not any(abs(t - self.center) < 1e-12 for t in ticks):
                ticks = sorted(ticks + [self.center])
        return ticks
