"""circular() layout — renders a list of pt.chart() objects as radial tracks.

Each chart occupies an equal r-band by default; pass r_bands=[(lo, hi), ...]
for manual control.

How it works (multi-ring composition on top of CircularCoordinate)
------------------------------------------------------------------
Single-ring circular charts are first-class via ``c.coordinate(pt.CircularCoordinate())``
in core. This helper is the *composition* on top: it draws several charts as
stacked radial bands by reusing ``CircularCoordinate.warp_svg`` per band with
a band-scoped project closure.

Each chart's artists draw in normalised Cartesian pixel space using fake
scales (x_scale(t)=t*iw, y_scale(r)=ih*(1-r)); ``warp_svg`` then back-projects
to (t, r) and forward-projects through the band-scoped circular project.

Constraints
-----------
- Set xlim and ylim explicitly on each chart (or rely on the (0, 1)
  default).  This layout runs _replay but not autoscale, so artists that
  rely on autoscaling won't get domain expansion.
- Line segments are warped point-by-point and become straight chords
  across the ring (fine for dense data, visible for sparse).
- Text labels inside data artists land at their unwarped positions
  (the bezier-glyph heuristic skips them).  Prefer frame-level text.

Usage::

    import plotlet as pt
    from layout import circular

    c1 = pt.chart(xlim=(0, 1), ylim=(0, 1))
    c1.scatter(data={"x": ts, "y": vs}, x="x", y="y", color="#534AB7")

    circular([c1], width=400, height=400).save_svg("out.svg")
"""
import math

from plotlet.chart import Chart
from plotlet.coordinates import CircularCoordinate
from plotlet.core import _prebin_hist, _replay
from plotlet.draw import TAB10, resolve_color
from plotlet.registry import RenderContext, get_artist


# ---------------------------------------------------------------------------
# Artist extraction
# ---------------------------------------------------------------------------

def _chart_state(chart):
    """Replay the chart and run the prep steps _render_inner normally does.

    Mirrors the relevant prefix of _render_inner: hist binning, then color
    resolution (explicit `color=` wins; otherwise tab10 cycle for artists
    that opt in).  Returned `st["artists"]` is ready to draw — every entry
    has `_color` populated and any artist-specific replay prep applied.
    """
    st = _replay(chart._calls)
    _prebin_hist(st)

    color_idx = 0
    for a in st["artists"]:
        spec = get_artist(a["type"])
        opts = a.get("opts") or {}
        user_color = resolve_color(
            opts.get("color")
            or opts.get("_color_literal")
            or opts.get("_fill_literal")
        )
        if user_color is not None:
            a["_color"] = user_color
        elif spec is not None and spec.uses_color_cycle:
            a["_color"] = TAB10[color_idx % 10]
            color_idx += 1
        else:
            a["_color"] = spec.default_color if spec else None
    return st


# ---------------------------------------------------------------------------
# Spine helper
# ---------------------------------------------------------------------------

def _spine_circle(cx, cy, project, r_val, color="#999999", width=0.8) -> str:
    px, py = project(0.0, r_val)
    radius = math.hypot(px - cx, py - cy)
    return (f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}" '
            f'fill="none" stroke="{color}" stroke-width="{width}"/>')


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def circular(charts, *, coordinate=None, width=400, height=400, r_bands=None,
             spine_color="#999999", spine_width=0.8):
    """Render a list of charts as stacked radial tracks.

    Returns a Chart leaf with `_leaf_kind="diagram"` — composes with `|`,
    `/`, and `pt.grid([[..., circular(...), ...]])` like any plotlet panel.
    """
    if coordinate is None:
        coordinate = CircularCoordinate()

    n = len(charts)
    if r_bands is None:
        r_bands = [(i / n, (i + 1) / n) for i in range(n)]

    iw, ih = float(width), float(height)
    cx, cy = iw / 2, ih / 2
    base_project = coordinate({}, iw, ih)
    parts = []

    # Spines at every band boundary.
    r_boundaries = sorted({r for lo, hi in r_bands for r in (lo, hi)})
    for r_val in r_boundaries:
        parts.append(_spine_circle(cx, cy, base_project, r_val,
                                   color=spine_color, width=spine_width))

    for chart, (r_lo, r_hi) in zip(charts, r_bands):
        st = _chart_state(chart)
        xlo, xhi = st["xlim"] if st["xlim"] is not None else (0.0, 1.0)
        ylo, yhi = st["ylim"] if st["ylim"] is not None else (0.0, 1.0)

        # Map the chart's data range to pixel space [0, iw] × [0, ih] (y flipped).
        # _warp_svg then back-projects pixels → [0, 1] × [0, 1] before re-projecting.
        def make_xscale(lo=xlo, hi=xhi):
            return lambda t: ((t - lo) / (hi - lo)) * iw
        def make_yscale(lo=ylo, hi=yhi):
            return lambda r: ih * (1.0 - (r - lo) / (hi - lo))
        x_scale = make_xscale()
        y_scale = make_yscale()

        def make_project(lo=r_lo, hi=r_hi):
            def project(t, r):
                return base_project(t, lo + r * (hi - lo))
            return project

        band_project = make_project()
        for a in st["artists"]:
            spec = get_artist(a["type"])
            if spec is None:
                continue
            ctx = RenderContext(
                x_scale=x_scale, y_scale=y_scale,
                iw=iw, ih=ih,
                color=a.get("_color"),
                defaults={}, dash={},
                project=None,
            )
            body = spec.draw(a, ctx)
            parts.append(coordinate.warp_svg(body, band_project, iw, ih))

    # `_diagram_inner` is the SVG body — no outer <svg>. The layout engine
    # wraps it in <g transform="translate(x,y)"> when composing; standalone
    # rendering wraps it in a fresh <svg> via _render_standalone_diagram.
    bg = f'<rect width="{width}" height="{height}" fill="white"/>'
    inner = bg + "".join(parts)

    leaf = Chart._new_sized_leaf(
        canvas_width=width, canvas_height=height,
        leaf_kind="diagram",
        margin={"left": 0, "right": 0, "top": 0, "bottom": 0},
    )
    leaf._diagram_inner = inner
    return leaf
