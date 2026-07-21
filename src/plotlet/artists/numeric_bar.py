"""Numeric-x bar.

Sibling of the categorical `c.bar`: where `bar` places cats on a band
scale and takes bandwidth from the scale, `numeric_bar` anchors bars at
*numeric* positions (e.g. genome coordinates, time-series with explicit
numeric x) with a fixed data-unit `width` you control directly.

  c.add_numeric_bar(data=df, x='col', y='col', width=0.8, ...)
"""

from ..registry import ArtistSpec, add_artist, declare_coord_support
from ..utils import pack_opts, to_list
from ..draw import rect
from .._spec import _D


def numeric_bar_record(data=None,
                       # input columns — consumed here at record
                       x=None, y=None,
                       # style — packed into opts for the draw/legend side
                       width=None, color=None, alpha=None,
                       label=None, legend=None):
    if data is None or x is None or y is None:
        raise TypeError("numeric_bar requires data=, x=, y= (heights).")
    return {
        "type": "numeric_bar",
        "xs":      to_list(data[x]),
        "heights": to_list(data[y]),
        "opts": pack_opts(width=width, color=color, alpha=alpha,
                          label=label, legend=legend),
    }


# Autoscale: x extent grows by half-width on each side so bar edges fit;
# y always includes 0 so bars anchor visually.
def numeric_bar_xdomain(a):
    w = a["opts"].get("width", 0.8)
    return [x - w / 2 for x in a["xs"]] + [x + w / 2 for x in a["xs"]]


def numeric_bar_ydomain(a):
    return list(a["heights"]) + [0]


def numeric_bar_draw(a, ctx):
    opts = a["opts"]
    w = opts.get("width", 0.8)
    alpha = opts.get("alpha", _D["bar_alpha"])
    col = ctx.color
    y0 = ctx.y_scale(0)
    out = []
    for x, h in zip(a["xs"], a["heights"]):
        x_left  = ctx.x_scale(x - w / 2)
        x_right = ctx.x_scale(x + w / 2)
        y_top   = ctx.y_scale(h)
        bx = min(x_left, x_right)
        bw = abs(x_right - x_left)
        by = min(y0, y_top)
        bh = abs(y_top - y0)
        out.append(rect(bx, by, bw, bh, fill=col, alpha=alpha,
                        project=ctx.warp))
    return "".join(out)


def numeric_bar_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        col = a["_color"]
        alpha = a["opts"].get("alpha", _D["bar_alpha"])
        return rect(x0, y_mid - 5, 22, 10, fill=col, alpha=alpha)
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


add_artist(ArtistSpec(
    name="numeric_bar",
    record=numeric_bar_record,
    xdomain=numeric_bar_xdomain,
    ydomain=numeric_bar_ydomain,
    draw=numeric_bar_draw,
    legend_entries=numeric_bar_legend_entries,
    force_zero_y=True,
))
declare_coord_support("Circular", ["numeric_bar"])
