"""Custom artist: feature_strip — colored rectangles spanning x-intervals.

For interval-style annotations: cytogenetic bands, gene / exon features,
ChIP peaks, highlight regions. Each row of the long-form data is one
filled rectangle spanning ``[x1, x2]`` over the full y range of the panel.

Pairs with ``annotation_strip`` — same "thin track" idiom, different
data shape:

- ``annotation_strip``: N **positions**, each with a value / cmap / text.
- ``feature_strip``:    N **intervals** ``(x1, x2)``, each with a category color.

API::

    # all rows one color
    c.feature_strip(data=df, x1='start', x2='end', color='#888')

    # category → color via palette dict
    c.feature_strip(data=df, x1='start', x2='end',
                    color='stain', palette={'gneg': '#fff', ...})

Coord-native — works in a `CircularCoordinate` ring leaf (cytobands
on the outer rim) and in flat panels. Sector remap picks up `x1` /
`x2` automatically when ``c.sectors(column='chrom')`` is active.
"""

SUMMARY = "Filled rectangles spanning x-intervals — cytobands, gene tracks, ChIP peaks, highlight regions."

from pathlib import Path

import plotlet as pt
from plotlet.draw import rect, TAB10
from plotlet.utils import to_list, resolve_aes, palette_color


def _feature_strip_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "feature_strip requires long-form input: "
            "c.feature_strip(data=df, x1='col', x2='col')."
        )
    data  = kw.pop("data", None)
    x1_col = kw.pop("x1", None)
    x2_col = kw.pop("x2", None)
    if data is None or x1_col is None or x2_col is None:
        raise TypeError("feature_strip requires data=, x1=, x2=.")
    color   = kw.pop("color", None)
    palette = kw.pop("palette", None)
    xs1 = to_list(data[x1_col])
    xs2 = to_list(data[x2_col])

    color_kind, color_value = resolve_aes(data, color)
    if color_kind != "column":
        opts = dict(kw)
        if color_value is not None:
            opts["color"] = color_value
        return {"type": "feature_strip", "xs1": xs1, "xs2": xs2,
                "colors": None, "opts": opts}

    # Categorical color: resolve each row to its color at record time.
    # Single record (no per-level split) — feature_strip rows are often
    # dense (hundreds–thousands), so splitting would explode the artist
    # count without buying anything.
    color_vec = list(color_value)
    levels = list(dict.fromkeys(color_vec))
    row_colors = []
    for v in color_vec:
        idx = levels.index(v)
        c = palette_color(palette, v, idx) or TAB10[idx % 10]
        row_colors.append(c)
    return {"type": "feature_strip", "xs1": xs1, "xs2": xs2,
            "colors": row_colors, "opts": dict(kw)}


def _feature_strip_xdomain(a):
    return list(a["xs1"]) + list(a["xs2"])


def _feature_strip_ydomain(a):
    # Strip fills the orthogonal axis; y-data is degenerate.
    return [0, 1]


def _feature_strip_draw(a, ctx):
    opts = a["opts"]
    alpha = opts.get("alpha", 1.0)
    default_color = ctx.color
    row_colors = a["colors"]
    y0 = ctx.y_scale(0)
    y1 = ctx.y_scale(1)
    y_top = min(y0, y1)
    h     = abs(y1 - y0)
    out = []
    for i, (x1, x2) in enumerate(zip(a["xs1"], a["xs2"])):
        x1_px = ctx.x_scale(x1)
        x2_px = ctx.x_scale(x2)
        x_left = min(x1_px, x2_px)
        w = abs(x2_px - x1_px)
        fill = row_colors[i] if row_colors else default_color
        out.append(rect(x_left, y_top, w, h, fill=fill, alpha=alpha,
                        project=ctx.warp))
    return "".join(out)


def _feature_strip_frame_defaults(args, kw):
    # Nothing meaningful on the y-axis — feature_strip is a thin track
    # spanning the panel's full y-range, with categories encoded by
    # fill color. Spines stay on (they frame the track visually) but
    # y-ticks and ylabel drop out.
    return [
        ("yticks", [[]], {}),
        ("ylabel", [""], {}),
    ]


pt.add_artist(pt.ArtistSpec(
    name="feature_strip",
    record=_feature_strip_record,
    xdomain=_feature_strip_xdomain,
    ydomain=_feature_strip_ydomain,
    draw=_feature_strip_draw,
    frame_defaults=_feature_strip_frame_defaults,
    coord_native=True,
    tight_domain=True,
))


def demo():
    """Linear cytoband-style demo: a few colored intervals along an axis."""
    import pandas as pd
    df = pd.DataFrame({
        "start": [0, 25, 50, 75, 90],
        "end":   [25, 50, 75, 90, 100],
        "kind":  ["a", "b", "a", "c", "b"],
    })
    c = pt.chart(df, xlim=(0, 100), data_height=40)
    c.feature_strip(x1="start", x2="end", color="kind",
                    palette={"a": "#888", "b": "#000", "c": "#d92626"})
    c.title("Feature strip").xlabel("position").yticks([])
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
