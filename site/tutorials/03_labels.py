"""Chapter 3 — chrome: titles, labels, legends."""

PAGE = dict(
    slug="labels",
    title="Titles, labels & legends",
    blurb="""The text around the data: layered titles, measure-driven
margins, and the two ways to place a legend.""",
    sections=[
        dict(
            id="titles",
            title="Title, subtitle, caption",
            prose="""Three text slots stack around the figure: the
title, a smaller subtitle under it, and a right-aligned caption at the
very bottom &mdash; the conventional place for a data source.""",
            code="""\
df = {"displacement": [1.8, 2.0, 2.8, 3.1, 4.2, 5.3],
      "mpg": [29, 31, 26, 27, 23, 20]}

c = pt.chart(df, aes(x="displacement", y="mpg"),
             data_width=340, data_height=170,
             title="Fuel efficiency", subtitle="highway, 1999-2008",
             caption="Source: EPA", xlabel="displacement (L)",
             ylabel="mpg")
c.add_scatter(size=3)
""",
        ),
        dict(
            id="margins",
            title="Margins grow to fit",
            prose="""Label space is measured, not guessed: long tick
labels, wide titles, or multi-line axis labels
(<code>\\n</code> works everywhere) grow the margins exactly as needed
&mdash; and in a grid, the growth propagates so data regions stay
aligned across panels.""",
            code="""\
df = {"score": [1, 2, 3, 4, 5],
      "name": ["measurement_alpha", "measurement_beta",
               "measurement_gamma", "measurement_delta",
               "measurement_epsilon"]}

c = pt.chart(df, aes(x="score", y="name"),
             data_width=300, data_height=170, xlabel="score")
c.add_scatter(size=3)
""",
        ),
        dict(
            id="legend-inline",
            title="Legends, next to the panel",
            prose="""<code>legend=True</code> reserves the right-hand
slot; entries come from mapped aesthetics automatically, or from
<code>label=</code> on individual artist calls when you layer
manually.""",
            code="""\
import math
xs = [i * 0.1 for i in range(64)]
df = {"t": xs,
      "sin": [math.sin(x) for x in xs],
      "cos": [math.cos(x) for x in xs]}

c = pt.chart(df, data_width=340, data_height=170, legend=True,
             xlabel="t", ylabel="value")
c.add_line(aes(x="t", y="sin"), label="sin(t)")
c.add_line(aes(x="t", y="cos"), label="cos(t)", linestyle="--")
""",
        ),
        dict(
            id="legend-cell",
            title="Legends, as a layout cell",
            prose="""In a composition, <code>pt.legend()</code> is a
grid cell of its own: it harvests entries from every panel in the
layout &mdash; discrete swatches and continuous gradients together
&mdash; so one legend serves the whole figure. The
<a href="cookbook.html#annotated-heatmap">annotated heatmap</a> relies
on this.""",
            code="""\
df = pt.load_dataset("flights")
months = df["month"][:12]
years = sorted(set(df["year"]))
data = {"year": [str(y) for y in years]}
for m in months:
    data[m] = [n for n, month in zip(df["passengers"], df["month"])
               if month == m]

hm = pt.chart(title="airline passengers", data_width=380,
              data_height=200)
hm.add_heatmap(data=data, mapping=aes(x="year"), values=months,
               cmap="viridis", legend={"label": "passengers"})
c = pt.grid([[hm, pt.legend()]]).gap(0)
""",
        ),
        dict(
            id="annotations",
            title="Annotate the data",
            prose="""<code>c.add_text(...)</code> places data-anchored
labels in batch; <code>c.add_annotate(...)</code> adds a single note,
with an arrow when the label sits away from its target and
<code>bbox=</code> for a background box over dense data.""",
            code="""\
import math
xs = [i * 0.2 for i in range(40)]
ys = [math.sin(x) + math.sin(2 * x) * 0.4 for x in xs]
df = {"x": xs, "y": ys}

c = pt.chart(df, aes(x="x", y="y"), data_width=400, data_height=190)
c.add_line()
peak = ys.index(max(ys))
c.add_annotate("global max", xy=(xs[peak], ys[peak]),
               xytext=(xs[peak] + 1.5, ys[peak] + 0.2))
c.add_annotate("baseline", xy=(6.5, -0.05), bbox=True)
""",
        ),
    ],
)
