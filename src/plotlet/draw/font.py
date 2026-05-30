"""Font loading + glyph-to-path rendering using bundled DejaVu Sans.

Owns the full text → SVG-path pipeline: glyph lookup, width measurement,
italic synthesis. `text_path` in `plotlet.draw` is a thin wrapper that
adds the SVG `<path fill=...>` element around the path data produced here.
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

# DejaVu Sans ships no italic variant; the official DejaVu Sans Oblique is
# itself a synthesized skew. Match matplotlib's approach: tilt the upright
# font at render time by -12° (skewX) when `fontstyle="italic"`.
_ITALIC_SKEW_RAD = -0.20943951023931953  # math.radians(-12)
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


def measure_text(s: str, size: float) -> float:
    """Exact pixel width of `s` rendered in DejaVu Sans at `size` pt."""
    if not s:
        return 0.0
    scale = size / _UPEM
    return sum(_glyph(ch).width * scale for ch in s)


def cap_height(size: float) -> float:
    """Cap height in px for the bundled font at `size`. Equals the distance
    from baseline up to the top of a capital letter — i.e. the conversion
    between `text_path`'s baseline anchor and the visual glyph top."""
    return size * _CAP_HEIGHT_RATIO


def descender(size: float) -> float:
    """Descender depth in px (positive) for the bundled font at `size`.
    Equals the worst-case distance baseline → glyph bottom, used to place
    text so its visible bottom edge sits at a target pixel."""
    return size * _DESCENDER_RATIO


def _glyph_path_d(s: str, x: float, y: float, size: float,
                  anchor: str = "start", fontstyle: str = "normal") -> str:
    """Build the SVG `d` attribute for `s` rendered at baseline (x, y).

    `anchor` matches SVG's text-anchor ('start' | 'middle' | 'end');
    `fontstyle="italic"` applies the synthetic oblique skew."""
    if not s:
        return ""
    width = measure_text(s, size)
    if anchor == "middle":
        x0 = x - width / 2
    elif anchor == "end":
        x0 = x - width
    else:
        x0 = x
    pen = SVGPathPen(_GS)
    scale = size / _UPEM
    cx = x0
    italic = (fontstyle == "italic")
    for ch in s:
        g = _glyph(ch)
        # SVG y points down, font y points up — flip with negative scale.
        # Italic: skewX applied before the y-flip+scale so the slant lives
        # in the post-scale (screen) frame; top of glyph leans right.
        t = Transform().translate(cx, y).scale(scale, -scale)
        if italic:
            t = t.skew(_ITALIC_SKEW_RAD, 0)
        tpen = TransformPen(pen, t)
        g.draw(tpen)
        cx += g.width * scale
    return pen.getCommands()


_DECORATION_KINDS = ("underline", "overline", "line-through")


def _decoration_y_offset(decoration: str, size: float) -> float:
    """Vertical offset (relative to baseline, in SVG-y-down) for a
    text-decoration line at the given font size."""
    if decoration == "underline":
        # Sits just below the baseline, in the descender region.
        return size * 0.12
    if decoration == "line-through":
        # Middle of cap-height (visually crosses the x-height of glyphs).
        return -size * _CAP_HEIGHT_RATIO / 2
    if decoration == "overline":
        # Just above the cap.
        return -size * _CAP_HEIGHT_RATIO - size * 0.06
    raise ValueError(
        f"unknown decoration={decoration!r}; "
        f"expected one of {_DECORATION_KINDS} or 'none'."
    )
