"""Font loading + text width measurement using bundled DejaVu Sans.

Glyph extraction lives here; `text_path` (the public SVG-emit primitive that
uses these helpers) is in `plotlet.draw`.
"""
from pathlib import Path

from fontTools.ttLib import TTFont

_HERE = Path(__file__).parent
_FONT_PATH = _HERE / "fonts" / "DejaVuSans.ttf"

_TTF = TTFont(str(_FONT_PATH))
_UPEM = _TTF["head"].unitsPerEm
_CMAP = _TTF.getBestCmap()
_GS = _TTF.getGlyphSet()
_ASCENT = _TTF["hhea"].ascent
_DESCENT = _TTF["hhea"].descent
# Cap height of the bundled DejaVu Sans, measured from the 'H' glyph
# bounds: 1493 / 2048 (font units / unitsPerEm). Used to convert between
# baseline anchor (where `text_path` draws) and cap-top anchor (where
# the eye perceives the top of the glyph). Replaces several hard-coded
# tick-positioning magic numbers in core.py.
_CAP_HEIGHT_RATIO = 1493 / 2048
# Descender depth (positive value, in em-fraction). Worst-case glyph
# extent below the baseline — used to place text so its descender bottom
# sits at a target pixel without clipping.
_DESCENDER_RATIO = abs(_DESCENT) / _UPEM


def _glyph(ch):
    return _GS[_CMAP.get(ord(ch), ".notdef")]


def _measure_text(s: str, size: float) -> float:
    """Exact pixel width of `s` rendered in DejaVu Sans at `size` pt."""
    if not s:
        return 0.0
    scale = size / _UPEM
    return sum(_glyph(ch).width * scale for ch in s)


def _cap_height(size: float) -> float:
    """Cap height in px for the bundled font at `size`. Equals the distance
    from baseline up to the top of a capital letter — i.e. the conversion
    between `text_path`'s baseline anchor and the visual glyph top."""
    return size * _CAP_HEIGHT_RATIO


def _descender(size: float) -> float:
    """Descender depth in px (positive) for the bundled font at `size`.
    Equals the worst-case distance baseline → glyph bottom, used to place
    text so its visible bottom edge sits at a target pixel."""
    return size * _DESCENDER_RATIO
