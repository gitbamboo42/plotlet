"""Font loading + glyph-to-path rendering using bundled DejaVu Sans.

Owns the full text → SVG-path pipeline: glyph lookup, width measurement,
italic synthesis. `text_path` in `plotlet.draw` is a thin wrapper that
adds the SVG `<path fill=...>` element around the path data produced here.
"""
import math
import re
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.transform import Transform
from .._spec import _FONTSPEC
from .format import coord


_HERE = Path(__file__).parent
_FONT_PATH = _HERE / "fonts" / "DejaVuSans.ttf"

_TTF = TTFont(str(_FONT_PATH))
_UPEM = _TTF["head"].unitsPerEm
_CMAP = _TTF.getBestCmap()
_GS = _TTF.getGlyphSet()
_ASCENT = _TTF["hhea"].ascent
_DESCENT = _TTF["hhea"].descent

# DejaVu Sans ships no italic variant; the official DejaVu Sans Oblique
# is itself a synthesized skew. We do the same: tilt the upright font at
# render time by -12° (skewX) when `fontstyle="italic"`.
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
    """Exact pixel width of `s` rendered in DejaVu Sans at `size` pt.
    Multi-line text (`\\n`) measures as the widest line."""
    if not s:
        return 0.0
    if "\n" in s:
        return max(measure_text(line, size) for line in s.split("\n"))
    scale = size / _UPEM
    return sum(_glyph(ch).width * scale for ch in s)


def line_height(size: float) -> float:
    """Baseline-to-baseline distance between consecutive lines of
    multi-line text at `size` pt (``size × font.linespacing``)."""
    return size * _FONTSPEC["linespacing"]


def text_block_height(s: str, size: float) -> float:
    """Layout height of the text block for `s` at `size` pt — the bare
    font size for single-line text (matching what layout math reserved
    before multi-line existed), plus one `line_height` per extra line.
    Use this wherever band/margin math previously reserved `size`."""
    return size + (s.count("\n")) * line_height(size)


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


def rotated_label_bbox(label_w: float, label_h: float, rot_deg: float) -> tuple[float, float]:
    """Bounding-box (width, height) of a rotated text label. Conservative —
    uses the simple ``|cos|·w + |sin|·h`` envelope, which is exact for the
    AABB of an axis-aligned rectangle rotated by any angle."""
    if rot_deg == 0:
        return label_w, label_h
    rad = math.radians(abs(rot_deg))
    sin_r = math.sin(rad)
    cos_r = math.cos(rad)
    return (label_w * cos_r + label_h * sin_r,
            label_w * sin_r + label_h * cos_r)


def tick_band_height(labels, size, rotation) -> float:
    """Vertical extent of a tick-label band past its anchor row.

    Anchor sits at ``cap_height`` below the band top (cap top flush with
    the band top for rot=0). Rotated text extends ``|sin|·label_w`` plus
    ``|cos|·descender`` below the anchor (AABB of the rotated label rect
    with anchor at right-edge/baseline). Used by both the margin
    reservation and the sector-label stacking position — same formula in
    one home keeps them in lockstep.
    """
    if not labels:
        return 0.0
    max_w = max((measure_text(str(l), size) for l in labels), default=0.0)
    rad = math.radians(abs(rotation))
    return (cap_height(size)
            + math.sin(rad) * max_w
            + math.cos(rad) * descender(size))


_GLYPH_FLOAT_RE = re.compile(r"-?\d+\.\d+")


def _round_glyph_floats(d: str) -> str:
    """Round every float in a glyph-path d-string via ``coord(...)``.

    fontTools sub-bit rounding inside `SVGPathPen.getCommands()` shifts
    between releases (e.g. 4.62 → 4.63 turns `10.9921875` into
    `10.992187499999993`). Routing through ``coord`` matches the pixel
    quantization used everywhere else and collapses both representations
    identically."""
    return _GLYPH_FLOAT_RE.sub(lambda m: f"{coord(float(m.group()))}", d)


def _glyph_path_d(s: str, x: float, y: float, size: float,
                  anchor: str = "start", fontstyle: str = "normal") -> str:
    """Build the SVG `d` attribute for `s` rendered at baseline (x, y).

    `anchor` matches SVG's text-anchor ('start' | 'middle' | 'end');
    `fontstyle="italic"` applies the synthetic oblique skew. Multi-line
    text (`\\n`) puts the FIRST line's baseline at (x, y) and steps each
    subsequent line down by `line_height(size)`; every line is anchored
    independently, so `anchor="middle"` centers each line."""
    if not s:
        return ""
    pen = SVGPathPen(_GS)
    scale = size / _UPEM
    italic = (fontstyle == "italic")
    for i, line in enumerate(s.split("\n")):
        width = measure_text(line, size)
        if anchor == "middle":
            cx = x - width / 2
        elif anchor == "end":
            cx = x - width
        else:
            cx = x
        ly = y + i * line_height(size)
        for ch in line:
            g = _glyph(ch)
            # SVG y points down, font y points up — flip with negative scale.
            # Italic: skewX applied before the y-flip+scale so the slant lives
            # in the post-scale (screen) frame; top of glyph leans right.
            t = Transform().translate(cx, ly).scale(scale, -scale)
            if italic:
                t = t.skew(_ITALIC_SKEW_RAD, 0)
            tpen = TransformPen(pen, t)
            g.draw(tpen)
            cx += g.width * scale
    return _round_glyph_floats(pen.getCommands())


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
