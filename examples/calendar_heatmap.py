"""Custom artist: calendar heatmap (GitHub-style contribution graph).

A grid of colored cells, one per day, laid out as weeks (columns) ×
weekdays (rows) with each week's column spanning all 7 days in
chronological order. Values map through a colormap.

API: c.calendar_heatmap(dates, values, cmap="Greens", vmin=None, vmax=None).
`dates` is an iterable of `datetime.date` (or `datetime.datetime`); `values`
aligns 1-to-1 with dates.
"""

SUMMARY = 'GitHub-style daily contribution grid, weeks × weekdays.'
import datetime
from pathlib import Path

import plotlet as pt
from plotlet.colormaps import colormap, _ContinuousNorm
from plotlet._spec import _D
from plotlet.font import _text_path


def calhm_record(args, kw):
    dates = list(args[0])
    values = list(args[1])
    if not dates:
        return {"type": "calendar_heatmap", "weeks": 0, "_grid": [], "opts": kw}
    # Anchor at the Monday of the week containing the first date.
    d0 = min(dates)
    start = d0 - datetime.timedelta(days=d0.weekday())
    d_last = max(dates)
    end = d_last + datetime.timedelta(days=(6 - d_last.weekday()))
    n_weeks = ((end - start).days // 7) + 1
    grid = [[None] * 7 for _ in range(n_weeks)]
    by_date = {d: v for d, v in zip(dates, values)}
    for w in range(n_weeks):
        for wd in range(7):
            day = start + datetime.timedelta(weeks=w, days=wd)
            if day in by_date:
                grid[w][wd] = by_date[day]
    flat = [v for row in grid for v in row if v is not None]
    vmin = kw.get("vmin", min(flat) if flat else 0.0)
    vmax = kw.get("vmax", max(flat) if flat else 1.0)
    return {"type": "calendar_heatmap", "weeks": n_weeks, "_grid": grid,
            "_start": start, "_vmin": vmin, "_vmax": vmax, "opts": kw}


def calhm_xdomain(a):
    return [0, a["weeks"]]


def calhm_ydomain(a):
    return [0, 7]


def calhm_draw(a, ctx):
    cmap = colormap(a["opts"].get("cmap", "Greens"))
    norm = _ContinuousNorm(a["_vmin"], a["_vmax"], "linear")
    pad = a["opts"].get("pad", 1)
    out = []
    # Cell width / height in pixels, from the scale's mapping of integer steps.
    x_step = ctx.x_scale(1) - ctx.x_scale(0)
    y_step = ctx.y_scale(1) - ctx.y_scale(0)  # negative — y grows down in svg
    cw = abs(x_step) - pad
    ch = abs(y_step) - pad
    miss = a["opts"].get("missing_color", "#f2f2f2")
    for w in range(a["weeks"]):
        for wd in range(7):
            x = ctx.x_scale(w)
            # Put Monday at top by mapping wd via (7 - wd - 1).
            y = ctx.y_scale(7 - wd - 1)
            v = a["_grid"][w][wd]
            if v is None:
                fill = miss
            else:
                r, g, b = cmap(norm.to_unit(v))
                fill = f"rgb({r},{g},{b})"
            out.append(
                f'<rect x="{min(x, x + x_step) + pad / 2:.2f}" '
                f'y="{min(y, y + y_step) + pad / 2:.2f}" '
                f'width="{cw:.2f}" height="{ch:.2f}" fill="{fill}"/>'
            )
    # Weekday labels along the left.
    labels = a["opts"].get("weekday_labels", ["Mon", "", "Wed", "", "Fri", "", "Sun"])
    for wd, label in enumerate(labels):
        if not label:
            continue
        y = ctx.y_scale(7 - wd - 1) + y_step / 2
        x_left = ctx.x_scale(0) - 4
        out.append(_text_path(label, x_left, y + 3, 9, anchor="end"))
    return "".join(out)


def calhm_legend_gradient(a):
    return {"kind": "continuous",
            "cmap": a["opts"].get("cmap", "Greens"),
            "vmin": a["_vmin"], "vmax": a["_vmax"], "norm": "linear",
            "label": a["opts"].get("legend_label", "contributions")}


pt.add_artist(pt.ArtistSpec(
    name="calendar_heatmap",
    record=calhm_record,
    xdomain=calhm_xdomain,
    ydomain=calhm_ydomain,
    draw=calhm_draw,
    uses_color_cycle=False,
    legend_gradient=calhm_legend_gradient,
    tight_domain=True,
))


if __name__ == "__main__":
    import random
    random.seed(5)
    start = datetime.date(2025, 1, 6)  # a Monday
    n_days = 7 * 26  # half a year
    dates = [start + datetime.timedelta(days=i) for i in range(n_days)]
    values = [max(0, int(random.gauss(2.5, 2.0))) for _ in dates]
    c = pt.chart(data_width=560, data_height=140)
    c.calendar_heatmap(dates, values, cmap="Greens")
    c.title("Daily activity (first half of 2025)")
    c.yticks([]); c.xticks([])
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
