"""Custom artist: gene-arrow (directional feature track).

Each feature is a horizontal arrow with a body (rectangle) and a triangular
head pointing in the strand direction. Useful for genomics-style "where
on the genome / chromosome is each gene" tracks; also fine for any
directional interval data.

API: c.gene_arrow(starts, ends, strands, y=0, height=0.6, head_frac=0.25).
- `starts`, `ends` — interval bounds in data x units.
- `strands`        — +1 / -1 per feature; +1 points right, -1 points left.
- `y`              — data y baseline of the track.
- `height`         — feature thickness in data y units.
- `head_frac`      — fraction of feature length taken by the arrowhead.
- optional `labels` -> per-feature labels drawn above the body.
"""

SUMMARY = 'Directional rectangles with arrowheads, per strand — for genomics tracks.'
from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist
from plotlet.font import _text_path


def gene_arrow_record(args, kw):
    starts = _to_pylist(args[0])
    ends   = _to_pylist(args[1])
    strands = _to_pylist(args[2])
    return {"type": "gene_arrow", "starts": starts, "ends": ends,
            "strands": strands, "opts": kw}


def gene_arrow_xdomain(a):
    return list(a["starts"]) + list(a["ends"])


def gene_arrow_ydomain(a):
    y = a["opts"].get("y", 0)
    h = a["opts"].get("height", 0.6)
    return [y - h / 2, y + h / 2]


def gene_arrow_draw(a, ctx):
    col = ctx.color
    y = a["opts"].get("y", 0)
    h = a["opts"].get("height", 0.6)
    head_frac = a["opts"].get("head_frac", 0.25)
    labels = a["opts"].get("labels")
    y_top = ctx.y_scale(y + h / 2)
    y_bot = ctx.y_scale(y - h / 2)
    y_mid = (y_top + y_bot) / 2
    out = []
    for i, (s, e, st) in enumerate(zip(a["starts"], a["ends"], a["strands"])):
        x_s = ctx.x_scale(s); x_e = ctx.x_scale(e)
        if x_s > x_e:
            x_s, x_e = x_e, x_s
        length = x_e - x_s
        head_w = length * head_frac
        if st >= 0:
            body_l, body_r = x_s, x_e - head_w
            tip = x_e
            d = (f"M{body_l:.2f},{y_top:.2f} L{body_r:.2f},{y_top:.2f} "
                 f"L{body_r:.2f},{y_top - (y_top - y_bot) * 0.25:.2f} "
                 f"L{tip:.2f},{y_mid:.2f} "
                 f"L{body_r:.2f},{y_bot + (y_top - y_bot) * 0.25:.2f} "
                 f"L{body_r:.2f},{y_bot:.2f} L{body_l:.2f},{y_bot:.2f} Z")
        else:
            body_l, body_r = x_s + head_w, x_e
            tip = x_s
            d = (f"M{body_r:.2f},{y_top:.2f} L{body_l:.2f},{y_top:.2f} "
                 f"L{body_l:.2f},{y_top - (y_top - y_bot) * 0.25:.2f} "
                 f"L{tip:.2f},{y_mid:.2f} "
                 f"L{body_l:.2f},{y_bot + (y_top - y_bot) * 0.25:.2f} "
                 f"L{body_l:.2f},{y_bot:.2f} L{body_r:.2f},{y_bot:.2f} Z")
        out.append(f'<path d="{d}" fill="{col}"/>')
        if labels and i < len(labels) and labels[i]:
            out.append(_text_path(labels[i], (x_s + x_e) / 2, y_top - 4,
                                  10, anchor="middle"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="gene_arrow",
    record=gene_arrow_record,
    xdomain=gene_arrow_xdomain,
    ydomain=gene_arrow_ydomain,
    draw=gene_arrow_draw,
))


if __name__ == "__main__":
    starts  = [100,  450,  900, 1300, 1800]
    ends    = [380,  820, 1280, 1700, 2300]
    strands = [  1,    1,   -1,    1,   -1]
    labels  = ["geneA", "geneB", "geneC", "geneD", "geneE"]
    c = pt.chart(data_height=120)
    c.gene_arrow(starts, ends, strands, y=0, height=0.7, labels=labels)
    c.ylim(-0.7, 0.9).yticks([])
    c.title("Gene track").xlabel("position (bp)")
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
