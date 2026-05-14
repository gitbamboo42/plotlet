"""Custom artist: Cleveland dot plot.

A horizontal dot at each category, optionally with a thin connecting
line from the y-axis to the dot. Cleveland's empirical work on
chart-perception found dot plots more accurately read than horizontal
bars — same data, less ink, often clearer rank ordering.

API:
    c.cleveland_dot(labels, values, size=5,
                    line=True, line_color="#bbbbbb")

Pair with `c.yscale("category", order=labels)`. Labels appear on the
y-axis as normal category tick labels.
"""

SUMMARY = "Horizontal dot at each category — Cleveland's perception-tested alternative to barh."

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list


def cdot_record(args, kw):
    return {"type": "cleveland_dot",
            "labels": to_list(args[0]),
            "values": to_list(args[1]),
            "opts": kw}


def cdot_xdomain(a):
    return list(a["values"]) + [0]


def cdot_ydomain(a): return a["labels"]


def cdot_draw(a, ctx):
    col = ctx.color
    r = a["opts"].get("size", 5)
    line = a["opts"].get("line", True)
    line_col = a["opts"].get("line_color", "#bbbbbb")
    out = []
    x0 = ctx.x_scale(0) if min(a["values"]) >= 0 else ctx.x_scale(min(a["values"]))
    for label, v in zip(a["labels"], a["values"]):
        py = ctx.y_scale(label)
        px = ctx.x_scale(v)
        if line:
            out.append(
                f'<line x1="{0:.2f}" x2="{px:.2f}" y1="{py:.2f}" y2="{py:.2f}" '
                f'stroke="{line_col}" stroke-width="1"/>'
            )
        out.append(
            f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{r}" fill="{col}"/>'
        )
    return "".join(out)


def cdot_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    return (
        f'<line x1="{x0}" x2="{x0 + 22}" y1="{y_mid}" y2="{y_mid}" '
        f'stroke="#bbbbbb" stroke-width="1"/>'
        f'<circle cx="{x0 + 22}" cy="{y_mid}" r="4" fill="{col}"/>'
    )


pt.add_artist(pt.ArtistSpec(
    name="cleveland_dot",
    record=cdot_record,
    xdomain=cdot_xdomain,
    ydomain=cdot_ydomain,
    draw=cdot_draw,
    legend_swatch=cdot_legend_swatch,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    cats = ["Python", "JavaScript", "TypeScript", "Rust", "Go", "C++",
            "Java", "Ruby"]
    vals = [42, 38, 27, 18, 14, 11, 22, 7]
    c = pt.chart()
    c.yscale("category", order=cats)
    c.cleveland_dot(cats, vals)
    c.title("Stack share").xlabel("% respondents")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
