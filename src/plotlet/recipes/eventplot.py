"""Custom artist: eventplot (raster / tick).

A grid of short vertical (or horizontal) tick marks, one per event time.
Used for spike trains, sequence motif hits, log timelines — matplotlib's
`plt.eventplot`. Each call adds one *row* of ticks at a given y; call
multiple times for multiple rows.

API: c.eventplot(positions, y=0, length=0.6, orientation="vertical").
- `positions`  -> 1-D iterable of event times along the data axis.
- `y`          -> data-coord position of the row baseline.
- `length`     -> tick length in data units along the orthogonal axis.
- `orientation -> "vertical" (default; tick is vertical, row stacks on y)
                  or "horizontal" (tick is horizontal, row stacks on x).
"""

SUMMARY = 'Vertical or horizontal tick marks per row, for spike rasters / event timelines.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import segment


def eventplot_record(args, kw):
    return {"type": "eventplot", "pos": to_list(args[0]), "opts": kw}


def eventplot_xdomain(a):
    if a["opts"].get("orientation", "vertical") == "vertical":
        return a["pos"]
    y = a["opts"].get("y", 0); ln = a["opts"].get("length", 0.6)
    return [y - ln / 2, y + ln / 2]


def eventplot_ydomain(a):
    if a["opts"].get("orientation", "vertical") == "horizontal":
        return a["pos"]
    y = a["opts"].get("y", 0); ln = a["opts"].get("length", 0.6)
    return [y - ln / 2, y + ln / 2]


def eventplot_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.2)
    y = a["opts"].get("y", 0)
    ln = a["opts"].get("length", 0.6)
    orient = a["opts"].get("orientation", "vertical")
    out = []
    if orient == "vertical":
        y1 = ctx.y_scale(y - ln / 2)
        y2 = ctx.y_scale(y + ln / 2)
        for x in a["pos"]:
            px = ctx.x_scale(x)
            out.append(segment(px, y1, px, y2, color=col, width=lw))
    else:  # horizontal — `y` here is read as an x-coord baseline
        x1 = ctx.x_scale(y - ln / 2)
        x2 = ctx.x_scale(y + ln / 2)
        for p in a["pos"]:
            py = ctx.y_scale(p)
            out.append(segment(x1, py, x2, py, color=col, width=lw))
    return "".join(out)


def eventplot_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    return (
        segment(x0 + 4, y_mid - 5, x0 + 4, y_mid + 5, color=col)
        + segment(x0 + 10, y_mid - 5, x0 + 10, y_mid + 5, color=col)
        + segment(x0 + 14, y_mid - 5, x0 + 14, y_mid + 5, color=col)
        + segment(x0 + 19, y_mid - 5, x0 + 19, y_mid + 5, color=col)
    )


pt.add_artist(pt.ArtistSpec(
    name="eventplot",
    record=eventplot_record,
    xdomain=eventplot_xdomain,
    ydomain=eventplot_ydomain,
    draw=eventplot_draw,
    legend_entries=pt.legend_from_swatch(eventplot_legend_swatch),
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(4)
    n_rows = 8
    c = pt.chart(data_height=240)
    for i in range(n_rows):
        # Each row: ~30 events with rate ~1/sec, total 30s.
        t = 0
        events = []
        while t < 30:
            t += random.expovariate(1.0)
            if t < 30:
                events.append(t)
        c.eventplot(events, y=i, length=0.7, color="C0",
                    label="trial 0" if i == 0 else None)
    c.title("Spike raster").xlabel("time (s)").ylabel("trial")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
