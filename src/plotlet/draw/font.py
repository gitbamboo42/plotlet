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


def _glyph(ch):
    return _GS[_CMAP.get(ord(ch), ".notdef")]


def _measure_text(s: str, size: float) -> float:
    """Exact pixel width of `s` rendered in DejaVu Sans at `size` pt."""
    if not s:
        return 0.0
    scale = size / _UPEM
    return sum(_glyph(ch).width * scale for ch in s)
