"""Chapter 4 — multi-panel composition."""

PAGE = dict(
    slug="composition",
    title="Multi-panel composition",
    blurb="""Operators, grids, shared scales, attachments, insets and
facets &mdash; the layer the flagship figures are built on.""",
    sections=[
        dict(
            id="operators",
            title="Operators and grids",
            prose="""Charts are values: <code>a | b</code> puts panels
side by side, <code>a / b</code> stacks them, and
<code>pt.grid([[...]])</code> builds full grids &mdash;
<code>None</code> leaves a cell empty. Margins are coordinated across
the layout so data regions align.""",
            code="""\
import math
xs = [i * 0.2 for i in range(40)]
sig = {"x": xs, "y": [math.sin(x) for x in xs]}
counts = {"cat": ["a", "b", "c"], "n": [4, 7, 3]}
dist = {"x": [0.1, 0.4, 0.5, 0.55, 0.7, 0.8, 0.9, 1.1, 1.3]}

a = pt.chart(sig, aes(x="x", y="y"), title="signal",
             data_width=220, data_height=140)
a.add_line()
b = pt.chart(counts, aes(x="cat", y="n"), title="counts",
             data_width=220, data_height=140)
b.add_bar()
d = pt.chart(dist, aes(x="x"), title="dist",
             data_width=220, data_height=140)
d.add_hist(bins=6)
c = pt.grid([[a, b], [d, None]])   # same as (a | b) / bottom row
""",
        ),
        dict(
            id="sizes",
            title="Panel sizes and gaps",
            prose="""Layouts are body-first: each chart&rsquo;s
<code>data_width</code> / <code>data_height</code> act as relative size
hints, and the layout sums them. <code>.gap(0)</code> removes the
default spacing; <code>.heights([...])</code> overrides row
ratios.""",
            code="""\
import math
xs = [i * 0.15 for i in range(60)]
sig = {"x": xs, "y": [math.sin(x) for x in xs]}
rate = {"x": xs, "y": [math.cos(3 * x) for x in xs]}

main = pt.chart(sig, aes(x="x", y="y"),
                data_width=420, data_height=180, ylabel="signal")
main.add_line()
small = pt.chart(rate, aes(x="x", y="y"),
                 data_width=420, data_height=60, ylabel="rate")
small.add_line(color="C2")
c = pt.grid([[small], [main]]).gap(0).share_x("col")
""",
        ),
        dict(
            id="share",
            title="Shared scales",
            prose="""<code>.share_x()</code> / <code>.share_y()</code>
take <code>"col"</code>, <code>"row"</code>, or <code>True</code> for
all panels: data ranges union, panels align, inner tick labels
collapse. This is what makes Anscombe grids and stacked tracks honest
&mdash; every panel really is on the same scale.""",
            code="""\
raw = pt.load_dataset("anscombe")

panels = []
for ds in ("I", "II", "III", "IV"):
    sub = {"x": [x for x, d in zip(raw["x"], raw["dataset"])
                 if d == ds],
           "y": [y for y, d in zip(raw["y"], raw["dataset"])
                 if d == ds]}
    p = pt.chart(sub, aes(x="x", y="y"), title=f"dataset {ds}",
                 data_width=180, data_height=130)
    p.add_scatter(size=3)
    p.add_regression()
    panels.append(p)
a, b, d, e = panels
c = pt.grid([[a, b], [d, e]]).share_x(True).share_y(True)
""",
        ),
        dict(
            id="attach",
            title="Attachments",
            prose="""<code>attach_above / _below / _left / _right</code>
glue annotation tracks to a host chart and share the touching axis
&mdash; marginal histograms, annotation strips, dendrograms. Multiple
attachments stack outward in call order.""",
            code="""\
import random
rng = random.Random(5)
xs = [rng.gauss(0, 1) for _ in range(300)]
df = {"x": xs, "y": [x * 0.6 + rng.gauss(0, 0.6) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"), data_width=300, data_height=200,
             xlabel="x", ylabel="y")
c.add_scatter(size=2, alpha=0.5)
top = pt.chart(df, aes(x="x"), data_height=55)
top.add_hist(bins=30, fill="#8a8fb0")
c.attach_above(top)
""",
        ),
        dict(
            id="inset",
            title="Insets",
            prose="""<code>c.inset(rect=(x, y, w, h))</code> places a
child panel inside the parent&rsquo;s data area (fractions of the
panel), with its own limits &mdash; the classic zoom-on-the-tail.""",
            code="""\
labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
counts = [950, 320, 80, 45, 28, 18, 12, 8, 5, 3]
df = {"category": labels, "count": counts}
df_tail = {"category": labels[2:], "count": counts[2:]}

c = pt.chart(df, aes(x="category", y="count"),
             data_width=440, data_height=240,
             title="long-tail distribution", ylabel="count")
c.add_bar()
inset = c.inset(rect=(0.4, 0.45, 0.55, 0.45), ylim=(0, 100))
inset.add_bar(df_tail, aes(x="category", y="count"))
""",
        ),
        dict(
            id="facets",
            title="Facets",
            prose="""When the panels are one-per-group over the same
columns, skip manual loops: <code>pt.facet(df, by=...)</code> splits a
table into a wrapped grid of shared-axis panels, and
<code>row=</code> / <code>col=</code> build two-factor grids.""",
            code="""\
import math
raw = pt.load_dataset("penguins")
keep = [i for i in range(len(raw["species"]))
        if not math.isnan(raw["bill_length_mm"][i])
        and not math.isnan(raw["bill_depth_mm"][i])]
df = {k: [raw[k][i] for i in keep]
      for k in ("species", "bill_length_mm", "bill_depth_mm")}

c = pt.facet(df, by="species", col_wrap=3,
             data_width=170, data_height=140,
             xlabel="bill length (mm)", ylabel="bill depth (mm)")
c.add_scatter(aes(x="bill_length_mm", y="bill_depth_mm"),
              size=2, alpha=0.7)
""",
        ),
    ],
)
