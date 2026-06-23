"""Matrix chord diagrams — reproduction of pycirclize's chord_diagram
examples 1-1 (3 × 6), 1-2 (10 × 10), 1-3 (10 × 2).

Reference: https://moshi4.github.io/pyCirclize/chord_diagram/

Each pycirclize ``Circos.chord_diagram(matrix_df, ...)`` collapses three
operations into one call: sector layout (one sector per row + col
label, length = row_sum + col_sum), slot allocation (each non-zero
M[i, j] reserves a width-v slot on sector i for outgoing and on
sector j for incoming), and ribbon rendering. plotlet keeps those
layers separate — the small helper below handles layout + slots, then
the ``chord_ribbon`` artist renders the ribbons in a CircularCoordinate
inner disc.
"""
from pathlib import Path

import pandas as pd

import plotlet as pt
import plotlet.extensions.chord_ribbon       # noqa
import plotlet.extensions.annotation_strip   # noqa


def _palette(cmap_name: str, n: int) -> list[str]:
    """Sample `n` evenly-spaced colors from a named colormap. Single-step
    point per sector keeps colors stable as the matrix size changes."""
    lut = pt.draw.colormap_lut(cmap_name)
    out = []
    for j in range(n):
        i = int(j * 255 / max(n - 1, 1))
        out.append(f"#{lut[i*3]:02x}{lut[i*3+1]:02x}{lut[i*3+2]:02x}")
    return out


def matrix_to_chord(matrix_df: pd.DataFrame):
    """Turn a matrix DataFrame into (sector_names, sector_lengths, ribbons).

    Sector order = rows first, then columns (skipping any column label
    already in the row index — the symmetric case in example 1-2 where
    rows == cols collapses to one sector per label).

    Each sector's length = row_sum + col_sum. Within a sector, outgoing
    slots are packed first in row-iteration order; incoming slots
    follow, packed in column-iteration order. That layout matches the
    convention pycirclize / circlize use and keeps related ribbons
    bunched together visually.

    ``ribbons`` columns: ``src``, ``dst``, ``value``,
    ``x1a`` / ``x1b`` (src endpoints, global x), ``x2a`` / ``x2b`` (dst
    endpoints, global x). Positions are pre-offset into the global
    coordinate, so the chord_ribbon artist needs no sector remap.
    """
    # Slot allocation mirrors pycirclize's `parser.matrix.Matrix.__init__`:
    # iterate the matrix REVERSED (bottom-right to top-left), with a
    # SINGLE cumulative counter per sector — outgoing and incoming share
    # the same offset. On the col side the slot is emitted with
    # `start > end` (reversed direction) so when chord_ribbon connects
    # start↔start / end↔end the ribbon edges run parallel along the
    # natural sweep instead of knotting up. Self-loops (row==col) keep
    # both slots forward but offset by `value` to leave a gap between
    # outgoing and incoming halves on the same sector.
    rows = list(matrix_df.index)
    cols = list(matrix_df.columns)
    sector_names = list(rows)
    for c in cols:
        if c not in sector_names:
            sector_names.append(c)

    name2size = {n: 0.0 for n in sector_names}
    rows_out = []
    for r in reversed(rows):
        for c in reversed(cols):
            v = float(matrix_df.loc[r, c])
            if v <= 0:
                continue
            row_size = name2size[r]
            col_size = name2size[c]
            if r == c:                                  # self-loop
                x1a, x1b = row_size, row_size + v
                x2a, x2b = col_size + 2 * v, col_size + v
            else:
                x1a, x1b = row_size, row_size + v
                x2a, x2b = col_size + v, col_size       # reversed direction
            rows_out.append({
                "src": r, "dst": c, "value": v,
                "x1a": x1a, "x1b": x1b, "x2a": x2a, "x2b": x2b,
            })
            name2size[r] += v
            name2size[c] += v

    sector_lengths = [name2size[n] for n in sector_names]
    return sector_names, sector_lengths, pd.DataFrame(rows_out)


def _build_chord(matrix_df, *, cmap, gap=4, r_inner=0.93,
                 size=800, label_fontsize=12, edge_color=None,
                 edge_width=0.0, alpha=0.6, alpha_handler=None):
    """Compose the standard 2-layer chord diagram: ring with sector
    chrome on the outside, ribbons on the inside disc.

    ``alpha_handler`` (``f(src, dst) -> alpha``) — example 1-3 uses this
    to highlight a subset by sorting ribbons into low-α / high-α
    buckets so the highlighted set draws on top.
    """
    sector_names, sector_lengths, ribbons = matrix_to_chord(matrix_df)
    palette = dict(zip(sector_names, _palette(cmap, len(sector_names))))
    XL = (0, sum(sector_lengths))
    sectors_spec = pt.Sectors(
        names=sector_names, lengths=sector_lengths, gap=gap,
        fontsize=label_fontsize,
    )

    arcs = pt.chart(ribbons, xlim=XL, data_width=size, data_height=size)
    arcs.sectors(sectors_spec, column="src", label=False)

    if alpha_handler is None:
        arcs.chord_ribbon(
            x1_start="x1a", x1_end="x1b", x2_start="x2a", x2_end="x2b",
            x1_sector="src", x2_sector="dst",
            color="src", palette=palette,
            alpha=alpha, edge_color=edge_color, edge_width=edge_width,
        )
    else:
        # Two passes — low alpha first (background), high alpha last
        # (highlighted, draws on top). Matches pycirclize's zorder kwarg
        # in example 1-3.
        ribbons["alpha"] = [alpha_handler(r, d)
                            for r, d in zip(ribbons["src"], ribbons["dst"])]
        for a in sorted(ribbons["alpha"].unique()):
            sub = ribbons[ribbons["alpha"] == a].reset_index(drop=True)
            arcs.chord_ribbon(
                data=sub,
                x1_start="x1a", x1_end="x1b",
                x2_start="x2a", x2_end="x2b",
                x1_sector="src", x2_sector="dst",
                color="src", palette=palette,
                alpha=float(a),
                edge_color=edge_color, edge_width=edge_width,
            )

    # Colored sector strip on the ring — one filled segment per sector
    # in the sector's assigned palette color, with the sector name
    # rendered inside the band. matches pycirclize's chord_diagram
    # sector-rim look (`label_kws=dict(color="white", ...)`).
    #
    # `start`/`end` are LOCAL (per-sector) — the framework's sector
    # remap adds each row's sector offset on the way in (and tags each
    # value with its sector index, so the right-edge of sector i and
    # the left-edge of sector i+1 land on distinct pixels).
    strip_df = pd.DataFrame({
        "name":  sector_names,
        "start": [0.0] * len(sector_names),
        "end":   list(sector_lengths),
    })
    ring = pt.chart(strip_df, xlim=XL, ylim=(0, 1),
                    data_width=size, data_height=size)
    ring.sectors(sectors_spec, column="name", label=False)
    ring.annotation_strip(x1="start", x2="end", value="name",
                          palette=palette, text=True,
                          text_color="white", fontsize=label_fontsize)
    return pt.grid([[ring]]).coordinate(
        # gap=0.01 keeps the ring close to the canvas edge (default 0.05
        # leaves ~5% of canvas radius empty as outer margin).
        pt.CircularCoordinate(r_inner=r_inner, inner=arcs, gap=0.01)
    )


def _build_linear(matrix_df, *, cmap, gap=4, width=900, ribbon_h=140,
                  strip_h=30, label_fontsize=11, edge_color=None,
                  edge_width=0.0, alpha=0.6, alpha_handler=None):
    """Linear unroll of the matrix chord diagram: a colored sector strip
    on top, ribbons arching between intervals on the same baseline below.

    `share_x` glues the two panels so sector chrome lines up. The
    ribbon panel sets its own xlim to the full sector span; the artist
    handles the linear-bow draw path on a Cartesian coord.
    """
    sector_names, sector_lengths, ribbons = matrix_to_chord(matrix_df)
    palette = dict(zip(sector_names, _palette(cmap, len(sector_names))))
    XL = (0, sum(sector_lengths))
    sectors_spec = pt.Sectors(
        names=sector_names, lengths=sector_lengths, gap=gap,
        fontsize=label_fontsize, rotation=0,
    )
    # `start`/`end` are LOCAL — see the circular builder above.
    strip_df = pd.DataFrame({
        "name":  sector_names,
        "start": [0.0] * len(sector_names),
        "end":   list(sector_lengths),
    })

    p_strip = pt.chart(strip_df, xlim=XL, data_width=width, data_height=strip_h)
    p_strip.sectors(sectors_spec, column="name", label=False)
    p_strip.annotation_strip(x1="start", x2="end", value="name",
                             palette=palette, text=True,
                             text_color="white", fontsize=label_fontsize)

    p_arc = pt.chart(ribbons, xlim=XL, data_width=width, data_height=ribbon_h)
    p_arc.sectors(sectors_spec, column="src", label=False)
    if alpha_handler is None:
        p_arc.chord_ribbon(
            x1_start="x1a", x1_end="x1b", x2_start="x2a", x2_end="x2b",
            x1_sector="src", x2_sector="dst",
            color="src", palette=palette,
            alpha=alpha, edge_color=edge_color, edge_width=edge_width,
        )
    else:
        ribbons["alpha"] = [alpha_handler(r, d)
                            for r, d in zip(ribbons["src"], ribbons["dst"])]
        for a in sorted(ribbons["alpha"].unique()):
            sub = ribbons[ribbons["alpha"] == a].reset_index(drop=True)
            p_arc.chord_ribbon(
                data=sub,
                x1_start="x1a", x1_end="x1b",
                x2_start="x2a", x2_end="x2b",
                x1_sector="src", x2_sector="dst",
                color="src", palette=palette,
                alpha=float(a),
                edge_color=edge_color, edge_width=edge_width,
            )
    # Strip BELOW, arcs ABOVE — same layering as hg38_chord's linear
    # unroll. Arc baseline (y=0) sits at the bottom of its panel, right
    # against the strip's top edge, so arc roots face the strip.
    return p_strip.attach_above(p_arc, gap=0)


def example_1_1():
    """3 × 6 matrix (circlize-doc reference)."""
    row_names = ["S1", "S2", "S3"]
    col_names = ["E1", "E2", "E3", "E4", "E5", "E6"]
    matrix_data = [
        [4, 14, 13, 17, 5, 2],
        [7, 1, 6, 8, 12, 15],
        [9, 10, 3, 16, 11, 18],
    ]
    df = pd.DataFrame(matrix_data, index=row_names, columns=col_names)
    return _build_chord(df, cmap="tab10", gap=5, r_inner=0.93,
                        edge_color="#000", edge_width=0.5, alpha=0.7)


def example_1_2():
    """10 × 10 matrix (rows == cols, so 10 sectors not 20)."""
    row_names = list("ABCDEFGHIJ")
    matrix_data = [
        [ 51, 115,  60,  17, 120, 126, 115, 179, 127, 114],
        [108, 138, 165, 170,  85, 221,  75, 107, 203,  79],
        [108,  54,  72, 123,  84, 117, 106, 114,  50,  27],
        [ 62, 134,  28, 185, 199, 179,  74,  94, 116, 108],
        [211, 114,  49,  55, 202,  97,  10,  52,  99, 111],
        [ 87,   6, 101, 117, 124, 171, 110,  14, 175, 164],
        [167,  99, 109, 143,  98,  42,  95, 163, 134,  78],
        [ 88,  83, 136,  71, 122,  20,  38, 264, 225, 115],
        [145,  82,  87, 123, 121,  55,  80,  32,  50,  12],
        [122, 109,  84,  94, 133,  75,  71, 115,  60, 210],
    ]
    df = pd.DataFrame(matrix_data, index=row_names, columns=row_names)
    return _build_chord(df, cmap="tab10", gap=3, r_inner=0.93,
                        alpha=0.5)


def example_1_3():
    """10 × 2 matrix with selective row-source highlighting."""
    row_names = list("ABCDEFGHIJ")
    col_names = list("KL")
    matrix_data = [
        [ 83,  79], [ 90, 118], [165,  81], [121,  77],
        [187, 197], [177,   8], [141, 127], [ 29,  27],
        [ 95,  82], [107,  39],
    ]
    df = pd.DataFrame(matrix_data, index=row_names, columns=col_names)
    highlight = {"C", "G"}

    def alpha_handler(src, dst):
        return 0.5 if src in highlight else 0.1

    return _build_chord(df, cmap="Set3", gap=2, r_inner=0.93,
                        edge_color="#000", edge_width=0.5,
                        alpha_handler=alpha_handler)


def example_1_1_linear():
    """Linear unroll of example 1-1, same matrix + same colors."""
    row_names = ["S1", "S2", "S3"]
    col_names = ["E1", "E2", "E3", "E4", "E5", "E6"]
    matrix_data = [
        [4, 14, 13, 17, 5, 2],
        [7, 1, 6, 8, 12, 15],
        [9, 10, 3, 16, 11, 18],
    ]
    df = pd.DataFrame(matrix_data, index=row_names, columns=col_names)
    return _build_linear(df, cmap="tab10", gap=5,
                         edge_color="#000", edge_width=0.5, alpha=0.7)


if __name__ == "__main__":
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    for name, builder in [
        ("chord_matrix_3x6.svg",          example_1_1),
        ("chord_matrix_10x10.svg",        example_1_2),
        ("chord_matrix_10x2.svg",         example_1_3),
        ("chord_matrix_3x6_linear.svg",   example_1_1_linear),
    ]:
        path = out_dir / name
        builder().save_svg(str(path))
        print(f"wrote {path}")
