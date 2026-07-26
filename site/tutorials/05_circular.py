"""Chapter 5 — sectors and circular coordinates."""

PAGE = dict(
    slug="circular",
    title="Sectors & circular coordinates",
    blurb="""Named axis partitions, ring layouts, and chord diagrams
&mdash; the genomics / Circos toolkit, from the same chart API.""",
    sections=[
        dict(
            id="sectors",
            title="Sectors: named partitions of an axis",
            prose="""<code>c.sectors({...})</code> splits the x-axis into
named, length-weighted regions with walls and labels. Each region gets
its own local coordinates; a tag column routes every row to its
region.""",
            code="""\
import random
rng = random.Random(4)
regions = {"promoter": 100, "gene body": 400, "UTR": 150}
data = {"region": [], "pos": [], "signal": []}
for name, length in regions.items():
    for _ in range(12):
        data["region"].append(name)
        data["pos"].append(rng.uniform(0, length))
        data["signal"].append(rng.uniform(0.2, 0.9))

c = pt.chart(data, aes(x="pos", y="signal"), data_width=460,
             data_height=130, ylim=(0, 1), ylabel="signal")
c.sectors(regions, column="region")
c.add_scatter(size=3, color="#534AB7")
""",
        ),
        dict(
            id="sectors-cat",
            title="Categorical sectors and gaps",
            prose="""Sectors can also group existing categories:
<code>{"group": ["cat", ...]}</code> partitions a categorical axis into
labeled blocks. A prebuilt <code>pt.Sectors(...)</code> value adds
control &mdash; <code>gap=</code> for whitespace between blocks,
<code>divider=False</code> / <code>label=False</code> to drop the
chrome.""",
            code="""\
df = {"cat": list("abcdefgh"), "val": [3, 5, 2, 6, 4, 7, 3, 5]}

c = pt.chart(df, aes(x="cat", y="val", fill="cat"), data_width=420,
             data_height=170, ylabel="count")
c.sectors({"G1": ["a", "b", "c"], "G2": ["d", "e"],
           "G3": ["f", "g", "h"]}, axis="x")
c.add_bar(palette="Set2", legend=False)
""",
        ),
        dict(
            id="tracks",
            title="Stacked tracks",
            prose="""Declared on a layout, <code>.sectors(...)</code>
applies to every track at once &mdash; combined with
<code>.share_x("col")</code> this is the genome-browser shape: aligned
tracks, one sector chrome.""",
            code="""\
import random
rng = random.Random(4)
regions = {"chr1": 100, "chr2": 80, "chr3": 60}
pts = {"chrom": [], "pos": [], "score": []}
for name, length in regions.items():
    for _ in range(10):
        pts["chrom"].append(name)
        pts["pos"].append(rng.uniform(0, length))
        pts["score"].append(rng.uniform(0.1, 0.9))
cov = {"chrom": pts["chrom"], "pos": pts["pos"],
       "cov": sorted(pts["score"])}

t1 = pt.chart(pts, aes(x="pos", y="score"), data_width=460,
              data_height=70, ylabel="score", ylim=(0, 1))
t1.add_scatter(size=3, color="#534AB7")
t2 = pt.chart(cov, aes(x="pos", y="cov", group="chrom"),
              data_width=460, data_height=70, ylabel="coverage",
              ylim=(0, 1))
t2.add_line(color="#1D9E75")
c = (pt.grid([[t1], [t2]])
       .share_x("col")
       .sectors(regions, column="chrom"))
""",
        ),
        dict(
            id="ring",
            title="Wrap it on a circle",
            prose="""A coordinate system is a per-panel property.
<code>c.coordinate(pt.CircularCoordinate())</code> wraps the same chart
onto a ring &mdash; x becomes angle, y becomes radius, and every artist
warps through: bars, lines, boxplots, even dendrograms.""",
            code="""\
df = {"cat": list("abcdefgh"), "val": [3, 5, 2, 6, 4, 7, 3, 5]}

c = pt.chart(df, aes(x="cat", y="val", fill="cat"))
c.coordinate(pt.CircularCoordinate())
c.add_bar(legend=False)
""",
        ),
        dict(
            id="ring-tuning",
            title="Tuning the ring",
            prose="""<code>r_inner=</code> reserves a center hole (0
&rarr; full disc, 0.9 &rarr; thin band);
<code>wrap_gap_deg=</code> leaves a wedge of whitespace at 12
o&rsquo;clock so the axis has visible ends. Sectors compose with the
warp &mdash; wedges, walls and per-sector arcs.""",
            code="""\
import math
xs = [i / 48 for i in range(49)]
wave = {"x": xs, "y": [0.5 + 0.35 * math.sin(4 * math.pi * x)
                       for x in xs]}

c = pt.chart(wave, aes(x="x", y="y"), xlim=(0, 1), ylim=(0, 1),
             title="r_inner=0.5, wrap_gap_deg=20")
c.coordinate(pt.CircularCoordinate(r_inner=0.5, wrap_gap_deg=20))
c.add_line(color="#1D9E75")
""",
        ),
        dict(
            id="chords",
            title="Chords through the center",
            prose="""The hole is usable space: pass another chart as
<code>inner=</code> and it renders in the central disc, inheriting the
sector partition &mdash; that&rsquo;s where
<code>add_chord_links</code> (arcs) and <code>add_chord_ribbon</code>
(filled ribbons) live in a Circos-style figure. See the
<a href="cookbook.html#chord">chord recipe</a> for the full recipe.""",
            code="""\
sectors = pt.Sectors(names=["A", "B", "C"], lengths=[30, 25, 20], gap=4)
span = (0, sectors.total())
links = {"src": ["A", "A", "B"], "dst": ["B", "C", "C"],
         "x1a": [0, 18, 0], "x1b": [10, 28, 15],
         "x2a": [0, 0, 0], "x2b": [10, 8, 12]}

arcs = pt.chart(links, aes(x1_start="x1a", x1_end="x1b",
                           x2_start="x2a", x2_end="x2b",
                           x1_sector="src", x2_sector="dst",
                           color="src"), xlim=span)
arcs.sectors(sectors, column="src", label=False)
arcs.add_chord_ribbon(alpha=0.6)
ring = pt.chart(xlim=span, ylim=(0, 1))
ring.sectors(sectors, column="x")
c = pt.grid([[ring]]).coordinate(
    pt.CircularCoordinate(r_inner=0.85, inner=arcs))
""",
        ),
    ],
)
