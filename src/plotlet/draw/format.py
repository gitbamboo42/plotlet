"""Numeric formatters for SVG attribute emission.

One semantic per helper; each helper owns the precision its field needs.
All SVG-emitting code calls these instead of inlining ``f"{v:.2f}"``, so
precision policy lives in one place. Changing how coordinates are
serialized is a one-file edit here — not a 100-site sweep.
"""
from __future__ import annotations


def coord(v: float) -> str:
    """Pixel coordinate or length: x/y/cx/cy/r/width/height/dx/dy/etc.

    Sub-pixel precision (the second decimal) is below human acuity but
    drives byte-identical reproducibility — kept so refactors that change
    geometry by ≥ 0.01 px get caught by baseline tests."""
    return f"{v:.2f}"


def stroke_w(v: float) -> str:
    """Stroke width in px. Typical values are 0.5/1/1.5/2, so 2 decimals
    preserves the common fractional widths exactly."""
    return f"{v:.2f}"


def opacity(v: float) -> str:
    """0..1 opacity (``opacity``, ``fill-opacity``, ``stroke-opacity``).
    Two decimals = 1% steps — coarser would be visibly chunky."""
    return f"{v:.2f}"


def degree(v: float) -> str:
    """Rotation angle in degrees. One decimal is fine for normal use."""
    return f"{v:.2f}"
