"""Chapter 1 — the basic pattern."""

PAGE = dict(
    slug="intro",
    title="Introduction",
    blurb="""The mental model in five minutes: charts are journals,
data is long-form, <code>aes()</code> maps columns to aesthetics, and
rendering is deterministic.""",
    sections=[
        dict(
            id="first-chart",
            title="A first chart",
            prose="""A chart is a <em>journal</em>: every method call
records what you asked for, and nothing is drawn until you render. In a
notebook, <code>c.show()</code> displays the figure;
<code>c.to_svg()</code> returns the SVG as text. The same journal always
renders to the same bytes, on any machine.""",
            code="""\
import plotlet as pt
from plotlet import aes

df = {"month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
      "sales": [12, 15, 14, 18, 21, 19]}

c = pt.chart(df, aes(x="month", y="sales"),
             title="monthly sales", ylabel="units (k)")
c.add_line()
c.add_scatter(size=3)
""",
        ),
        dict(
            id="long-form",
            title="Long-form data in, aes() maps the columns",
            prose="""plotlet expects tidy tables &mdash; a plain dict of
columns, a pandas frame, or a polars frame all work. Column mappings go
in <code>aes(...)</code>: each aesthetic names one column. Four small
datasets ship for experimenting (<code>pt.list_datasets()</code> &rarr;
<code>anscombe</code>, <code>flights</code>, <code>penguins</code>,
<code>tips</code>).""",
            code="""\
tips = pt.load_dataset("tips")

c = pt.chart(tips, aes(x="total_bill", y="tip", color="day"),
             title="tips", xlabel="total bill ($)", ylabel="tip ($)",
             legend=True)
c.add_scatter(size=3, alpha=0.7)
""",
        ),
        dict(
            id="aesthetics",
            title="Declare aesthetics once, layer many marks",
            prose="""The <code>aes(...)</code> on the chart is inherited
by every artist you add, so layering is just more calls &mdash; here
the scatter and the per-group regression share <code>x</code>,
<code>y</code> and <code>color</code> from the chart, and each layer
carries only its own styling.""",
            code="""\
tips = pt.load_dataset("tips")

c = pt.chart(tips, aes(x="total_bill", y="tip", color="time"),
             xlabel="total bill ($)", ylabel="tip ($)", legend=True)
c.add_scatter(size=3, alpha=0.6)
c.add_regression()
""",
        ),
        dict(
            id="distributions",
            title="Distributions across groups",
            prose="""The statistical artists take the same long-form
table. Overlaying a boxplot and the raw points is two bare calls once
the chart carries the aesthetics.""",
            code="""\
tips = pt.load_dataset("tips")

c = pt.chart(tips, aes(x="day", y="total_bill"),
             ylabel="total bill ($)")
c.xscale("category", order=["Thur", "Fri", "Sat", "Sun"])
c.add_boxplot()
c.add_strip(size=2.5, alpha=0.4)
""",
        ),
        dict(
            id="saving",
            title="Rendering and saving",
            prose="""<code>to_svg()</code> is the native output &mdash;
text as paths, no font dependencies. <code>save_png()</code> rasterizes
through resvg (prebuilt wheels, no system libraries),
<code>save_pdf()</code> needs the optional <code>cairosvg</code>
extra, and <code>save_html()</code> wraps the SVG for a browser.""",
            code="""\
df = {"x": [1, 2, 3, 4], "y": [2, 4, 3, 5]}

c = pt.chart(df, aes(x="x", y="y"), title="export")
c.add_line()
svg_text = c.to_svg()       # the canonical, byte-stable output
# c.save_svg("figure.svg")  # or: save_png, save_pdf, save_html
""",
        ),
        dict(
            id="next",
            title="Where next",
            prose="""The remaining chapters go deeper: scales and
aesthetics, labels and legends, multi-panel composition, sectors and
circular coordinates, color and themes, and the reproducibility and
AI-tooling story. Or jump straight to the
<a href="cookbook.html">cookbook</a> and copy something.""",
        ),
    ],
)
