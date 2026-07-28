"""Chapter 7 — reproducibility and AI tooling."""

PAGE = dict(
    slug="reproducibility",
    title="Reproducibility & AI tooling",
    blurb="""Byte-identical output, figures as data, and an SVG your
scripts and AI assistants can read.""",
    sections=[
        dict(
            id="deterministic",
            title="Why the bytes match",
            prose="""Text is drawn as paths from a bundled font, so
nothing depends on what&rsquo;s installed on the machine. There is no
global state &mdash; themes, defaults, everything is per-chart &mdash;
and no interactivity, ever. The result: the same script produces the
same SVG, byte for byte, on macOS, Linux and Windows. Figures can live
in version control and break loudly when they change &mdash;
plotlet&rsquo;s own test suite is 270+ committed baseline SVGs compared
byte-wise on every CI run.""",
            code="""\
df = {"x": [1, 2, 3, 4], "y": [2, 4, 3, 5]}

c = pt.chart(df, aes(x="x", y="y"), title="render me twice")
c.add_line()
assert c.to_svg() == c.to_svg()   # trivially true here —
# the real claim is across machines, and CI enforces it
""",
        ),
        dict(
            id="serialize",
            title="Figures as data",
            prose="""The journal serializes to JSON: archive it next to
a paper, ship it to a colleague, rebuild it years later &mdash; the SVG
matches byte for byte. The <code>assert</code> below runs on every
build of this page.""",
            code="""\
df = {"x": [1, 2, 3, 4], "y": [2, 4, 3, 5]}

c1 = pt.chart(df, aes(x="x", y="y"), title="original")
c1.add_line()

payload = pt.to_json(c1)          # the journal, as JSON
c = pt.from_json(payload)         # rebuilt anywhere, any machine
assert c.to_svg() == c1.to_svg()  # byte-identical
""",
        ),
        dict(
            id="ai",
            title="What your AI assistant sees",
            prose="""The SVG is self-describing: every artist group
carries <code>data-plotlet-*</code> attributes &mdash; plot type,
mapped columns, row counts, data ranges &mdash; so an AI assistant (or
any script) can read what a figure shows from the file itself, no
pixels involved. For layout questions (&ldquo;why does the legend
overlap the title?&rdquo;), <code>c.regions()</code> returns every
chrome box as structured data. Below: the chart, a fragment of its own
SVG, and the first rows of its region report. Full schema in
<a href="docs-ai_attrs.html">docs/AI_ATTRS.md</a>.""",
            code="""\
tips = pt.load_dataset("tips")

c = pt.chart(tips, aes(x="total_bill", y="tip"), title="tips",
             data_width=300, data_height=200)
c.add_scatter(size=2.5, alpha=0.6)
""",
        ),
        dict(
            id="discovery",
            title="Discoverable by construction",
            prose="""The registry is queryable at runtime &mdash;
<code>pt.artist_table()</code> lists every installed artist with its
capabilities, and <code>help(c.add_scatter)</code> forwards the
artist&rsquo;s docstring through the recorder. AI-oriented onboarding
guides ship inside the package
(<a href="https://github.com/gitbamboo42/plotlet/tree/main/src/plotlet/skills">skills/</a>)
&mdash; <code>pt.skill()</code> prints the users guide for tools that
generate plotlet code on your behalf.""",
            code="""\
names = sorted({row["name"] for row in pt.artist_table()
                if row["origin"] == "core"})
assert len(names) == 43
# help(c.add_scatter)  ->  the scatter artist's full docstring
""",
        ),
        dict(
            id="extend",
            title="Make it yours",
            prose="""A plot type is a single registered function &mdash;
no classes to subclass. <code>pt.add_artist</code> plus a draw function
gets a new mark onto every chart, with the <code>draw.*</code> helpers
emitting the SVG. The ~45 artists in
<a href="https://github.com/gitbamboo42/plotlet-extensions">plotlet-extensions</a>
are each one file built exactly this way &mdash; read
<a href="docs-extending.html">docs/EXTENDING.md</a>
and copy one.""",
        ),
    ],
)
