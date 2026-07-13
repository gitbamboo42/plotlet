"""Color resolution and discrete palettes.

Single-color specs resolve via `resolve_color`; discrete palette lists
come from `palette()`, derived from the vendored colormap LUTs in
`_cm_data` (no separate palette data).
"""
from ._cm_data import LUTS
from .colormaps import _lut


class Palette(list):
    """A list of color strings that displays as swatches in notebooks.

    Behaves exactly like a plain list everywhere else (indexing, JSON
    serialization, `palette=` kwargs). Hover a swatch for its hex value.
    """
    def _repr_html_(self):
        s = 24
        rects = "".join(
            f'<rect x="{i * s}" width="{s}" height="{s}" fill="{c}">'
            f"<title>{c}</title></rect>"
            for i, c in enumerate(self))
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{len(self) * s}" height="{s}">{rects}</svg>')


TAB10 = Palette([
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
])

# Names and single-letter codes are tab10-flavored, not CSS: "red" is the
# muted tab10 red, not #ff0000. Letters map to the tab10 hue of the same
# family (m → pink, y → olive — tab10 has no true magenta/yellow).
_COLOR_NAMES = {
    "blue":   "#1f77b4",
    "orange": "#ff7f0e",
    "green":  "#2ca02c",
    "red":    "#d62728",
    "purple": "#9467bd",
    "brown":  "#8c564b",
    "pink":   "#e377c2",
    "gray":   "#7f7f7f",
    "olive":  "#bcbd22",
    "cyan":   "#17becf",
    "k": "#000000",
    "w": "#ffffff",
    "b": "#1f77b4",
    "g": "#2ca02c",
    "r": "#d62728",
    "c": "#17becf",
    "m": "#e377c2",
    "y": "#bcbd22",
}


def resolve_color(c):
    """Map a color spec to an SVG color string. Pass-through unrecognized strings.

    Accepts: 'C0', 'C1', … cycle shortcuts (wrap past 'C9'), named colors
    ('red', 'blue', …), single-letter codes ('b','g','r','c','m','y','k','w'),
    grayscale strings ('0.5'), (r, g, b[, a]) tuples of floats in [0, 1],
    or any hex / CSS color string (SVG understands the full CSS set natively).
    """
    if c is None:
        return None
    if isinstance(c, str):
        if len(c) >= 2 and c[0] == "C" and c[1:].isdigit():
            return TAB10[int(c[1:]) % 10]
        if c in _COLOR_NAMES:
            return _COLOR_NAMES[c]
        try:
            v = float(c)
        except ValueError:
            return c
        if 0.0 <= v <= 1.0:
            g = round(v * 255)
            return f"#{g:02x}{g:02x}{g:02x}"
        return c
    if (isinstance(c, (tuple, list)) and len(c) in (3, 4)
            and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in c)):
        return "#" + "".join(f"{round(v * 255):02x}" for v in c)
    return c


# The qualitative colormaps in `_cm_data` are step functions: N flat runs
# across the 256-entry LUT. Sampling each run's midpoint recovers the
# original discrete colors exactly, so palettes need no extra data — only
# the palette sizes, which the LUT format erases.
_QUALITATIVE_N = {
    "Accent": 8, "Dark2": 8, "Paired": 12,
    "Pastel1": 9, "Pastel2": 8,
    "Set1": 9, "Set2": 8, "Set3": 12,
    "tab10": 10, "tab20": 20, "tab20b": 20, "tab20c": 20,
}


# Palettes that are plain color lists, not LUT-derived. "colorblind" is
# Okabe & Ito's colorblind-safe qualitative set in its canonical order
# (https://jfly.uni-koeln.de/color/) — safe under deuteranopia,
# protanopia, and tritanopia.
_EXPLICIT_PALETTES = {
    "colorblind": [
        "#000000", "#e69f00", "#56b4e9", "#009e73",
        "#f0e442", "#0072b2", "#d55e00", "#cc79a7",
    ],
}


def _lut_hex(lut, i):
    j = 3 * i
    return f"#{lut[j]:02x}{lut[j + 1]:02x}{lut[j + 2]:02x}"


def auto_label_color(r, g, b):
    """Black or white cell-label text, whichever contrasts with an
    (r, g, b) 0–255 background — the shared `annot=` rule for heatmap
    and imshow. Perceived luminance (ITU-R BT.601 weights) with a 0.55
    cutoff: slightly above 0.5 so mid-tones prefer white text, which
    reads better on saturated colormap mids."""
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#ffffff" if lum < 0.55 else "#000000"


def palette(name, n=None):
    """Discrete color list (hex strings) by name.

    Qualitative names (`list_palettes()`) return their full color list;
    `n` truncates or cycles past the end. Any continuous colormap name
    ('viridis', …) is sampled at `n` evenly-spaced points (`n` required).
    A '_r' suffix reverses either kind. Accepted anywhere artists take
    `palette=`, e.g. `c.bar(..., fill="group", palette="Set2")`. The
    returned `Palette` is a plain list that shows swatches in notebooks.
    """
    base = name[:-2] if name.endswith("_r") else name
    if base in _EXPLICIT_PALETTES:
        cols = list(_EXPLICIT_PALETTES[base])
        if name.endswith("_r"):
            cols.reverse()
        if n is not None:
            cols = [cols[i % len(cols)] for i in range(n)]
        return Palette(cols)
    if base in _QUALITATIVE_N:
        size = _QUALITATIVE_N[base]
        lut = LUTS[name]
        cols = [_lut_hex(lut, int((i + 0.5) * 256 / size)) for i in range(size)]
        if n is not None:
            cols = [cols[i % size] for i in range(n)]
        return Palette(cols)
    lut = _lut(name)
    if lut is not None:
        if n is None:
            raise ValueError(
                f"{name!r} is a continuous colormap — pass a count to "
                f"sample it into a color list: palette({name!r}, n)")
        if n == 1:
            return Palette([_lut_hex(lut, 128)])
        return Palette(_lut_hex(lut, int(i * 255 / (n - 1) + 0.5))
                       for i in range(n))
    raise ValueError(
        f"unknown palette {name!r}. Qualitative palettes: "
        f"plotlet.list_palettes(); continuous colormaps (sampled with n): "
        f"plotlet.list_colormaps().")


def list_palettes():
    """Sorted qualitative palette names accepted by `palette()`.

    Each also has a '_r' reversed variant, and any continuous colormap
    name (`list_colormaps()`) works too when `n` is given.
    """
    return sorted(set(_QUALITATIVE_N) | set(_EXPLICIT_PALETTES))
