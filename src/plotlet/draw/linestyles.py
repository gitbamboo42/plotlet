"""Linestyle resolution: long-name aliases for plotlet's `_DASH` keys.

`_DASH` (loaded from `spec.json:linestyles`) is keyed on the short codes
`-`, `--`, `:`, `-.`. Users often type the long names (`"solid"`,
`"dashed"`, `"dotted"`, `"dashdot"`) — `resolve_linestyle` maps those to
the short code so they hit `_DASH` correctly. Pass-through for raw SVG
dasharray strings (`"6,3"`) and anything else unrecognized.
"""

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
