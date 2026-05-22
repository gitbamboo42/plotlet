"""Helpers shared across 2+ per-artist files.

Each built-in artist registers one of the `*_legend_entries` functions so
the legend dispatch in `_render` can stay generic — no type-string matching.
Paint logic is a nested closure; there are no shared swatch helpers.
"""
from .._spec import _LEGSPEC
from ..draw import marker, segment, rect


def _xy_minmax(xs, ys):
    """Min/max for an x/y series, ignoring NaN. Returns dict ready to merge
    into a data_attrs result."""
    fxs = [x for x in xs if isinstance(x, (int, float)) and x == x]
    fys = [y for y in ys if isinstance(y, (int, float)) and y == y]
    out = {}
    if fxs:
        out["x-min"] = min(fxs)
        out["x-max"] = max(fxs)
    if fys:
        out["y-min"] = min(fys)
        out["y-max"] = max(fys)
    return out


def _line_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        out = segment(x0, y_mid, x0 + sw, y_mid,
                      color=a["_color"],
                      width=a["opts"].get("linewidth", ctx.defaults["linewidth"]),
                      dash=a["opts"].get("linestyle"))
        if a["opts"].get("marker"):
            out += marker(a["opts"]["marker"], x0 + sw / 2, y_mid,
                          a["opts"].get("markersize", ctx.defaults["markersize"]),
                          a["_color"], 1)
        return out
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


def _refline_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        return segment(x0, y_mid, x0 + sw, y_mid,
                       color=a["_color"],
                       width=a["opts"].get("linewidth", ctx.defaults["refline_width"]),
                       dash=a["opts"].get("linestyle"))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


def _bar_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        return rect(x0, y_mid - 5, sw, 10, fill=a["_color"],
                    alpha=a["opts"].get("alpha", 1))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


def _refspan_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        return rect(x0, y_mid - 5, sw, 10, fill=a["_color"],
                    alpha=a["opts"].get("alpha", ctx.defaults["refspan_alpha"]))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]
