"""Font loading + text→SVG path conversion using bundled DejaVu Sans.

We extract glyph outlines and emit them as <path> elements rather than
<text>, so SVG renders identically on every machine regardless of installed
fonts. The same loaded font also gives us exact text-width measurement —
no `len(text) * fudge_factor` magic numbers.
"""
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.transform import Transform

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


def _text_path(s: str, x: float, y: float, size: float,
               anchor: str = "start", color: str = "#000") -> str:
    """Render `s` as a single SVG <path> with its baseline at (x, y).

    `anchor` matches SVG's text-anchor: 'start' | 'middle' | 'end'.
    Useful for tick labels (anchor='middle'), y-tick labels (anchor='end').
    """
    if not s:
        return ""
    width = _measure_text(s, size)
    if anchor == "middle":
        x0 = x - width / 2
    elif anchor == "end":
        x0 = x - width
    else:
        x0 = x
    pen = SVGPathPen(_GS)
    scale = size / _UPEM
    cx = x0
    for ch in s:
        g = _glyph(ch)
        # SVG y points down, font y points up — flip with negative scale.
        tpen = TransformPen(pen, Transform().translate(cx, y).scale(scale, -scale))
        g.draw(tpen)
        cx += g.width * scale
    return f'<path d="{pen.getCommands()}" fill="{color}"/>'
