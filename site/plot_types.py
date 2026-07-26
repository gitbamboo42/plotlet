"""Tile definitions for the plot-types page.

Each tile is (category, artist_name, snippet). The snippet is the
exact code the generator runs — it must leave a chart in `c` — and
the exact code shown under the tile. Snippets assume
`import plotlet as pt` and `from plotlet import aes`; anything else
they import themselves.
"""

TILES = [
    # ---------------------------------------------------------- pairwise
    ("Pairwise data", "scatter", """\
df = {"x": [1, 2, 3, 4, 5, 6, 7], "y": [2, 4, 3, 6, 5, 7, 6]}

c = pt.chart(df, aes(x="x", y="y"), xlabel="x", ylabel="y")
c.add_scatter(size=4)
"""),
    ("Pairwise data", "line", """\
import math
xs = [i * 0.2 for i in range(40)]
df = {"x": xs, "y": [math.sin(x) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"), xlabel="x", ylabel="y")
c.add_line()
"""),
    ("Pairwise data", "step", """\
df = {"x": list(range(8)), "y": [1, 3, 2, 5, 4, 3, 6, 5]}

c = pt.chart(df, aes(x="x", y="y"), xlabel="x", ylabel="y")
c.add_step(where="post")
"""),
    ("Pairwise data", "area", """\
import math
xs = [i * 0.2 for i in range(40)]
df = {"x": xs, "y": [1.2 + math.sin(x) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"), xlabel="x", ylabel="y")
c.add_area(alpha=0.4)
"""),
    ("Pairwise data", "fill_between", """\
import math
xs = [i * 0.2 for i in range(40)]
mid = [math.sin(x) for x in xs]
df = {"x": xs, "mid": mid, "lo": [m - 0.3 for m in mid],
      "hi": [m + 0.3 for m in mid]}

c = pt.chart(df, aes(x="x"), xlabel="x", ylabel="y")
c.add_fill_between(aes(y1="lo", y2="hi"), alpha=0.3)
c.add_line(aes(y="mid"))
"""),
    ("Pairwise data", "regression", """\
import random
rng = random.Random(11)
xs = [i * 0.5 for i in range(30)]
df = {"x": xs, "y": [1 + 0.7 * x + rng.gauss(0, 1) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"), xlabel="x", ylabel="y")
c.add_scatter(size=2.5)
c.add_regression()
"""),
    ("Pairwise data", "errorbar", """\
df = {"x": [1, 2, 3, 4, 5, 6],
      "y": [2.1, 3.4, 4.0, 3.8, 5.1, 6.2],
      "sd": [0.4, 0.3, 0.6, 0.5, 0.4, 0.7]}

c = pt.chart(df, aes(x="x", y="y", yerr="sd"), xlabel="x", ylabel="y")
c.add_errorbar()
"""),
    ("Pairwise data", "numeric_bar", """\
df = {"x": [0.5, 1.2, 3.0, 3.4, 6.0, 8.5], "y": [3, 7, 4, 9, 2, 6]}

c = pt.chart(df, aes(x="x", y="y"), xlabel="pos", ylabel="score")
c.add_numeric_bar(width=0.4)
"""),
    ("Pairwise data", "polyline", """\
c = pt.chart(xlim=(0, 10), ylim=(0, 6))
c.add_polyline([1, 3, 4, 6, 8, 9], [1, 4, 2, 5, 3, 5],
               color="#534AB7", linewidth=1.5)
"""),
    # ----------------------------------------------------- distributions
    ("Distributions", "hist", """\
import random
rng = random.Random(7)
df = {"x": [rng.gauss(0, 1) for _ in range(800)]}

c = pt.chart(df, aes(x="x"), xlabel="value", ylabel="count")
c.add_hist(bins=24)
"""),
    ("Distributions", "freqpoly", """\
import random
rng = random.Random(14)
df1 = {"x": [rng.gauss(0, 1) for _ in range(400)]}
df2 = {"x": [rng.gauss(1, 1.4) for _ in range(400)]}

c = pt.chart(xlabel="value", ylabel="count")
c.add_freqpoly(df1, aes(x="x"), bins=25)
c.add_freqpoly(df2, aes(x="x"), bins=25)
"""),
    ("Distributions", "density_1d", """\
import random
rng = random.Random(10)
df1 = {"x": [rng.gauss(0, 1) for _ in range(300)]}
df2 = {"x": [rng.gauss(1.2, 1.3) for _ in range(300)]}

c = pt.chart(xlabel="value", ylabel="density")
c.add_density_1d(df1, aes(x="x"), fill=True)
c.add_density_1d(df2, aes(x="x"), fill=True)
"""),
    ("Distributions", "ecdf", """\
import random
rng = random.Random(8)
df1 = {"x": [rng.gauss(0, 1) for _ in range(200)]}
df2 = {"x": [rng.gauss(0.6, 1.3) for _ in range(200)]}

c = pt.chart(xlabel="value", ylabel="F(x)")
c.add_ecdf(df1, aes(x="x"))
c.add_ecdf(df2, aes(x="x"))
"""),
    ("Distributions", "qq", """\
import random
rng = random.Random(16)
sample = [rng.gauss(0, 1) + 0.2 * (rng.expovariate(1) - 1) for _ in range(150)]
df = {"s": sample}

c = pt.chart(df, aes(sample="s"), xlabel="theoretical", ylabel="sample")
c.add_qq(dist="normal")
"""),
    ("Distributions", "rug", """\
import random
rng = random.Random(9)
df = {"x": [rng.gauss(0, 1) for _ in range(150)]}

c = pt.chart(df, aes(x="x"), xlabel="value", ylabel="density")
c.add_density_1d(fill=True)
c.add_rug(color="#444444")
"""),
    ("Distributions", "ridge", """\
import random
rng = random.Random(15)
data = {"row": [], "value": []}
for i, row in enumerate(["a", "b", "c", "d"]):
    data["row"] += [row] * 150
    data["value"] += [rng.gauss(i, 1.2) for _ in range(150)]

c = pt.chart(data, aes(x="row", y="value"), xlabel="value")
c.add_ridge(overlap=1.5)
c.yticks([])
"""),
    # ------------------------------------------------------- categorical
    ("Categorical", "bar", """\
df = {"cat": ["a", "b", "c", "d"], "n": [4, 7, 3, 5]}

c = pt.chart(df, aes(x="cat", y="n", fill="cat"), ylabel="count",
             legend=False)
c.add_bar()
"""),
    ("Categorical", "boxplot", """\
import random
rng = random.Random(0)
data = {"grp": [], "value": []}
for i, grp in enumerate(["a", "b", "c"]):
    data["grp"] += [grp] * 40
    data["value"] += [rng.gauss(5 + i, 1 + 0.3 * i) for _ in range(40)]

c = pt.chart(data, aes(x="grp", y="value"), ylabel="value")
c.add_boxplot()
"""),
    ("Categorical", "violin", """\
import random
rng = random.Random(1)
data = {"grp": [], "value": []}
for i, grp in enumerate(["a", "b", "c"]):
    data["grp"] += [grp] * 80
    data["value"] += [rng.gauss(5 + i, 1) for _ in range(80)]

c = pt.chart(data, aes(x="grp", y="value"), ylabel="value")
c.add_violin()
"""),
    ("Categorical", "strip", """\
import random
rng = random.Random(3)
data = {"grp": [], "value": []}
for i, grp in enumerate(["a", "b", "c", "d"]):
    data["grp"] += [grp] * 30
    data["value"] += [rng.gauss(4 + i, 0.8) for _ in range(30)]

c = pt.chart(data, aes(x="grp", y="value"), ylabel="value")
c.add_strip(size=2.5, alpha=0.6)
"""),
    ("Categorical", "swarm", """\
import random
rng = random.Random(2)
data = {"grp": [], "value": []}
for i, grp in enumerate(["a", "b", "c"]):
    data["grp"] += [grp] * 40
    data["value"] += [rng.gauss(4 + i, 0.8) for _ in range(40)]

c = pt.chart(data, aes(x="grp", y="value"), ylabel="value")
c.add_swarm(size=2.2)
"""),
    ("Categorical", "pointplot", """\
import random
rng = random.Random(7)
data = {"t": [], "score": []}
for i, t in enumerate(["w1", "w2", "w4", "w8"]):
    data["t"] += [t] * 20
    data["score"] += [rng.gauss(5 + 0.4 * i, 1) for _ in range(20)]

c = pt.chart(data, aes(x="t", y="score"), ylabel="score")
c.add_pointplot()
"""),
    # -------------------------------------------------- gridded / matrix
    ("Gridded & matrix", "heatmap", """\
import math
data = {"col": [f"c{i}" for i in range(8)]}
for r in range(5):
    data[f"r{r}"] = [math.sin(i * 0.7 + r) for i in range(8)]

c = pt.chart()
c.add_heatmap(data=data, mapping=aes(x="col"),
              values=[f"r{r}" for r in range(5)], cmap="viridis")
"""),
    ("Gridded & matrix", "imshow", """\
import math
grid = [[math.sin(r * 0.15) + math.cos(col * 0.1) for col in range(80)]
        for r in range(60)]

c = pt.chart(xlabel="col", ylabel="row")
c.add_imshow(grid, cmap="magma")
"""),
    ("Gridded & matrix", "contour", """\
import math
def z(x, y):
    return (math.exp(-(x + 1) ** 2 - y ** 2)
            + math.exp(-(x - 1) ** 2 - (y - 1) ** 2))
grid = [[z(-3 + 6 * i / 30, -3 + 6 * j / 30) for i in range(31)]
        for j in range(31)]

c = pt.chart(xlabel="x", ylabel="y")
c.add_contour(grid, extent=(-3, 3, -3, 3), cmap="viridis",
              levels=[0.1, 0.3, 0.5, 0.7, 0.9])
"""),
    ("Gridded & matrix", "hist2d", """\
import random
rng = random.Random(24)
xs = [rng.gauss(0, 1) for _ in range(3000)]
df = {"x": xs, "y": [x * 0.6 + rng.gauss(0, 0.8) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"), xlabel="x", ylabel="y")
c.add_hist2d(bins=25)
"""),
    ("Gridded & matrix", "hexbin", """\
import random
rng = random.Random(13)
xs = [rng.gauss(0, 1) for _ in range(3000)]
df = {"x": xs, "y": [x + rng.gauss(0, 1) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"), xlabel="x", ylabel="y")
c.add_hexbin(gridsize=20)
"""),
    ("Gridded & matrix", "kde_2d", """\
import random
rng = random.Random(12)
xs = [rng.gauss(0, 1) for _ in range(300)]
df = {"x": xs, "y": [x * 0.5 + rng.gauss(0, 0.8) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"), xlabel="x", ylabel="y")
c.add_kde_2d(n_grid=40, cmap="viridis")
"""),
    # ------------------------------------------------------ trees, flows
    ("Trees & flows", "dendrogram", """\
import random
rng = random.Random(0)
data = [[rng.gauss(i % 3, 0.4) for _ in range(4)] for i in range(9)]

c = pt.chart()
c.add_dendrogram(data, labels=[f"s{i}" for i in range(9)], method="ward")
"""),
    ("Trees & flows", "chord_links", """\
df = {"a": [1, 2, 1, 5, 3], "b": [4, 6, 8, 7, 9]}

c = pt.chart(df, aes(x1="a", x2="b"), xlabel="position")
c.add_chord_links(color="#4C72B0", width=1.5)
c.yticks([])
"""),
    ("Trees & flows", "chord_ribbon", """\
df = {"a0": [0.0, 2.0], "a1": [1.5, 3.5],
      "b0": [6.0, 8.0], "b1": [7.5, 9.5]}

c = pt.chart(df, aes(x1_start="a0", x1_end="a1",
                     x2_start="b0", x2_end="b1"), xlabel="position")
c.add_chord_ribbon(color="#4C72B0", alpha=0.6)
c.yticks([])
"""),
    ("Trees & flows", "annotation_strip", """\
cols = [f"c{i}" for i in range(10)]
groups = {"col": cols, "group": ["A"] * 3 + ["B"] * 4 + ["C"] * 3}
bars = {"col": cols, "v": [3, 5, 4, 6, 7, 5, 6, 4, 3, 5]}

strip = pt.chart(groups, aes(position="col", value="group"),
                 data_height=16)
strip.add_annotation_strip(name="group")
c = pt.chart(bars, aes(x="col", y="v"), data_height=110)
c.add_bar(fill="#8a8fb0")
c.attach_above(strip)
"""),
    # ------------------------------------------------ guides, annotation
    ("Guides & annotation", "axhline", """\
import math
xs = [i * 0.2 for i in range(40)]
df = {"x": xs, "y": [math.sin(x) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"))
c.add_line()
c.add_axhline(0.5, color="#C44E52", linestyle="--")
"""),
    ("Guides & annotation", "axvline", """\
import math
xs = [i * 0.2 for i in range(40)]
df = {"x": xs, "y": [math.sin(x) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"))
c.add_line()
c.add_axvline(math.pi, color="#C44E52", linestyle=":")
"""),
    ("Guides & annotation", "axhspan", """\
import math
xs = [i * 0.2 for i in range(40)]
df = {"x": xs, "y": [math.sin(x) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"))
c.add_axhspan(-0.5, 0.5, color="C2")
c.add_line()
"""),
    ("Guides & annotation", "axvspan", """\
import math
xs = [i * 0.2 for i in range(40)]
df = {"x": xs, "y": [math.sin(x) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"))
c.add_axvspan(2.0, 3.5)
c.add_line()
"""),
    ("Guides & annotation", "axline", """\
import random
rng = random.Random(31)
obs = [i * 0.5 + rng.gauss(0, 0.6) for i in range(20)]
df = {"o": obs, "p": [v + rng.gauss(0, 0.5) for v in obs]}

c = pt.chart(df, aes(x="o", y="p"), xlabel="observed", ylabel="predicted")
c.add_scatter(size=2.5)
c.add_axline((0, 0), slope=1, linestyle="--")
"""),
    ("Guides & annotation", "hlines", """\
c = pt.chart(xlabel="x", ylabel="y")
c.add_hlines([1, 2, 3], 0, 5, linestyle="--")
"""),
    ("Guides & annotation", "vlines", """\
c = pt.chart(xlabel="x", ylabel="y")
c.add_vlines([1.5, 3.5], 0.5, 3.5, color="C3")
"""),
    ("Guides & annotation", "annotate", """\
import math
xs = [i * 0.2 for i in range(40)]
df = {"x": xs, "y": [math.sin(x) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"))
c.add_line()
c.add_annotate("peak", xy=(1.6, 1.0), xytext=(3.0, 1.2))
"""),
    ("Guides & annotation", "text", """\
df = {"x": [1, 2, 3, 4, 5], "y": [3, 7, 4, 9, 5], "lab": list("ABCDE")}

c = pt.chart(df, aes(x="x", y="y"))
c.add_scatter()
c.add_text(aes(label="lab"), dy=-10, ha="center")
"""),
    # ------------------------------------------------------------ shapes
    ("Shapes", "rect", """\
c = pt.chart(xlim=(0, 8), ylim=(0, 4))
c.add_rect([0, 2, 4, 6], 0, 1.5, 2, fill="C0", alpha=0.6)
c.add_rect(0.5, 2.5, 7, 1, fill="C1", alpha=0.3)
"""),
    ("Shapes", "polygon", """\
c = pt.chart(xlim=(0, 5), ylim=(0, 3.5))
c.add_polygon([0, 2, 1], [0, 0, 2], alpha=0.5)
c.add_polygon([3, 4, 3, 2], [1, 2, 3, 2], fill="none", linewidth=2)
"""),
]
