"""Chapter 6 — color and themes."""

PAGE = dict(
    slug="color",
    title="Color & themes",
    blurb="""Palettes for categories, colormaps for values, the cycle
notation, and per-chart themes.""",
    sections=[
        dict(
            id="palettes",
            title="Palettes for categories",
            prose="""A categorical column mapped through
<code>aes(...)</code> pulls colors from the default cycle.
<code>palette=</code> overrides it: a named palette
(<code>pt.list_palettes()</code> &mdash; tab10, Set2, colorblind,
&hellip;) or an explicit <code>{level: color}</code> dict when specific
levels must keep specific colors.""",
            code="""\
import random
rng = random.Random(1)
data = {"grp": [], "value": [], "arm": []}
for i, g in enumerate(["ctrl", "low", "high"]):
    for arm in ("A", "B"):
        data["grp"] += [g] * 40
        data["arm"] += [arm] * 40
        data["value"] += [rng.gauss(5 + i + (arm == "B"), 1)
                          for _ in range(40)]

c = pt.chart(data, aes(x="grp", y="value", fill="arm"), legend=True,
             data_width=380, data_height=200)
c.xscale("category", order=["ctrl", "low", "high"])
c.add_violin(palette={"A": "#3F97C5", "B": "#F99917"}, inner="box")
c.legend()
""",
        ),
        dict(
            id="cycle",
            title="The color cycle",
            prose="""Literal colors accept hex strings, named colors,
and the cycle notation <code>"C0"</code>&hellip;<code>"C9"</code>
&mdash; slot <em>n</em> of the default tab10 cycle, the same in every
theme, so layered artists can coordinate colors without hardcoding hex. A bare
<code>color=</code> string is always a literal like these &mdash; only
<code>aes(...)</code> maps a column. The default cycle is also
available as <code>pt.TAB10</code>.""",
            code="""\
import math
xs = [i * 0.2 for i in range(40)]
waves = {"x": xs, "sin": [math.sin(x) for x in xs],
         "cos": [math.cos(x) for x in xs]}

c = pt.chart(waves, aes(x="x"), data_width=380, data_height=170,
             legend=True)
c.add_line(aes(y="sin"), color="C0", label="C0")
c.add_line(aes(y="cos"), color="C1", label="C1")
c.add_axhline(0, color="C3", linestyle="--", label="C3")
c.legend()
""",
        ),
        dict(
            id="colormaps",
            title="Colormaps for values",
            prose="""Continuous values map through <code>cmap=</code>
&mdash; the matplotlib names are all registered
(<code>pt.list_colormaps()</code>), each with a reversed
<code>_r</code> twin. For diverging data, <code>center=</code> pins the
midpoint (e.g. 0) to the colormap&rsquo;s center. Register custom maps
with <code>pt.register_colormap</code>.""",
            code="""\
import math
data = {"col": [f"c{i}" for i in range(10)]}
for r in range(6):
    data[f"r{r}"] = [math.sin(i * 0.6 + r) for i in range(10)]
values = [f"r{r}" for r in range(6)]

left = pt.chart(title="viridis", data_width=220, data_height=150)
left.add_heatmap(data=data, mapping=aes(x="col"), values=values,
                 cmap="viridis")
right = pt.chart(title="RdBu_r, center=0", data_width=220,
                 data_height=150)
right.add_heatmap(data=data, mapping=aes(x="col"), values=values,
                  cmap="RdBu_r", center=0)
c = left | right
""",
        ),
        dict(
            id="themes",
            title="Themes",
            prose="""Four built-ins &mdash; <code>classic</code> (the
default), <code>dark</code>, <code>minimal</code>,
<code>void</code> &mdash; set per chart, never globally: the same
script always produces the same figures. Themes restyle the chrome
&mdash; background, frame, gridlines, fonts &mdash; while series colors
and your data code don&rsquo;t change. Custom themes are a
dict away (<code>pt.register_theme</code>,
<a href="docs-themes.html">docs/THEMES.md</a>).""",
            code="""\
import math
xs = [i * 0.1 for i in range(64)]
waves = {"t": xs, "sin": [math.sin(x) for x in xs],
         "cos": [math.cos(x) for x in xs]}

a = pt.chart(waves, aes(x="t", y="sin"), theme="classic",
             title="classic", data_width=210, data_height=140,
             xlabel="t")
a.add_line()
a.add_line(aes(y="cos"), linestyle="--")
b = pt.chart(waves, aes(x="t", y="sin"), theme="minimal",
             title="minimal", data_width=210, data_height=140,
             xlabel="t")
b.add_line()
b.add_line(aes(y="cos"), linestyle="--")
c = a | b
""",
        ),
    ],
)
