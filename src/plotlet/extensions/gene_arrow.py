"""Custom artist: gene-arrow (directional feature track).

Each feature is a horizontal arrow with a body (rectangle) and a triangular
head pointing in the strand direction. Useful for genomics-style "where
on the genome / chromosome is each gene" tracks; also fine for any
directional interval data.

API: c.gene_arrow(data=df, start="col", end="col", strand="col",
                  label="col", at=0, height=0.6, head_frac=0.25).
- `start=`, `end=` — interval bound columns in data x units.
- `strand=`        — column of +1 / -1 per feature (+1 points right).
- `label=`         — optional column of per-feature labels drawn above
                     the body.
- `at`             — scalar data-y baseline of the track (default 0;
                     intrinsically 1-D so this is placement, not a col).
- `height`         — feature thickness in data y units.
- `head_frac`      — fraction of feature length taken by the arrowhead.
"""

SUMMARY = 'Directional rectangles with arrowheads, per strand — for genomics tracks.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import path, text_path
from ..draw import coord



def gene_arrow_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "gene_arrow requires long-form input: "
            "c.gene_arrow(data=df, start='col', end='col', strand='col')."
        )
    data = kw.pop("data", None)
    start_col = kw.pop("start", None)
    end_col = kw.pop("end", None)
    strand_col = kw.pop("strand", None)
    if data is None or start_col is None or end_col is None or strand_col is None:
        raise TypeError("gene_arrow requires data=, start=, end=, strand=.")
    label_col = kw.pop("label", None)
    if label_col is not None:
        kw["labels"] = [str(v) for v in to_list(data[label_col])]
    return {"type": "gene_arrow",
            "starts": to_list(data[start_col]),
            "ends": to_list(data[end_col]),
            "strands": to_list(data[strand_col]),
            "opts": kw}


def gene_arrow_xdomain(a):
    return list(a["starts"]) + list(a["ends"])


def gene_arrow_ydomain(a):
    y = a["opts"].get("at", 0)
    h = a["opts"].get("height", 0.6)
    return [y - h / 2, y + h / 2]


def gene_arrow_draw(a, ctx):
    col = ctx.color
    y = a["opts"].get("at", 0)
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
            d = (f"M{coord(body_l)},{coord(y_top)} L{coord(body_r)},{coord(y_top)} "
                 f"L{coord(body_r)},{coord(y_top - (y_top - y_bot) * 0.25)} "
                 f"L{coord(tip)},{coord(y_mid)} "
                 f"L{coord(body_r)},{coord(y_bot + (y_top - y_bot) * 0.25)} "
                 f"L{coord(body_r)},{coord(y_bot)} L{coord(body_l)},{coord(y_bot)} Z")
        else:
            body_l, body_r = x_s + head_w, x_e
            tip = x_s
            d = (f"M{coord(body_r)},{coord(y_top)} L{coord(body_l)},{coord(y_top)} "
                 f"L{coord(body_l)},{coord(y_top - (y_top - y_bot) * 0.25)} "
                 f"L{coord(tip)},{coord(y_mid)} "
                 f"L{coord(body_l)},{coord(y_bot + (y_top - y_bot) * 0.25)} "
                 f"L{coord(body_l)},{coord(y_bot)} L{coord(body_r)},{coord(y_bot)} Z")
        out.append(path(d, fill=col))
        if labels and i < len(labels) and labels[i]:
            out.append(text_path(labels[i], (x_s + x_e) / 2, y_top - 4,
                                  10, anchor="middle"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="gene_arrow",
    record=gene_arrow_record,
    xdomain=gene_arrow_xdomain,
    ydomain=gene_arrow_ydomain,
    draw=gene_arrow_draw,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    df = {
        "start":  [100,  450,  900, 1300, 1800],
        "end":    [380,  820, 1280, 1700, 2300],
        "strand": [  1,    1,   -1,    1,   -1],
        "name":   ["geneA", "geneB", "geneC", "geneD", "geneE"],
    }
    c = pt.chart(data_height=120)
    c.gene_arrow(df, start="start", end="end", strand="strand", label="name",
                 at=0, height=0.7)
    c.ylim(-0.7, 0.9).yticks([])
    c.title("Gene track").xlabel("position (bp)")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
