"""Chapter 2 — mappings, scales, ticks."""

PAGE = dict(
    slug="aesthetics",
    title="Aesthetics & scales",
    blurb="""Column mappings versus literals, controlling axes, and
everything about ticks.""",
    sections=[
        dict(
            id="mapped-vs-literal",
            title="Mapped vs. literal aesthetics",
            prose="""Name a column inside <code>aes(...)</code> and the
aesthetic is <em>mapped</em> &mdash; plotlet builds a scale and a
legend entry per level. Pass the same aesthetic as a bare kwarg and it
is a <em>literal</em> that applies to every mark. The spelling decides:
<code>aes(color="species")</code> maps the column,
<code>color="#534AB7"</code> is just that color &mdash; even if a
column shares the name.""",
            code="""\
import math
raw = pt.load_dataset("penguins")
keep = [i for i in range(len(raw["species"]))
        if not math.isnan(raw["flipper_length_mm"][i])]
df = {k: [raw[k][i] for i in keep]
      for k in ("species", "flipper_length_mm", "body_mass_g")}

left = pt.chart(df, aes(x="flipper_length_mm", y="body_mass_g"),
                title="mapped", legend=True,
                data_width=240, data_height=180)
left.add_scatter(aes(color="species"), size=2.5, alpha=0.7)

right = pt.chart(df, aes(x="flipper_length_mm", y="body_mass_g"),
                 title="literal", data_width=240, data_height=180)
right.add_scatter(color="#534AB7", size=2.5, alpha=0.5)

c = left | right
""",
        ),
        dict(
            id="size-style",
            title="Size and style channels",
            prose="""Beyond position and color, columns can drive marker
size &mdash; the radius in px (<code>aes(size=...)</code>, with
<code>sizes=(lo, hi)</code> on the artist to bound the range) &mdash;
and marker shape
(<code>aes(style=...)</code>). Channels compose &mdash; one column
each.""",
            code="""\
import random
rng = random.Random(2)
n = 36
df = {"x": [rng.uniform(0, 10) for _ in range(n)],
      "y": [rng.uniform(0, 10) for _ in range(n)],
      "mass": [rng.uniform(5, 50) for _ in range(n)],
      "group": [["alpha", "beta", "gamma"][i % 3] for i in range(n)]}

c = pt.chart(df, aes(x="x", y="y", size="mass",
                     color="group", style="group"),
             title="color + size + style", xlabel="x", ylabel="y",
             legend=True, data_width=400, data_height=240)
c.add_scatter(sizes=(2, 8))
""",
        ),
        dict(
            id="category-order",
            title="Categorical order",
            prose="""Categorical axes default to first-seen order.
<code>xscale("category", order=[...])</code> pins the order you
mean.""",
            code="""\
tips = pt.load_dataset("tips")

c = pt.chart(tips, aes(x="day", y="tip"), ylabel="tip ($)")
c.xscale("category", order=["Thur", "Fri", "Sat", "Sun"])
c.add_boxplot()
""",
        ),
        dict(
            id="log",
            title="Log scales",
            prose="""<code>xscale("log")</code> /
<code>yscale("log")</code> switch an axis to log10. The
<code>power10</code> tick formatter writes exponents properly.""",
            code="""\
xs = [1, 3, 10, 30, 100, 300, 1000, 3000, 10000]
df = {"x": xs, "y": [x ** 0.5 for x in xs]}

c = pt.chart(df, aes(x="x", y="y"), xlabel="dose", ylabel="response",
             gridlines=True)
c.xscale("log")
c.xticks(format="power10")
c.add_line()
c.add_scatter(size=3)
""",
        ),
        dict(
            id="limits",
            title="Limits",
            prose="""Axes autoscale to the data with a small expansion
so extremes don&rsquo;t sit on the frame. <code>xlim=</code> /
<code>ylim=</code> (as chart kwargs or method calls) pin exact
ranges.""",
            code="""\
import math
xs = [i * 0.2 for i in range(60)]
df = {"x": xs, "y": [0.5 + 0.6 * math.sin(x) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"),
             title="ylim=(0, 1) clamps the frame",
             ylim=(0, 1), data_width=380, data_height=160)
c.add_line()
""",
        ),
        dict(
            id="ticks",
            title="Tick control",
            prose="""<code>xticks</code> / <code>yticks</code> take a
list of positions (empty list hides the axis entirely), plus
<code>rotation=</code>, <code>side=</code> (&ldquo;top&rdquo; /
&ldquo;right&rdquo;), <code>direction="in"</code>, and
<code>marks=False</code> / <code>labels=False</code> to hide marks or
labels independently.""",
            code="""\
import math
xs = [i * 0.2 for i in range(40)]
df = {"x": xs, "y": [math.sin(x) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"), data_width=380, data_height=170,
             title="ticks: explicit positions, rotated, right side")
c.add_line()
c.xticks([0, math.pi, 2 * math.pi], rotation=45)
c.yticks(side="right")
""",
        ),
        dict(
            id="formatters",
            title="Tick formatters",
            prose="""Named formatters &mdash; <code>comma</code>,
<code>money</code>, <code>percent</code>, <code>si</code>,
<code>scientific</code>, <code>power10</code> &mdash; attach per axis
with <code>format=</code>. Register your own with
<code>pt.register_formatter</code>.""",
            code="""\
df = {"quarter": ["Q1", "Q2", "Q3", "Q4"],
      "revenue": [1_200_000, 1_850_000, 1_600_000, 2_400_000]}

c = pt.chart(df, aes(x="quarter", y="revenue"), title="revenue",
             data_width=340, data_height=180)
c.add_bar(fill="#4C72B0")
c.yticks(format="si")
""",
        ),
        dict(
            id="gridlines",
            title="Gridlines and spines",
            prose="""<code>gridlines=True</code> draws the dotted grid.
<code>c.spines(top=False, right=False)</code> drops frame sides for the
open look.""",
            code="""\
import math
xs = [i * 0.2 for i in range(40)]
df = {"x": xs, "y": [math.sin(x) for x in xs]}

c = pt.chart(df, aes(x="x", y="y"), gridlines=True,
             data_width=380, data_height=170,
             title="open frame + grid")
c.spines(top=False, right=False)
c.add_line()
""",
        ),
    ],
)
