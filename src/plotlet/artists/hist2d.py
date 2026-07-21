"""Rectangular 2-D histogram — point counts in a uniform x/y bin grid.

mpl `hist2d` / ggplot `geom_bin2d` / seaborn bivariate `histplot`. The
axis-aligned cousin of hexbin: same colormap-by-count encoding, but
rectangular bins under explicit binwidth control. Cells with no points
stay transparent (the `geom_bin2d` convention, and it keeps a sparse
scatter readable).

API: c.add_hist2d(aes(x="col", y="col"))

Binning (scalar applies to both axes; an (x, y) pair sets them apart):
  bins=30             bin count per axis; an explicit edge sequence, or an
                      (x_edges, y_edges) pair, pins the edges instead
  binwidth=           fixed bin width(s) instead of a count
  binrange=           (lo, hi) span to bin over, or ((xlo, xhi), (ylo, yhi));
                      points outside are dropped

Color:
  cmap='viridis'      colormap name for coloring cells by count
  vmin=0              colormap domain lower bound
  vmax=None           colormap domain upper bound (defaults to max count)
"""
import bisect
import math

from ..registry import ArtistSpec, add_artist
from ..draw import rect
from ..draw import colormap, ContinuousNorm
from ..utils import UNSET, pack_opts, to_list, hist_bin_edges
from .._spec import _D


def _bins_per_axis(value):
    """Split `bins=` into (x, y) parts. A 2-item value is a per-axis
    pair only when both items work as one — a bin count (int >= 1, the
    numpy `[int, int]` convention) or an edge sequence. Anything else
    (an int, a shared-edge sequence — including a 2-item one like
    `[0, 5]`, whose 0 can't be a count) applies to both axes."""
    def per_axis(v):
        return ((isinstance(v, int) and not isinstance(v, bool) and v >= 1)
                or hasattr(v, "__iter__"))
    if (isinstance(value, (list, tuple)) and len(value) == 2
            and all(per_axis(v) for v in value)):
        return value[0], value[1]
    return value, value


def _width_per_axis(value):
    """Split `binwidth=` into (x, y) parts: any 2-item pair is per-axis
    (widths are always scalars, so there's no shared-sequence form)."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0], value[1]
    return value, value


def _range_per_axis(binrange):
    if binrange is None:
        return None, None
    lo = binrange[0]
    if hasattr(lo, "__iter__"):
        return binrange[0], binrange[1]
    return binrange, binrange


def _count2d(xs, ys, xe, ye):
    """Count (x, y) points into the edge grid. Last bin right-inclusive,
    points outside either span dropped, NaN/None pairs skipped — the same
    conventions as `hist_bin_counts`. Returns counts[yi][xi]."""
    def bad(v):
        return v is None or (isinstance(v, float) and math.isnan(v))
    nx = len(xe) - 1
    ny = len(ye) - 1
    counts = [[0] * nx for _ in range(ny)]
    for x, y in zip(xs, ys):
        if bad(x) or bad(y):
            continue
        if x < xe[0] or x > xe[-1] or y < ye[0] or y > ye[-1]:
            continue
        xi = nx - 1 if x == xe[-1] else bisect.bisect_right(xe, x) - 1
        yi = ny - 1 if y == ye[-1] else bisect.bisect_right(ye, y) - 1
        counts[yi][xi] += 1
    return counts


def _hist2d_record(data=None,
                   # input & binning — consumed here at record
                   x=None, y=None,
                   bins=UNSET, binwidth=None, binrange=None,
                   # color — packed into opts for the draw/legend side
                   cmap=None, vmin=None, vmax=None,
                   label=None, legend=None):
    if data is None or x is None or y is None:
        raise TypeError("hist2d requires data=, x=, y=.")
    # `bins=` has a non-None default (30), so a sentinel keeps the
    # bins-vs-binwidth exclusivity check from firing on the default.
    if bins is not UNSET and binwidth is not None:
        raise TypeError("hist2d: pass bins= or binwidth=, not both.")
    if bins is UNSET:
        bins = 30
    xs = to_list(data[x])
    ys = to_list(data[y])
    bins_x, bins_y = _bins_per_axis(bins)
    bw_x, bw_y = _width_per_axis(binwidth)
    br_x, br_y = _range_per_axis(binrange)
    opts = pack_opts(cmap=cmap, vmin=vmin, vmax=vmax,
                     label=label, legend=legend)
    finite_x = [v for v in xs if isinstance(v, (int, float)) and v == v]
    finite_y = [v for v in ys if isinstance(v, (int, float)) and v == v]
    if not finite_x or not finite_y:
        return {"type": "hist2d", "_xedges": [], "_yedges": [],
                "_counts": [], "_n": 0, "_vmax": 0, "opts": opts}
    xe = hist_bin_edges(finite_x, bins=bins_x, binwidth=bw_x, binrange=br_x)
    ye = hist_bin_edges(finite_y, bins=bins_y, binwidth=bw_y, binrange=br_y)
    counts = _count2d(xs, ys, xe, ye)
    return {"type": "hist2d", "_xedges": xe, "_yedges": ye,
            "_counts": counts, "_n": len(xs),
            "_vmax": max((v for row in counts for v in row), default=0),
            "opts": opts}


def _hist2d_xdomain(a):
    xe = a["_xedges"]
    return [xe[0], xe[-1]] if xe else None


def _hist2d_ydomain(a):
    ye = a["_yedges"]
    return [ye[0], ye[-1]] if ye else None


def _hist2d_draw(a, ctx):
    xe, ye, counts = a["_xedges"], a["_yedges"], a["_counts"]
    if not counts:
        return ""
    cm = colormap(a["opts"].get("cmap", _D["default_cmap"]))
    vmin = a["opts"].get("vmin", 0)
    vmax = a["opts"].get("vmax", a["_vmax"])
    norm = ContinuousNorm(vmin, vmax, "linear")
    out = []
    for yi in range(len(ye) - 1):
        py0 = ctx.y_scale(ye[yi])
        py1 = ctx.y_scale(ye[yi + 1])
        for xi in range(len(xe) - 1):
            n = counts[yi][xi]
            if not n:
                continue
            rv, gv, bv = cm(norm.to_unit(n))
            px0 = ctx.x_scale(xe[xi])
            px1 = ctx.x_scale(xe[xi + 1])
            out.append(rect(min(px0, px1), min(py0, py1),
                            abs(px1 - px0), abs(py1 - py0),
                            fill=f"rgb({rv},{gv},{bv})"))
    return "".join(out)


def _hist2d_legend_gradient(a):
    return {"kind": "continuous",
            "cmap": a["opts"].get("cmap", _D["default_cmap"]),
            "vmin": a["opts"].get("vmin", 0),
            "vmax": a["opts"].get("vmax", a["_vmax"]),
            "norm": "linear", "label": "count"}


def _hist2d_data_attrs(a):
    return {"n": a["_n"],
            "bins-x": max(len(a["_xedges"]) - 1, 0),
            "bins-y": max(len(a["_yedges"]) - 1, 0),
            "count-max": a["_vmax"]}


add_artist(ArtistSpec(
    name="hist2d",
    record=_hist2d_record,
    xdomain=_hist2d_xdomain,
    ydomain=_hist2d_ydomain,
    draw=_hist2d_draw,
    uses_color_cycle=False,
    legend_gradient=_hist2d_legend_gradient,
    data_attrs=_hist2d_data_attrs,
))
