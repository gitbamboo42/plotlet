"""Baseline SVG regression tests for the heatmap artist/topic.

    pytest tests/test_chart_heatmap.py
    pytest tests/test_chart_heatmap.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest
from _chart_helpers import _big_continuous_heatmap, _by_label, _mock_tidy_df, _tidy_heatmap


def chart_heatmap_labeled():
    # Long-form heatmap: string `x` column → categorical x band labels,
    # value columns → track rows.
    data = [[math.sin(r * 0.6) * math.cos(c * 0.4) for c in range(8)]
            for r in range(6)]
    rows = [f"r{i}" for i in range(6)]
    cols = [f"c{i}" for i in range(8)]

    c = pt.chart(title="heatmap (labeled rows/cols)",
                 xlabel="condition", ylabel="sample")
    c.add_heatmap(data=_tidy_heatmap(data, cols, rows, xname="condition"), mapping=aes(x="condition"), values=rows, cmap="viridis")
    c.legend()
    return c


def chart_heatmap_dataframe():
    rng = random.Random(1)
    n_rows, n_cols = 5, 7
    values = [[rng.gauss(0, 1) for _ in range(n_cols)] for _ in range(n_rows)]
    samples  = [f"sample_{i}" for i in range(n_rows)]
    features = [f"feature_{j}" for j in range(n_cols)]
    tidy = _tidy_heatmap(values, features, samples, xname="feature")

    c = pt.chart(title="heatmap (DataFrame branch, diverging cmap)")
    c.add_heatmap(data=_mock_tidy_df(tidy), mapping=aes(x="feature"), values=samples,
              cmap="bwr", center=0)
    c.xticks(rotation=45)
    c.legend()
    return c


def chart_heatmap_annot():
    # annot=True overlays each cell's value; annot_color="auto" picks
    # white text on dark cells, black on light, via luminance. Inline
    # colorbar via chart.legend(True) — auto-flips inside → right for
    # the gradient — the canonical correlation-matrix look without the
    # composition workaround.
    n = 6
    data = [[math.cos((i - j) * 0.4) for j in range(n)] for i in range(n)]
    labels = [f"v{i}" for i in range(n)]

    c = pt.chart(title="correlation matrix (annot=True)")
    c.add_heatmap(data=_tidy_heatmap(data, labels, labels, xname="var"), mapping=aes(x="var"), values=labels,
              cmap="RdBu_r", vmin=-1, vmax=1, annot=True, fmt="+.2f",
              legend={"label": "corr"})
    c.legend(True)
    return c


def chart_heatmap_categorical():
    rows    = ["R1", "R2", "R3", "R4", "R5"]
    samples = ["S1", "S2", "S3", "S4", "S5", "S6"]
    matrix = [
        ["Alpha", "None",   "Gamma", "None",   "Alpha", None    ],
        ["None",  "Beta",   "None",  "Alpha",  "None",  "Delta" ],
        ["Delta", "None",   "None",  "Delta",  "Beta",  "None"  ],
        ["None",  "Alpha",  "Delta", None,     "None",  "Alpha" ],
        ["Beta",  "Delta",  "Alpha", "Gamma",  "None",  "None"  ],
    ]
    palette = {
        "None":   "#e8e8e8",
        "Alpha":  "#3a6dbf",
        "Beta":   "#c0392b",
        "Gamma":  "#e67e22",
        "Delta":  "#27ae60",
    }

    c = pt.chart(title="heatmap (categorical palette, absent=grey)",
                 xlabel="sample", ylabel="row")
    c.add_heatmap(data=_tidy_heatmap(matrix, samples, rows, xname="sample"), mapping=aes(x="sample"), values=rows,
              palette=palette, absent_fill="#dddddd")
    c.xticks(rotation=45)
    c.legend()
    return c


def chart_heatmap_nan():
    import math
    cols = ["A", "B", "C", "D"]
    rows = ["r1", "r2", "r3"]
    matrix = [
        [1.0,       float("nan"), 3.0,  None],
        [None,      2.0,          None, 4.0 ],
        [float("nan"), 1.5,       2.5,  None],
    ]

    c = pt.chart(title="heatmap (NaN/None → absent_fill)")
    c.add_heatmap(data=_tidy_heatmap(matrix, cols, rows, xname="col"), mapping=aes(x="col"), values=rows, cmap="viridis", absent_fill="#ff9999")
    c.legend()
    return c


def chart_heatmap_palette_annot():
    # Palette-mode annot renders numeric labels verbatim (identifiers /
    # counts, not measurements) — no fmt applied, unlike the cmap path,
    # where 990000 would come out as "9.9e+05".
    samples = [f"s{i}" for i in range(4)]
    rows = ["mut", "wt"]
    matrix = [["hit", "miss", "hit", "hit"],
              ["miss", "hit", "miss", "hit"]]
    counts = [[1234, 8, 250, 42],
              [3, 990000, 17, 5]]

    c = pt.chart(title="palette heatmap (verbatim numeric annot)")
    c.add_heatmap(data=_tidy_heatmap(matrix, samples, rows, xname="s"), mapping=aes(x="s"), values=rows,
              palette={"hit": "#4477aa", "miss": "#ee6677"}, annot=counts)
    c.legend()
    return c


def chart_heatmap_continuous_x():
    # Numeric `x` column → continuous linear x-axis (numeric ticks, not
    # category bands); value columns are categorical track rows.
    matrix = [[math.sin(0.5 * c + r) for c in range(10)] for r in range(6)]
    xs = [float(i) for i in range(10)]
    tracks = [f"r{i}" for i in range(6)]

    c = pt.chart(title="heatmap (continuous x)",
                 xlabel="x position", ylabel="track")
    c.add_heatmap(data=_tidy_heatmap(matrix, xs, tracks, xname="x"), mapping=aes(x="x"), values=tracks, cmap="viridis")
    c.legend()
    return c


def chart_heatmap_continuous_x_cat_y():
    # Annotation-track shape: continuous x (aligns to a scatter under
    # share_x), categorical track rows down the side.
    matrix = [[math.sin(0.4 * c + r) for c in range(12)] for r in range(3)]
    xs = [float(i) for i in range(12)]
    tracks = ["t1", "t2", "t3"]

    c = pt.chart(title="heatmap (continuous x, categorical tracks)",
                 xlabel="x position")
    c.add_heatmap(data=_tidy_heatmap(matrix, xs, tracks, xname="x"), mapping=aes(x="x"), values=tracks, cmap="magma")
    c.legend()
    return c


def chart_heatmap_continuous_uneven():
    # Unevenly spaced x → cell edges inferred as neighbor midpoints, so
    # each column gets a different width.
    matrix = [[1.0, 2.0, 3.0, 4.0, 5.0]]
    xs = [0.0, 1.0, 3.0, 6.0, 10.0]

    c = pt.chart(title="heatmap (uneven continuous x)", xlabel="t")
    c.add_heatmap(data=_tidy_heatmap(matrix, xs, ["v"], xname="t"), mapping=aes(x="t"), values=["v"], cmap="viridis", annot=True)
    c.legend()
    return c


def chart_heatmap_continuous_nan():
    # NaN/None on a continuous-position grid still routes to absent_fill,
    # never the imshow black.
    matrix = [
        [1.0, float("nan"), 3.0, None],
        [None, 2.0, 5.0, 4.0],
    ]
    xs = [0.0, 1.0, 2.0, 3.0]

    c = pt.chart(title="heatmap (continuous + NaN → absent_fill)",
                 xlabel="x")
    c.add_heatmap(data=_tidy_heatmap(matrix, xs, ["a", "b"], xname="x"), mapping=aes(x="x"), values=["a", "b"], cmap="viridis", absent_fill="#ff9999")
    c.legend()
    return c


def chart_heatmap_split():
    # Annotated-heatmap row + column clusters via c.sectors. Both
    # grouping vectors are deliberately interleaved so the auto
    # cluster-and-gap reordering is exercised on both axes — rows regroup
    # to A,A,A / B,B,B / C,C and cols regroup to X,X,X / Y,Y,Y,Y,Y /
    # Z,Z,Z,Z. The uneven block sizes (3-3-2 rows × 3-5-4 cols) make the
    # gaps obvious.
    nrows, ncols = 8, 12
    matrix = [[r * ncols + c for c in range(ncols)] for r in range(nrows)]
    row_labels = [f"r{i+1}" for i in range(nrows)]
    col_labels = [f"c{i+1}" for i in range(ncols)]
    row_groups = ["A", "B", "A", "C", "A", "B", "C", "B"]
    col_groups = ["X", "Y", "Z", "X", "Y", "Z", "Y", "Z",
                  "X", "Y", "Z", "Y"]

    c = pt.chart(title="heatmap (row + column clusters)")
    c.sectors(_by_label(col_labels, col_groups), axis="x",
              divider=False, label=False)
    c.sectors(_by_label(row_labels, row_groups), axis="y",
              divider=False, label=False)
    c.add_heatmap(data=_tidy_heatmap(matrix, col_labels, row_labels, xname="col"), mapping=aes(x="col"), values=row_labels, annot=True)
    c.legend()
    return c


PLOTS = {
    "heatmap_labeled": chart_heatmap_labeled,
    "heatmap_dataframe": chart_heatmap_dataframe,
    "heatmap_annot": chart_heatmap_annot,
    "heatmap_categorical": chart_heatmap_categorical,
    "heatmap_nan": chart_heatmap_nan,
    "heatmap_palette_annot": chart_heatmap_palette_annot,
    "heatmap_continuous_x": chart_heatmap_continuous_x,
    "heatmap_continuous_x_cat_y": chart_heatmap_continuous_x_cat_y,
    "heatmap_continuous_uneven": chart_heatmap_continuous_uneven,
    "heatmap_continuous_nan": chart_heatmap_continuous_nan,
    "heatmap_split": chart_heatmap_split,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_heatmap_baseline(name, fn, baseline_compare):
    baseline_compare("chart_heatmap", name, fn().to_svg())


def test_heatmap_unsorted_x_matches_sorted():
    # Tidy rows carry no order contract — record sorts by x, so any row
    # order renders the same SVG.
    a = pt.chart()
    df = {"x": [0.0, 2.0, 1.0, 3.0], "v": [10, 20, 30, 40]}
    a.add_heatmap(data=df, mapping=aes(x="x"))
    b = pt.chart()
    df2 = {"x": [0.0, 1.0, 2.0, 3.0], "v": [10, 30, 20, 40]}
    b.add_heatmap(data=df2, mapping=aes(x="x"))
    assert a.to_svg() == b.to_svg()


def test_heatmap_unsorted_x_permutes_annot():
    # A custom 2-D annot is [track][position] in input order and must be
    # permuted along with the columns.
    a = pt.chart()
    df = {"x": [1.0, 0.0], "v": [7.0, 5.0]}
    a.add_heatmap(data=df, mapping=aes(x="x"),
              annot=[["b", "a"]])
    b = pt.chart()
    df2 = {"x": [0.0, 1.0], "v": [5.0, 7.0]}
    b.add_heatmap(data=df2, mapping=aes(x="x"),
              annot=[["a", "b"]])
    assert a.to_svg() == b.to_svg()


def test_heatmap_rejects_bad_continuous_x():
    # Duplicate, NaN, or numbers-mixed-with-None x would silently produce
    # zero-width / NaN / mislabeled cells — all raise instead.
    for xs in ([1.0, 1.0, 2.0],
               [0.0, float("nan"), 2.0],
               [0.5, None, 1.0]):
        c = pt.chart()
        df = {"x": xs, "v": [1, 2, 3]}
        c.add_heatmap(data=df, mapping=aes(x="x"))
        with pytest.raises(ValueError):
            c.to_svg()


def test_heatmap_rejects_unknown_kwargs():
    c = pt.chart()
    df = {"x": ["a"], "v": [1]}
    c.add_heatmap(data=df, mapping=aes(x="x"), xticklabels=["a"])
    # The record signature is the kwarg allow-list — Python rejects
    # unknown names at replay.
    with pytest.raises(TypeError, match="xticklabels"):
        c.to_svg()


def test_heatmap_rejects_non_dict_palette():
    # A chart-level palette list (meant for color-cycling marks) is
    # injected into the heatmap call by aes inheritance — reject it
    # clearly instead of crashing on `_palette.items()` at draw.
    df = {"x": [0.0, 1.0], "v": [1.0, 2.0]}
    c = pt.chart(df, aes(x="x"),
                 palette=["#111111", "#222222"])
    c.add_heatmap()
    with pytest.raises(TypeError, match="palette"):
        c.to_svg()


def test_heatmap_inherited_y_not_a_track():
    # A chart-level y binding must not be swept into the value tracks.
    df = {"x": ["a", "b"], "v": [1.0, 2.0], "w": [3.0, 4.0]}
    c = pt.chart(df, aes(x="x", y="w"))
    c.add_heatmap()
    assert 'rows="1"' in c.to_svg()


def test_heatmap_numeric_x_categorical_scale_raises():
    # Categorical sectors force a category x scale, which maps numeric
    # cell edges to NaN — every cell would render invisible.
    c = pt.chart()
    c.sectors({"A": [1, 2], "B": [3]}, axis="x")
    df = {"id": [1, 2, 3], "t": [1.0, 2.0, 3.0]}
    c.add_heatmap(data=df, mapping=aes(x="id"))
    with pytest.raises(ValueError, match="categorical x scale"):
        c.to_svg()


def test_heatmap_numpy_scalar_x_is_continuous():
    # numpy scalars don't subclass int/float; the numbers.Real-based
    # dispatch must still classify an int64 column as continuous.
    np = pytest.importorskip("numpy")
    xs = list(np.arange(3))    # np.int64 elements, as DataFrameLite yields
    c = pt.chart()
    df = {"x": xs, "v": [1.0, 2.0, 3.0]}
    c.add_heatmap(data=df, mapping=aes(x="x"))
    assert 'x-axis="continuous"' in c.to_svg()


def test_heatmap_large_grid_encoding_matches_markup():
    # Plain large grid (>imshow_max_rects) → one PNG, attr says so.
    svg = _big_continuous_heatmap(with_y_sectors=False)
    assert svg.count("<image") == 1
    assert 'data-encoding="png-embedded"' in svg
    # y sector splits force rects — a single stretched image would paint
    # over the gap and shift rows off their bands — and the attr follows
    # the actual markup.
    svg = _big_continuous_heatmap(with_y_sectors=True)
    assert "<image" not in svg
    assert 'data-encoding="rects"' in svg


def test_heatmap_large_categorical_ring_uses_rects():
    # The warp guard is dtype-independent: a big categorical-x heatmap on
    # a Circular panel must not fall back to a flat unwarped <image>.
    tracks = [f"t{i}" for i in range(20)]
    data = {"x": [f"c{i}" for i in range(501)]}
    for r, name in enumerate(tracks):
        data[name] = [math.sin(0.01 * i + r) for i in range(501)]
    c = pt.chart(data_width=300, data_height=300)
    c.coordinate(pt.CircularCoordinate(r_inner=0.3))
    c.add_heatmap(data=data, mapping=aes(x="x"), values=tracks, cmap="viridis")
    assert "<image" not in c.to_svg()
