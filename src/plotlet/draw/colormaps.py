"""Continuous colormap registry — value in [0, 1] → (R, G, B) ints in [0, 255].

The vendored LUT data comes from matplotlib via `scripts/extract_cmaps.py`;
`register_colormap` adds user-defined entries in the same format. Each
entry is a 768-byte buffer (256 RGB triples). Lookup quantizes to the
nearest of 256 levels — visually indistinguishable from full interpolation
for any LUT this fine.

    cm = plotlet.colormaps.colormap("viridis")
    r, g, b = cm(0.5)        # → ints in [0, 255]
"""
from __future__ import annotations

import math
from typing import Callable

from ._cm_data import LUTS

# User-registered colormaps, keyed like LUTS. Per-process and explicit —
# same contract as themes._USER_OVERRIDES: a journal that names a user
# colormap re-renders elsewhere only after the same register_colormap call.
_USER_LUTS: dict[str, bytes] = {}


def _lut(name: str) -> bytes | None:
    if name in _USER_LUTS:
        return _USER_LUTS[name]
    return LUTS.get(name)


def colormap(name: str) -> Callable[[float], tuple[int, int, int]]:
    """Look up a colormap by name. Raises ValueError if unknown."""
    lut = _lut(name)
    if lut is None:
        raise ValueError(
            f"unknown colormap {name!r}. "
            f"Use plotlet.list_colormaps() for the full list, or "
            f"plotlet.register_colormap() to define one."
        )

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
    lut = _lut(name)
    if lut is None:
        raise ValueError(
            f"unknown colormap {name!r}. "
            f"Use plotlet.list_colormaps() for the full list, or "
            f"plotlet.register_colormap() to define one."
        )
    return lut


def list_colormaps() -> list[str]:
    """Sorted list of all registered colormap names."""
    return sorted({**LUTS, **_USER_LUTS})


def _parse_rgb(c) -> tuple[int, int, int]:
    from .colors import resolve_color
    from ._css_colors import CSS_COLORS
    s = resolve_color(c)
    # resolve_color passes CSS names through verbatim (SVG renders them
    # natively); interpolation needs numeric RGB, so reduce them here.
    # Plotlet names win over CSS ("red" is the tab10 red, as when drawing).
    if isinstance(s, str) and not s.startswith("#"):
        s = CSS_COLORS.get(s.lower(), s)
    if isinstance(s, str) and s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) == 6:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    raise ValueError(
        f"register_colormap: can't interpolate color {c!r} — use '#rrggbb' "
        f"hex, an (r, g, b) tuple of floats in [0, 1], a named plotlet "
        f"color ('blue', 'C0', ...), or a CSS color name ('white', ...)."
    )


def register_colormap(name: str, colors, stops=None) -> None:
    """Register a continuous colormap interpolated from a list of colors.

    Colors are spaced evenly along [0, 1], or at explicit `stops`
    (same length as `colors`, strictly increasing, from 0 to 1), and
    interpolated linearly in RGB. The reversed variant `name + '_r'` is
    registered alongside. After registration the name works everywhere a
    built-in does: `cmap=` kwargs, colorbars, `palette(name, n)`.

    Anchoring the midpoint at a data value is the norm's job, not the
    colormap's — pair with `center=` on the artist:

        pt.register_colormap("bwr2", ["#2166ac", "white", "#b2182b"])
        c.add_heatmap(..., cmap="bwr2", center=0)

    Re-registering a user name overwrites it; built-in names can't be
    shadowed. Registration is per-process (same contract as
    `register_theme`) — a serialized journal that names a user colormap
    needs the same call before re-rendering in a fresh process.
    """
    if not isinstance(name, str) or not name:
        raise ValueError("register_colormap: name must be a non-empty string")
    if name.endswith("_r"):
        raise ValueError(
            f"register_colormap: {name!r} — the '_r' suffix is reserved; "
            f"registering {name[:-2]!r} also registers its reversed variant."
        )
    if name in LUTS or name + "_r" in LUTS:
        raise ValueError(
            f"register_colormap: {name!r} is a built-in colormap and "
            f"can't be overridden — pick another name."
        )
    rgb = [_parse_rgb(c) for c in colors]
    if len(rgb) < 2:
        raise ValueError("register_colormap: need at least 2 colors")
    if stops is None:
        stops = [i / (len(rgb) - 1) for i in range(len(rgb))]
    else:
        stops = [float(s) for s in stops]
        if len(stops) != len(rgb):
            raise ValueError(
                f"register_colormap: {len(stops)} stops for {len(rgb)} colors"
            )
        if stops[0] != 0.0 or stops[-1] != 1.0:
            raise ValueError("register_colormap: stops must start at 0 and end at 1")
        if any(b <= a for a, b in zip(stops, stops[1:])):
            raise ValueError("register_colormap: stops must be strictly increasing")

    lut = bytearray(768)
    k = 0
    for i in range(256):
        t = i / 255.0
        while k < len(stops) - 2 and t > stops[k + 1]:
            k += 1
        u = (t - stops[k]) / (stops[k + 1] - stops[k])
        if u < 0.0: u = 0.0
        elif u > 1.0: u = 1.0
        for ch in range(3):
            a = rgb[k][ch]
            lut[3 * i + ch] = round(a + (rgb[k + 1][ch] - a) * u)

    rev = bytearray(768)
    for i in range(256):
        j = 3 * (255 - i)
        rev[3 * i:3 * i + 3] = lut[j:j + 3]
    _USER_LUTS[name] = bytes(lut)
    _USER_LUTS[name + "_r"] = bytes(rev)


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
