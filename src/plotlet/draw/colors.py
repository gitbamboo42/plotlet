"""Color resolution: tab10 shortcuts, named colors, single-letter codes."""

TAB10 = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]

colors = TAB10

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
}


def resolve_color(c):
    """Map a color spec to a hex string. Pass-through unrecognized strings.

    Accepts: 'C0'..'C9' tab10 shortcuts, named colors ('red', 'blue', …),
    single-letter codes ('k', 'r', 'g', 'b', 'w'), or any hex / CSS color.
    """
    if c is None:
        return None
    if isinstance(c, str):
        if len(c) == 2 and c[0] == "C" and c[1].isdigit():
            return TAB10[int(c[1])]
        return _COLOR_NAMES.get(c, c)
    return c
