"""Linestyle resolution: long-name aliases for plotlet's `_DASH` keys.

`_DASH` (loaded from `spec.json:linestyles`) is keyed on the short codes
`-`, `--`, `:`, `-.`. Users often type the long names (`"solid"`,
`"dashed"`, `"dotted"`, `"dashdot"`) — `resolve_linestyle` maps those to
the short code so they hit `_DASH` correctly. Pass-through for raw SVG
dasharray strings (`"6,3"`) and anything else unrecognized;
`check_dasharray` then rejects the anything-else at the emission
doorway (`dash_attr`), so a typo like `"dahsed"` errors instead of
landing in the SVG as a dasharray browsers silently ignore.
"""
import difflib
import re

_LINESTYLE_NAMES = {
    "solid":   "-",
    "dashed":  "--",
    "dotted":  ":",
    "dashdot": "-.",
}


def resolve_linestyle(ls):
    """Map a linestyle spec to a `_DASH` key.

    Long names (`"dotted"`, …) → short codes. Everything else passes
    through unchanged so raw dasharray strings (`"6,3"`) and the short
    codes themselves still work.
    """
    if ls is None:
        return None
    return _LINESTYLE_NAMES.get(ls, ls)


def check_dasharray(value):
    """A linestyle that isn't a registered code must be a raw SVG
    dasharray — numbers separated by commas or spaces (`"6,3"`).
    Anything else would emit a stroke-dasharray browsers silently
    ignore, rendering a solid line with no error — the vocabulary
    stays open, but not typo-shaped."""
    tokens = re.split(r"[,\s]+", str(value).strip())
    try:
        ok = bool(tokens) and all(float(t) >= 0 for t in tokens)
    except ValueError:
        ok = False
    if ok:
        return
    hint = ""
    if isinstance(value, str):
        close = difflib.get_close_matches(
            value, list(_LINESTYLE_NAMES), n=1)
        if close:
            hint = f" Did you mean {close[0]!r}?"
    raise ValueError(
        f"unknown linestyle {value!r} — must be '-', '--', ':', '-.', "
        f"'solid', 'dashed', 'dotted', 'dashdot', 'none', or a raw SVG "
        f"dasharray like '6,3'.{hint}"
    )
