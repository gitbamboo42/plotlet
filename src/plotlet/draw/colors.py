"""Color resolution: tab10 shortcuts, named colors, single-letter codes."""
from .._spec import _TAB10, _COLOR_NAMES

TAB10 = list(_TAB10)
colors = list(_TAB10)


def _resolve_color(c):
    """Map a color spec to a hex string. Pass-through unrecognized strings.

    Accepts: 'C0'..'C9' tab10 shortcuts, named colors ('red', 'blue', …),
    single-letter codes ('k', 'r', 'g', 'b', 'w'), or any hex / CSS color.
    """
    if c is None:
        return None
    if isinstance(c, str):
        if len(c) == 2 and c[0] == "C" and c[1].isdigit():
            return _TAB10[int(c[1])]
        return _COLOR_NAMES.get(c, c)
    return c
