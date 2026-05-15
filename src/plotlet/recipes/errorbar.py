"""Custom artist: errorbar.

Points with vertical (and optional horizontal) error bars + caps — the
matplotlib `plt.errorbar` staple for measured-with-uncertainty scatter.

API: c.errorbar(xs, ys, yerr=..., xerr=..., capsize=4, marker="o", ...).
`yerr`/`xerr` can be a scalar (symmetric, broadcast), a sequence (per-point
symmetric), or a 2-tuple `(lower, upper)` for asymmetric bars.
"""

SUMMARY = 'Points with vertical and/or horizontal error bars and caps.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import marker, segment, errorbar_v, errorbar_h


def _expand_err(err, n):
    """-> (lower_offsets, upper_offsets). None -> zeros."""
    if err is None:
        return [0.0] * n, [0.0] * n
    if isinstance(err, tuple) and len(err) == 2:
        lo = to_list(err[0]); hi = to_list(err[1])
        if len(lo) == 1: lo = lo * n
        if len(hi) == 1: hi = hi * n
        return lo, hi
    if hasattr(err, "__iter__") and not isinstance(err, str):
        v = to_list(err)
        return list(v), list(v)
    return [float(err)] * n, [float(err)] * n


def errorbar_record(args, kw):
    xs = to_list(args[0])
    ys = to_list(args[1])
    return {"type": "errorbar", "xs": xs, "ys": ys, "opts": kw}


def errorbar_xdomain(a):
    xs = a["xs"]
    xlo, xhi = _expand_err(a["opts"].get("xerr"), len(xs))
    return [x - lo for x, lo in zip(xs, xlo)] + [x + hi for x, hi in zip(xs, xhi)]


def errorbar_ydomain(a):
    ys = a["ys"]
    ylo, yhi = _expand_err(a["opts"].get("yerr"), len(ys))
    return [y - lo for y, lo in zip(ys, ylo)] + [y + hi for y, hi in zip(ys, yhi)]


def errorbar_draw(a, ctx):
    xs, ys, opts = a["xs"], a["ys"], a["opts"]
    n = len(xs)
    xlo, xhi = _expand_err(opts.get("xerr"), n)
    ylo, yhi = _expand_err(opts.get("yerr"), n)
    capsize = opts.get("capsize", 4)
    lw = opts.get("linewidth", 1.2)
    mk = opts.get("marker", "o")
    msize = opts.get("markersize", ctx.defaults["markersize"])
    col = ctx.color
    out = []
    for x, y, dxl, dxh, dyl, dyh in zip(xs, ys, xlo, xhi, ylo, yhi):
        px = ctx.x_scale(x); py = ctx.y_scale(y)
        if dyl or dyh:
            out.append(errorbar_v(px, ctx.y_scale(y - dyl), ctx.y_scale(y + dyh),
                                  capsize=capsize, color=col, width=lw))
        if dxl or dxh:
            out.append(errorbar_h(py, ctx.x_scale(x - dxl), ctx.x_scale(x + dxh),
                                  capsize=capsize, color=col, width=lw))
        out.append(marker(mk, px, py, msize, col, 1))
    return "".join(out)


def errorbar_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    msize = a["opts"].get("markersize", ctx.defaults["markersize"])
    cx = x0 + 11
    return (
        segment(cx, y_mid - 5, cx, y_mid + 5, color=col, width=1.2)
        + marker(a["opts"].get("marker", "o"), cx, y_mid, msize, col, 1)
    )


pt.add_artist(pt.ArtistSpec(
    name="errorbar",
    record=errorbar_record,
    xdomain=errorbar_xdomain,
    ydomain=errorbar_ydomain,
    draw=errorbar_draw,
    legend_swatch=errorbar_legend_swatch,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    xs = [1, 2, 3, 4, 5, 6]
    ys = [2.1, 3.4, 4.0, 3.8, 5.1, 6.2]
    yerr = [0.4, 0.3, 0.6, 0.5, 0.4, 0.7]
    c = pt.chart()
    c.errorbar(xs, ys, yerr=yerr, label="measurement")
    c.errorbar([1.2, 2.2, 3.2, 4.2, 5.2, 6.2],
               [1.5, 2.6, 3.3, 4.7, 5.9, 6.8],
               yerr=([0.2, 0.3, 0.2, 0.4, 0.3, 0.5],
                     [0.5, 0.4, 0.6, 0.3, 0.5, 0.4]),
               marker="s", label="model")
    c.title("Error bars").xlabel("x").ylabel("y").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
