"""Custom artist: per-position text labels rendered as a thin strip.

Paints one text label per category position along a thin attached
panel — column names above a heatmap, row names beside it, group
tags between split row groups in a `pt.grid` composition.

Why it's an artist (not just `xticks(labels=...)`). Tick labels are
suppressed by `share_x`/`share_y`'s default `hide_labels=True` along
joined-pair inner edges. That's the right call for axis decoration but
wrong for the "labels strip" use case, where the labels *are* the
content and must survive sharing. Rendering the labels as artist
glyphs (via `draw.text_path`) routes around the tick-label
suppression machinery entirely — no per-leaf opt-out, no asymmetric
joined-pair flag, no fight with `hide_labels`.

Side semantics. Labels sit on the strip's *inner* edge — the edge
pointing toward the host panel they describe. Pick `side=` accordingly:

  strip attached ABOVE host  →  side="bottom"  (default for orient="x")
  strip attached BELOW host  →  side="top"
  strip attached LEFT  of host → side="right" (default for orient="y")
  strip attached RIGHT of host → side="left"

API:

    c.labels_strip(data=df, position="col", label="col",
                   side="bottom", rotation=0,
                   fontsize=11, color="#222", pad=3)
    c.labels_strip(data=df, position="col", label="col",
                   orient="y", side="right", ...)

Empty / None entries in the label column are skipped (no glyph drawn).
"""

SUMMARY = "Per-category text labels as artist glyphs — bypasses share_x/share_y label hiding."
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import text_path, cap_height, descender


_VALID_SIDES = {"x": {"bottom", "top"}, "y": {"left", "right"}}
_DEFAULT_SIDE = {"x": "bottom", "y": "right"}


def labels_strip_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "labels_strip requires long-form input: "
            "c.labels_strip(data=df, position='col', label='col')."
        )
    data = kw.pop("data", None)
    position_col = kw.pop("position", None)
    label_col = kw.pop("label", None)
    if data is None or position_col is None or label_col is None:
        raise TypeError("labels_strip requires data=, position=, label=.")
    positions = to_list(data[position_col])
    labels = list(to_list(data[label_col]))
    if len(positions) != len(labels):
        raise ValueError(
            f"labels_strip: positions ({len(positions)}) and "
            f"labels ({len(labels)}) must be the same length."
        )
    orient = kw.get("orient", "x")
    if orient not in ("x", "y"):
        raise ValueError(
            f"labels_strip: orient= must be 'x' or 'y'; got {orient!r}."
        )
    side = kw.get("side") or _DEFAULT_SIDE[orient]
    if side not in _VALID_SIDES[orient]:
        raise ValueError(
            f"labels_strip: side={side!r} invalid for orient={orient!r}; "
            f"expected one of {sorted(_VALID_SIDES[orient])}."
        )
    return {
        "type": "labels_strip",
        "positions": positions,
        "labels": labels,
        "_orient": orient,
        "_side": side,
        "opts": kw,
    }


def labels_strip_xdomain(a):
    if a.get("_orient") == "y":
        return [0, 1]
    return list(a["positions"])


def labels_strip_ydomain(a):
    if a.get("_orient") == "y":
        return list(a["positions"])
    return [0, 1]


def labels_strip_draw(a, ctx):
    opts = a["opts"]
    fontsize = opts.get("fontsize", 11)
    color = opts.get("color", "#222")
    rotation = float(opts.get("rotation", 0))
    pad = float(opts.get("pad", 3))

    orient = a.get("_orient", "x")
    side = a["_side"]
    cat_scale  = ctx.y_scale if orient == "y" else ctx.x_scale
    orth_scale = ctx.x_scale if orient == "y" else ctx.y_scale

    # Panel bounds on the orthogonal axis in pixel space. y_scale flips
    # (data 0 → high pixel y) so take min/max of the two endpoints.
    o0 = orth_scale(0); o1 = orth_scale(1)
    o_lo, o_hi = min(o0, o1), max(o0, o1)

    cap = cap_height(fontsize)
    desc = descender(fontsize)

    out = []
    for pos, label in zip(a["positions"], a["labels"]):
        if label is None or label == "":
            continue
        s = str(label)
        cp = cat_scale(pos)

        if orient == "x":
            x = cp
            # When unrotated: anchor at horizontal midpoint of the column,
            # baseline `pad` px inside the inner edge. When rotated: switch
            # to an edge anchor so the rotated text body sits *inside* the
            # strip instead of straddling the anchor (half spilling into
            # the host panel). `rotation` uses the convention positive =
            # CCW; SVG's native `rotate()` is screen-CW so we negate when
            # emitting the transform.
            if side == "bottom":
                if rotation == 0:
                    anchor, y = "middle", o_hi - desc - pad
                else:
                    anchor, y = "start", o_hi - pad
            else:  # "top"
                if rotation == 0:
                    anchor, y = "middle", o_lo + cap + pad
                else:
                    anchor, y = "end", o_lo + pad
        else:  # orient == "y"
            # Horizontal text anchored against the inner vertical edge.
            # Vertical center of cap-box lines up with the category center.
            if side == "right":
                anchor = "end"
                x = o_hi - pad
            else:  # "left"
                anchor = "start"
                x = o_lo + pad
            y = cp + (cap - desc) / 2

        glyph = text_path(s, x, y, fontsize, anchor=anchor, color=color,
                          rotate=rotation)
        out.append(glyph)
    return "".join(out)


def labels_strip_frame_defaults(args, kw):
    """Auto-set the category scale on the position axis (matches `heatmap`),
    hide ticks and spines so only the artist glyphs remain. User overrides
    after the artist call still win — replay is in order."""
    # Long-form: dispatch sugar may hoist the first positional into data=,
    # but frame_defaults runs before that. Pull positions from data[position]
    # or fall back to args[0] (positional-data sugar) / kw["data"][...].
    if "data" in kw and "position" in kw:
        positions = to_list(kw["data"][kw["position"]])
    elif args and "position" in kw:
        positions = to_list(args[0][kw["position"]])
    else:
        positions = []
    orient = kw.get("orient", "x")
    out = [
        ("spines", [], {"top": False, "right": False,
                        "bottom": False, "left": False}),
    ]
    if orient == "x":
        out.append(("xscale", ["category"], {"order": positions, "padding": 0}))
        out.append(("xticks", [[]], {}))
        out.append(("yticks", [[]], {}))
    else:
        out.append(("yscale", ["category"], {"order": positions, "padding": 0}))
        out.append(("xticks", [[]], {}))
        out.append(("yticks", [[]], {}))
    return out


pt.add_artist(pt.ArtistSpec(
    name="labels_strip",
    record=labels_strip_record,
    xdomain=labels_strip_xdomain,
    ydomain=labels_strip_ydomain,
    draw=labels_strip_draw,
    frame_defaults=labels_strip_frame_defaults,
    uses_color_cycle=False,
    tight_domain=True,
))


def demo():
    """Annotated heatmap: clustered dendrogram on top, column-name strip
    between dendrogram and heatmap, row-name strip on the left.

    The labels strip is the load-bearing piece — it sits inside a
    `share_x` group with the heatmap and dendrogram but its labels still
    render, because they're artist glyphs rather than tick labels (which
    `share_x(hide_labels=True)` would suppress on joined-pair inner
    edges)."""
    import numpy as np
    from scipy.cluster.hierarchy import linkage, leaves_list
    rng = np.random.default_rng(0)
    n_rows, n_cols = 8, 10
    data = rng.standard_normal((n_rows, n_cols))
    col_names = [f"S{i+1}" for i in range(n_cols)]
    row_names = [f"G{i+1}" for i in range(n_rows)]

    # Cluster columns once; reorder data + labels so the heatmap and labels
    # strip render in dendrogram-leaf order. The dendrogram itself is fed
    # the ORIGINAL labels — scipy's leaf indices in Z point into the
    # pre-reorder column array, so labels[i] must still refer to original
    # column i. Plotlet doesn't auto-reorder (no implicit coupling
    # between panels) so the demo wires it explicitly.
    Z = linkage(data.T, method="single")
    order = leaves_list(Z)
    cols_clustered = [col_names[i] for i in order]
    data_clustered = data[:, order]

    hm = pt.chart(data_width="4in", data_height="3in")
    hm.heatmap(data_clustered, xticklabels=cols_clustered,
               yticklabels=row_names, cmap="RdBu_r", border=False)
    # Suppress the heatmap's own auto tick labels — the strips own them now.
    hm.xticks([]); hm.yticks([])

    # rotation=90 — column labels read vertically so narrow columns can
    # carry long labels without horizontal crowding. The artist itself
    # defaults to rotation=0; the caller picks per use case.
    cols_df = {"name": cols_clustered}
    rows_df = {"name": row_names}
    top_labels = pt.chart(data_height="0.5in")
    top_labels.labels_strip(cols_df, position="name", label="name",
                            side="bottom", rotation=90)

    tree = pt.chart(data_height="0.7in")
    tree.dendrogram(linkage=Z, orient="top", labels=col_names)

    left_labels = pt.chart(data_width="0.6in")
    left_labels.labels_strip(rows_df, position="name", label="name",
                             orient="y", side="right")

    # Attachment order: index 0 is innermost. Labels strip sits directly
    # above the heatmap; dendrogram stacks above the labels strip.
    hm.attach_above(top_labels)
    hm.attach_above(tree)
    hm.attach_left(left_labels)
    hm.title("Annotated heatmap")
    return hm


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
