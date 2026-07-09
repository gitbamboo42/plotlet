"""Font loading + glyph-to-path rendering.

Owns the full text → SVG-path pipeline: glyph lookup, width measurement,
italic synthesis. `text_path` in `plotlet.draw` is a thin wrapper that
adds the SVG `<path fill=...>` element around the path data produced here.

The active face is resolved from `_FONTSPEC["family"]` at call time (first
comma-separated segment), so per-chart `c.font(...)` and theme overrides
flow through the same spec rail as every other visual constant — no
parameter threading. plotlet only ever loads a font from a file it can
name explicitly (a bundled face or a user-supplied `.ttf`/`.otf` path),
never an OS font lookup — OS resolution would break byte-identical output
across machines.
"""
import math
import re
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.transform import Transform
from .._spec import _FONTSPEC
from .format import coord


_FONT_DIR = Path(__file__).parent / "fonts"

# Bundled families, keyed lowercase: (bold, italic) → face file. All
# four RIBBI faces ship per family, so `fontstyle` / `fontweight` on a
# bundled family always resolve to a real drawn face — never synthetic
# styling. Only the roman face is selectable as a *family* (a `font=`
# selector styles ALL text, ticks included; bold/italic are per-text
# options, e.g. `c.xticks(fontweight="bold")`).
_BUNDLED = {
    "dejavu sans": {
        (False, False): "DejaVuSans.ttf",
        (True,  False): "DejaVuSans-Bold.ttf",
        (False, True):  "DejaVuSans-Oblique.ttf",
        (True,  True):  "DejaVuSans-BoldOblique.ttf",
    },
    "arimo": {
        (False, False): "Arimo-Regular.ttf",
        (True,  False): "Arimo-Bold.ttf",
        (False, True):  "Arimo-Italic.ttf",
        (True,  True):  "Arimo-BoldItalic.ttf",
    },
}
# "Helvetica"/"Arial" map to Arimo (metric-compatible with both,
# OFL-licensed) rather than an OS lookup.
_ALIASES = {"sans": "dejavu sans", "helvetica": "arimo", "arial": "arimo"}

# Synthetic italic: tilt the upright face at render time by -12° (skewX).
# Fallback for path-loaded fonts only — bundled families resolve
# `fontstyle="italic"` to their real italic file.
_ITALIC_SKEW_RAD = -0.20943951023931953  # math.radians(-12)


class Font:
    """One loaded font file + the metrics layout math needs. Construct
    via `_load_font` (cached) so each file loads and measures once."""

    def __init__(self, path: str):
        self.path = path
        ttf = TTFont(path)
        self.upem = ttf["head"].unitsPerEm
        self.cmap = ttf.getBestCmap()
        self.glyphset = ttf.getGlyphSet()
        # Name-table family (nameID 1) — feeds the outer <svg
        # font-family> attr for path-loaded fonts, where the file path
        # itself must not leak into published output.
        self.family = ttf["name"].getDebugName(1) or Path(path).stem
        # Cap height measured from the 'H' glyph bounds (yMax / upem):
        # the conversion between baseline anchor (where `text_path`
        # draws) and cap-top anchor (where the eye perceives the top of
        # the glyph). Measured per font — DejaVu's 1493/2048 would be
        # wrong for any other face.
        self.cap_ratio = self._measure_cap_ratio()
        # Descender depth (positive, em-fraction). Worst-case glyph
        # extent below the baseline — used to place text so its
        # descender bottom sits at a target pixel without clipping.
        self.descender_ratio = abs(ttf["hhea"].descent) / self.upem

    def _measure_cap_ratio(self) -> float:
        gname = self.cmap.get(ord("H"))
        if gname is None:
            raise ValueError(
                f"font {self.path!r} has no 'H' glyph — cannot measure "
                "cap height, which plotlet's text layout requires."
            )
        pen = BoundsPen(self.glyphset)
        self.glyphset[gname].draw(pen)
        if pen.bounds is None:
            raise ValueError(
                f"font {self.path!r}: 'H' glyph has no outline — cannot "
                "measure cap height."
            )
        return pen.bounds[3] / self.upem

    def glyph(self, ch):
        return self.glyphset[self.cmap.get(ord(ch), ".notdef")]


@lru_cache(maxsize=None)
def _load_font(path: str) -> Font:
    return Font(path)


def _resolve_font(selector: str) -> Font:
    """Selector → roman `Font`. A `.ttf`/`.otf` path loads that file
    (the escape hatch — any font on disk, output stays self-contained);
    anything else must name a bundled family or alias. Unknown names
    fail loudly — no silent fallback."""
    sel = selector.strip()
    if sel.lower().endswith((".ttf", ".otf")):
        return _load_font(sel)
    key = _ALIASES.get(sel.lower(), sel.lower())
    if key in _BUNDLED:
        return _load_font(str(_FONT_DIR / _BUNDLED[key][(False, False)]))
    raise ValueError(
        f"unknown font {sel!r}: expected a bundled family or alias "
        f"({sorted(_BUNDLED) + sorted(_ALIASES)}) or a path to a "
        ".ttf/.otf file. plotlet never resolves font names through the OS."
    )


def _is_bold(fontweight) -> bool:
    if fontweight in (None, "normal"):
        return False
    if fontweight == "bold":
        return True
    raise ValueError(
        f"fontweight={fontweight!r}: expected 'normal' or 'bold'.")


def _is_italic(fontstyle) -> bool:
    if fontstyle in (None, "normal"):
        return False
    if fontstyle == "italic":
        return True
    raise ValueError(
        f"fontstyle={fontstyle!r}: expected 'normal' or 'italic'.")


def _resolve_face(fontstyle="normal", fontweight="normal") -> tuple[Font, bool]:
    """Active family + variant → `(Font, synthetic_italic)`.

    Bundled families resolve every (weight, style) combination to a real
    drawn face file, so `synthetic_italic` is False for them. A
    path-loaded font is one file with no known siblings: italic falls
    back to the synthetic skew (`synthetic_italic=True`), and bold is a
    loud error — pass the bold file's path as `font=` instead."""
    bold = _is_bold(fontweight)
    italic = _is_italic(fontstyle)
    sel = _FONTSPEC["family"].split(",")[0].strip()
    if sel.lower().endswith((".ttf", ".otf")):
        if bold:
            raise ValueError(
                f"fontweight='bold' with a path-loaded font ({sel!r}): "
                "plotlet can't know which file holds the bold face — "
                "pass the bold file's path as font= instead."
            )
        return _load_font(sel), italic
    key = _ALIASES.get(sel.lower(), sel.lower())
    faces = _BUNDLED.get(key)
    if faces is None:
        raise ValueError(
            f"unknown font {sel!r}: expected a bundled family or alias "
            f"({sorted(_BUNDLED) + sorted(_ALIASES)}) or a path to a "
            ".ttf/.otf file. plotlet never resolves font names through "
            "the OS."
        )
    return _load_font(str(_FONT_DIR / faces[(bold, italic)])), False


def _active_font() -> Font:
    """The roman face selected by the live spec — first comma-separated
    segment of `font.family`. Resolved at call time so `active_theme` /
    `active_font` scoping flows through without parameter threading."""
    return _resolve_face()[0]


def svg_family() -> str:
    """Value for the outer `<svg font-family="…">` attr. The spec string
    passes through verbatim (it's a CSS fallback list), except a
    path selector emits the font's name-table family instead — local
    file paths must not leak into published SVGs."""
    fam = _FONTSPEC["family"]
    if fam.split(",")[0].strip().lower().endswith((".ttf", ".otf")):
        return _active_font().family
    return fam


def measure_text(s: str, size: float,
                 fontstyle: str = "normal",
                 fontweight: str = "normal") -> float:
    """Exact pixel width of `s` rendered in the active font at `size` pt.
    Multi-line text (`\\n`) measures as the widest line. Pass the same
    `fontstyle` / `fontweight` the text will render with — variant faces
    have their own advance widths."""
    if not s:
        return 0.0
    if "\n" in s:
        return max(measure_text(line, size, fontstyle, fontweight)
                   for line in s.split("\n"))
    f, _ = _resolve_face(fontstyle, fontweight)
    scale = size / f.upem
    return sum(f.glyph(ch).width * scale for ch in s)


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
    """Cap height in px for the active font at `size`. Equals the distance
    from baseline up to the top of a capital letter — i.e. the conversion
    between `text_path`'s baseline anchor and the visual glyph top."""
    return size * _active_font().cap_ratio


def descender(size: float) -> float:
    """Descender depth in px (positive) for the active font at `size`.
    Equals the worst-case distance baseline → glyph bottom, used to place
    text so its visible bottom edge sits at a target pixel."""
    return size * _active_font().descender_ratio


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


def tick_band_height(labels, size, rotation,
                     fontstyle: str = "normal",
                     fontweight: str = "normal") -> float:
    """Vertical extent of a tick-label band past its anchor row.

    Anchor sits at ``cap_height`` below the band top (cap top flush with
    the band top for rot=0). Rotated text extends ``|sin|·label_w`` plus
    ``|cos|·descender`` below the anchor (AABB of the rotated label rect
    with anchor at right-edge/baseline). Used by both the margin
    reservation and the sector-label stacking position — same formula in
    one home keeps them in lockstep.

    Only the width measurement is variant-aware: cap/descender ratios
    are identical across all four faces of every bundled family, and a
    path-loaded font resolves every variant to its one file.
    """
    if not labels:
        return 0.0
    max_w = max((measure_text(str(l), size, fontstyle, fontweight)
                 for l in labels), default=0.0)
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
                  anchor: str = "start", fontstyle: str = "normal",
                  fontweight: str = "normal") -> str:
    """Build the SVG `d` attribute for `s` rendered at baseline (x, y).

    `anchor` matches SVG's text-anchor ('start' | 'middle' | 'end');
    `fontstyle` / `fontweight` select the variant face (real drawn
    Italic/Bold files for bundled families; a path-loaded font gets the
    synthetic oblique skew for italic). Multi-line text (`\\n`) puts the
    FIRST line's baseline at (x, y) and steps each subsequent line down
    by `line_height(size)`; every line is anchored independently, so
    `anchor="middle"` centers each line."""
    if not s:
        return ""
    f, synthetic_italic = _resolve_face(fontstyle, fontweight)
    pen = SVGPathPen(f.glyphset)
    scale = size / f.upem
    for i, line in enumerate(s.split("\n")):
        width = measure_text(line, size, fontstyle, fontweight)
        if anchor == "middle":
            cx = x - width / 2
        elif anchor == "end":
            cx = x - width
        else:
            cx = x
        ly = y + i * line_height(size)
        for ch in line:
            g = f.glyph(ch)
            # SVG y points down, font y points up — flip with negative scale.
            # Italic: skewX applied before the y-flip+scale so the slant lives
            # in the post-scale (screen) frame; top of glyph leans right.
            t = Transform().translate(cx, ly).scale(scale, -scale)
            if synthetic_italic:
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
        return -cap_height(size) / 2
    if decoration == "overline":
        # Just above the cap.
        return -cap_height(size) - size * 0.06
    raise ValueError(
        f"unknown decoration={decoration!r}; "
        f"expected one of {_DECORATION_KINDS} or 'none'."
    )
