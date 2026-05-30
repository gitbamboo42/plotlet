"""Custom artist: per-position text labels rendered as a thin strip.

Marsilea calls the equivalent `Labels`; ComplexHeatmap calls it
`anno_text`. The job: paint one text label per category position along
a thin attached panel — column names above a heatmap, row names beside
it, group tags between split row groups in a `pt.grid` composition.

Why it's an artist (not just `xticks(labels=...)`). Tick labels are
suppressed by `share_x`/`share_y`'s default `hide_labels=True` along
joined-pair inner edges. That's the right call for axis decoration but
wrong for the "labels strip" use case, where the labels *are* the
content and must survive sharing. Rendering the labels as artist
glyphs (via `draw.text_path`) routes around the tick-label
suppression machinery entirely — no per-leaf opt-out, no asymmetric
joined-pair flag, no fight with `hide_labels`.

Side semantics. Labels sit on the strip's *inner* edge — the edge
pointing toward the host panel they describe — matching the
marsilea/ComplexHeatmap convention. Pick `side=` accordingly:

  strip attached ABOVE host  →  side="bottom"  (default for orient="x")
  strip attached BELOW host  →  side="top"
  strip attached LEFT  of host → side="right" (default for orient="y")
  strip attached RIGHT of host → side="left"

API:

    c.labels_strip(positions, labels, side="bottom", rotation=0,
                   fontsize=11, color="#222", pad=3)
    c.labels_strip(positions, labels, orient="y", side="right", ...)

Empty / None entries in `labels` are skipped (no glyph drawn).
"""

SUMMARY = "Per-category text labels as artist glyphs — bypasses share_x/share_y label hiding."
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import text_path, cap_height, descender


_VALID_SIDES = {"x": {"bottom", "top"}, "y": {"left", "right"}}
_DEFAULT_SIDE = {"x": "bottom", "y": "right"}


def labels_strip_record(args, kw):
    if len(args) < 2:
        raise TypeError(
            "labels_strip requires (positions, labels); "
            "got %d positional arg(s)." % len(args)
        )
    positions = to_list(args[0])
    labels = list(args[1])
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
            anchor = "middle"
            x = cp
            # Baseline anchored to the inner edge with `pad` px of breathing
            # room. "bottom" → baseline near panel bottom, glyphs extend up.
            # "top" → baseline `cap` px below panel top, glyphs reach the top.
            if side == "bottom":
                y = o_hi - desc - pad
            else:  # "top"
                y = o_lo + cap + pad
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

        glyph = text_path(s, x, y, fontsize, anchor=anchor, color=color)
        if rotation != 0:
            # Rotate around the anchor point — same approach as the marsilea
            # text.py workaround. Replaceable once `text_path` grows a native
            # `rotate=` kwarg (separate todo).
            glyph = (f'<g transform="rotate({rotation:.2f} {x:.2f} {y:.2f})">'
                     f'{glyph}</g>')
        out.append(glyph)
    return "".join(out)


def labels_strip_frame_defaults(args, kw):
    """Auto-set the category scale on the position axis (matches `heatmap`),
    hide ticks and spines so only the artist glyphs remain. User overrides
    after the artist call still win — replay is in order."""
    positions = to_list(args[0])
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
    """Reproduce the marsilea minimal figure: heatmap + top labels strip
    + top dendrogram + left labels strip, all sharing the categorical
    axes.

    The labels strip is the load-bearing piece: it sits between the
    dendrogram and the heatmap with labels hugging the heatmap on its
    BOTTOM (inner) edge. Default `share_x(hide_labels=True)` would
    silence those labels if they were tick labels — but they're artist
    glyphs, so they render regardless. The dendrogram above continues
    to render with its own conventions, no `xticks([])` workaround
    needed."""
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
               yticklabels=row_names, cmap="RdBu_r")
    # Suppress the heatmap's own auto tick labels — the strips own them now.
    hm.xticks([]); hm.yticks([])

    top_labels = pt.chart(data_height="0.35in")
    top_labels.labels_strip(cols_clustered, cols_clustered, side="bottom")

    tree = pt.chart(data_height="0.7in")
    tree.dendrogram(linkage=Z, orient="top", labels=col_names)

    left_labels = pt.chart(data_width="0.6in")
    left_labels.labels_strip(row_names, row_names, orient="y", side="right")

    # Attachment order: index 0 is innermost. Labels strip sits directly
    # above the heatmap; dendrogram stacks above the labels strip.
    hm.attach_above(top_labels)
    hm.attach_above(tree)
    hm.attach_left(left_labels)
    hm.title("plotlet labels_strip + dendrogram + heatmap")
    return hm


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
