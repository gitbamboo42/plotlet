"""Build the plotlet website into ``site/build/``.

    python site/gen_site.py

Needs only plotlet, mistune and the stdlib. This file reads top to
bottom in build order:

  1. site config    — URLs, page tables, the snippets with no file of
                      their own (concepts)
  2. figures        — every snippet shown on the site is executed here;
                      a snippet that breaks fails the build
  3. docs           — docs/*.md rendered to HTML, links rewritten
  4. page shell     — CSS, client JS, the outer frame, the sidebar
  5. page builders  — one function per kind of page
  6. search + main

Output is deterministic: building twice yields identical bytes.
"""
from __future__ import annotations

import ast
import html
import json
import re
import sys
from pathlib import Path

try:
    import mistune  # build-time only; pinned in the site workflow
except ImportError:
    raise SystemExit("site build needs mistune: pip install mistune==3.1.4")

import plotlet as pt
from plotlet import aes

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_types import TILES  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Site config
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE / "examples"
BUILD = HERE / "build"

GITHUB = "https://github.com/gitbamboo42/plotlet"
EXTENSIONS = "https://github.com/gitbamboo42/plotlet-extensions"
COOKBOOK = "https://github.com/gitbamboo42/plotlet-cookbook"

TAGLINE = ("A plotting library built for AI authorship — reproducible, "
           "multi-panel scientific figures in Python.")

# Shown in the header and footer of every page so readers know which
# plotlet this manual documents. Comes from the installed package, so
# a build from a release tag stamps that release's version.
VERSION = pt.__version__

# Repo docs published on the site. Groups drive the sidebar; slugs are
# the lowercase stem (API.md -> docs-api.html).
DOC_GROUPS = [
    ("Guides", ["API", "SUBPLOTS", "COORDINATES", "EXTENDING",
                "THEMES", "AI_ATTRS"]),
    ("Project", ["ARCHITECTURE", "PHILOSOPHY"]),
]
DOC_STEMS = [s for _, stems in DOC_GROUPS for s in stems]

# Cookbook recipes shown as cards on the home page.
HIGHLIGHT_SLUGS = ["annotated-heatmap", "tracks", "ring-tree"]

# Cookbook: composed, multi-panel recipes only. Single-artist examples
# don't belong here — they live on that artist's reference page.
CATEGORIES = [
    ("Composition", ["anscombe", "facets", "annotated-heatmap", "tracks"]),
    ("Circular", ["circular", "ring-tree", "chord"]),
]
COOKBOOK_SLUGS = {s for _, slugs in CATEGORIES for s in slugs}

# Artist name -> example slug embedded on its reference page as the
# worked example (single-artist examples, retired from the cookbook).
EMBED_EXAMPLE = {
    "scatter": "scatter", "line": "line", "bar": "bar", "hist": "hist",
    "violin": "violin", "heatmap": "heatmap", "ecdf": "ecdf",
    "boxplot": "box-strip", "strip": "box-strip", "swarm": "swarm",
    "pointplot": "pointplot", "ridge": "ridge", "qq": "qq",
    "hexbin": "hexbin", "kde_2d": "kde-2d", "imshow": "imshow",
}

# Artist name -> cookbook recipe that features it.
COOKBOOK_LINKS = {
    "regression": "anscombe", "dendrogram": "annotated-heatmap",
    "axhline": "tracks", "chord_ribbon": "chord", "chord_links": "chord",
}

# Non-artist reference pages: coordinates and layout machinery.
# Each entry: slug, display name, snippet -> `c`.
CONCEPTS = [
    ("circular-coordinate", "pt.CircularCoordinate", """\
df = {"cat": list("abcdefgh"), "val": [3, 5, 2, 6, 4, 7, 3, 5]}

c = pt.chart(df, aes(x="cat", y="val", fill="cat"), legend=False)
c.coordinate(pt.CircularCoordinate())
c.add_bar()
"""),
    ("sectors", "c.sectors / pt.Sectors", """\
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
"""),
    ("grid", "pt.grid / | / attachments", """\
import math
xs = [i * 0.2 for i in range(40)]
signal = {"x": xs, "y": [math.sin(x) for x in xs]}
counts = {"cat": ["a", "b", "c"], "n": [4, 7, 3]}
values = {"x": [0.1, 0.4, 0.5, 0.55, 0.7, 0.8, 0.9, 1.1, 1.3]}

a = pt.chart(signal, aes(x="x", y="y"), title="signal",
             data_width=200, data_height=130)
a.add_line()
b = pt.chart(counts, aes(x="cat", y="n"), title="counts",
             data_width=200, data_height=130)
b.add_bar()
d = pt.chart(values, aes(x="x"), title="dist",
             data_width=200, data_height=130)
d.add_hist(bins=6)
c = pt.grid([[a, b], [d, None]])
"""),
    ("facet", "pt.facet", """\
import math
raw = pt.load_dataset("penguins")
keep = [i for i in range(len(raw["species"]))
        if not math.isnan(raw["bill_length_mm"][i])
        and not math.isnan(raw["bill_depth_mm"][i])]
df = {k: [raw[k][i] for i in keep]
      for k in ("species", "bill_length_mm", "bill_depth_mm")}

c = pt.facet(df, by="species", col_wrap=3,
             data_width=150, data_height=130)
c.add_scatter(aes(x="bill_length_mm", y="bill_depth_mm"),
              size=2, alpha=0.7)
"""),
    ("legend", "pt.legend", """\
import math
xs = [i * 0.1 for i in range(64)]
waves = {"t": xs, "sin": [math.sin(x) for x in xs],
         "cos": [math.cos(x) for x in xs]}

a = pt.chart(waves, aes(x="t"), data_width=260, data_height=170,
             xlabel="t")
a.add_line(aes(y="sin"), label="sin(t)")
a.add_line(aes(y="cos"), label="cos(t)", linestyle="--")
c = a | pt.legend(a)
"""),
]

# The "For AI agents" page: the thesis in three pillars, each a group
# of sections on the one page. Groups drive the page's h2 structure,
# its sidebar and the home-page pillar links (#seams, #verify,
# #extend); sections drive the search index.
AGENT_GROUPS = [
    ("seams", "Inspect every seam", [
        ("journal", "The journal: what was recorded"),
        ("ir", "The resolved IR: what render decided"),
        ("svg-attrs", "The SVG describes itself"),
        ("regions", "Where the chrome landed"),
        ("lint", "Overlap and clipping, as data"),
        ("layout", "The layout, drawn as a diagram"),
    ]),
    ("verify", "Verify, don't trust", [
        ("bytes", "Diff the bytes"),
    ]),
    ("extend", "Extend the vocabulary", [
        ("new-artist", "A new plot type is three functions"),
    ]),
    ("status", "Status", [
        ("roadmap", "Where this is going"),
    ]),
]
AGENT_SECTIONS = [(sid, t) for _, _, secs in AGENT_GROUPS
                  for sid, t in secs]

# The chart the seam sections inspect.
AGENT_CHART = """\
df = {"x": [1, 2, 3, 4], "y": [2, 4, 3, 5], "g": ["a", "a", "b", "b"]}

c = pt.chart(df, aes(x="x", y="y", color="g"), title="demo")
c.add_line()
"""

# Deliberately broken: five long category labels on a narrow chart.
AGENT_LINT_BROKEN = """\
df = {"treatment": ["alpha-treatment", "beta-treatment",
                    "gamma-treatment", "delta-treatment",
                    "epsilon-treatment"],
      "response": [3, 5, 2, 6, 4]}

c = pt.chart(df, aes(x="treatment", y="response"),
             data_width=260, data_height=180)
c.add_bar()

from plotlet.lint import lint
lint(c)
"""

AGENT_LINT_FIX = """\
c.xticks(rotation=90)
lint(c)
"""

AGENT_LAYOUT = """\
signal = {"x": [0, 1, 2, 3], "y": [0.0, 1.0, 0.5, 0.8]}
counts = {"cat": ["a", "b", "c"], "n": [4, 7, 3]}

a = pt.chart(signal, aes(x="x", y="y"), data_width=200, data_height=130)
a.add_line()
b = pt.chart(counts, aes(x="cat", y="n"), data_width=200, data_height=130)
b.add_bar()
g = pt.grid([[a, b]])

d = pt.layout_diagram(g)  # a Chart like any other — render or compose it
"""

# The complete lollipop artist from docs/EXTENDING.md, condensed.
AGENT_EXTEND = """\
from plotlet.utils import to_list, pack_opts
from plotlet.draw import segment, circle

def record(data=None, x=None, y=None, color=None, label=None):
    return {"type": "lollipop", "xs": to_list(data[x]),
            "ys": to_list(data[y]),
            "opts": pack_opts(color=color, label=label)}

def xdomain(a): return a["xs"]
def ydomain(a): return list(a["ys"]) + [0]   # stems start at 0

def draw(a, ctx):
    color = a["opts"].get("color") or ctx.color
    y0 = ctx.y_scale(0)
    parts = []
    for x, y in zip(a["xs"], a["ys"]):
        px, py = ctx.x_scale(x), ctx.y_scale(y)
        parts.append(segment(px, y0, px, py, color=color, width=1.5))
        parts.append(circle(px, py, 5, fill=color))
    return "".join(parts)

pt.add_artist(pt.ArtistSpec(name="lollipop", record=record,
                            xdomain=xdomain, ydomain=ydomain, draw=draw))

df = {"x": [1, 2, 3, 4, 5], "y": [3, 7, 2, 9, 4]}

c = pt.chart(df, aes(x="x", y="y"), data_width=300, data_height=180)
c.add_lollipop()
"""


def doc_file(stem: str) -> str:
    return f"docs-{stem.lower()}.html"


def ref_file(name: str) -> str:
    return f"reference-{name}.html"


def chapter_file(chapters: list[dict], i: int) -> str:
    return "tutorial.html" if i == 0 else f"tutorial-{chapters[i]['slug']}.html"


# ---------------------------------------------------------------------------
# 2. Figures — everything shown on the site is executed at build time
# ---------------------------------------------------------------------------

def core_artists() -> list[str]:
    return sorted({row["name"] for row in pt.artist_table()
                   if row["origin"] == "core"})


def namespace_ids(svg: str, prefix: str) -> str:
    """Prefix every id defined in `svg` (and its url(#…)/href="#…"
    references) so several inlined figures on one page can't capture
    each other's clip paths."""
    for i in set(re.findall(r'id="([^"]+)"', svg)):
        svg = svg.replace(f'id="{i}"', f'id="{prefix}-{i}"')
        svg = svg.replace(f'url(#{i})', f'url(#{prefix}-{i})')
        svg = svg.replace(f'href="#{i}"', f'href="#{prefix}-{i}"')
    return svg


def load_examples() -> list[dict]:
    """Run site/examples/*.py in filename order. Each file must leave
    the finished figure in ``c`` — the same convention as every other
    snippet on the site; its module docstring supplies the title
    (first line) and blurb (rest)."""
    out = []
    for path in sorted(EXAMPLES.glob("*.py")):
        src = path.read_text()
        mod = ast.parse(src)
        doc = ast.get_docstring(mod) or path.stem
        title, _, blurb = doc.partition("\n")

        # Displayed code = source minus the docstring.
        first = mod.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            code = "\n".join(src.splitlines()[first.end_lineno:]).strip("\n")
        else:
            code = src.strip("\n")

        ns: dict = {}
        exec(compile(src, str(path), "exec"), ns)
        slug = re.sub(r"^\d+_", "", path.stem).replace("_", "-")
        svg = namespace_ids(ns["c"].to_svg(), f"eg-{slug}")

        out.append({
            "slug": slug,
            "title": title.strip(),
            "blurb": blurb.strip(),
            "code": code,
            "svg": svg,
        })
        print(f"  rendered {path.name}")
    return out


def render_tiles() -> list[dict]:
    """Run every plot-types snippet; fail loudly if the tile set drifts
    from the registered core artists."""
    tile_names = [name for _, name, _ in TILES]
    missing = set(core_artists()) - set(tile_names)
    extra = set(tile_names) - set(core_artists())
    if missing or extra:
        raise SystemExit(f"plot_types.py out of sync with the artist "
                         f"registry: missing={sorted(missing)} "
                         f"extra={sorted(extra)}")
    doc_host = pt.chart({"x": [1], "y": [1]})
    out = []
    for category, name, snippet in TILES:
        ns: dict = {"pt": pt, "aes": aes}
        exec(compile(snippet, f"<plot_types:{name}>", "exec"), ns)
        out.append({
            "category": category,
            "name": name,
            "code": snippet.strip("\n"),
            "svg": namespace_ids(ns["c"].to_svg(), f"t-{name}"),
            "doc": (getattr(doc_host, f"add_{name}").__doc__ or "").strip(),
        })
    print(f"  rendered {len(out)} plot-type tiles")
    return out


def render_concepts() -> list[dict]:
    """The CONCEPTS snippets, shaped like tiles so the reference treats
    both the same way."""
    doc_src = {
        "circular-coordinate": pt.CircularCoordinate.__doc__,
        "sectors": pt.Sectors.__doc__,
        "grid": pt.grid.__doc__,
        "facet": pt.facet.__doc__,
        "legend": pt.legend.__doc__,
    }
    out = []
    for slug, display, snippet in CONCEPTS:
        ns: dict = {"pt": pt, "aes": aes}
        exec(compile(snippet, f"<concept:{slug}>", "exec"), ns)
        out.append({
            "category": "Coordinates & layout",
            "name": slug,
            "display": display,
            "code": snippet.strip("\n"),
            "svg": namespace_ids(ns["c"].to_svg(), f"cn-{slug}"),
            "doc": (doc_src.get(slug) or "").strip(),
        })
    print(f"  rendered {len(out)} concept pages")
    return out


def _ext_registered_name(py_path: str) -> str | None:
    """The ArtistSpec name a module registers, read from its source.

    Needed when the method name differs from the module name
    (boxenplot.py registers "boxen", so the call is c.add_boxen)."""
    for node in ast.walk(ast.parse(Path(py_path).read_text())):
        if isinstance(node, ast.Call):
            f = node.func
            if (getattr(f, "id", None) or getattr(f, "attr", None)) == "ArtistSpec":
                for kw in node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        return kw.value.value
    return None


def render_ext_gallery() -> list[dict]:
    """One tile per module of the installed plotlet-extensions package.

    Every module in that package ships ``SUMMARY`` and ``demo()`` (the
    convention its own gallery builder relies on). A module whose demo
    raises is skipped so one broken extension can't take the site down,
    but the drop is printed loudly — never silently.

    Importing the package registers every artist at once, so tiles
    don't need per-module imports. Each tile carries its real call:
    ``method`` (most modules register a chart method — not always the
    module's name) or ``func`` (composition helpers like jointplot,
    which register nothing and are imported as functions)."""
    try:
        import plotlet.extensions as ext_pkg
    except ImportError:
        print("  plotlet-extensions not installed — skipping the gallery")
        return []
    import importlib
    import pkgutil
    out, dropped = [], []
    names = sorted(m.name for m in pkgutil.iter_modules(ext_pkg.__path__)
                   if not m.name.startswith("_"))
    probe = pt.chart()
    for name in names:
        try:
            mod = importlib.import_module(f"plotlet.extensions.{name}")
            svg = mod.demo().to_svg()
        except Exception as e:
            dropped.append(name)
            print(f"  ! {name} failed: {e}")
            continue
        if hasattr(probe, f"add_{name}"):
            method, func = f"add_{name}", None
        elif callable(getattr(mod, name, None)):
            method, func = None, name
        else:
            reg = _ext_registered_name(mod.__file__)
            method, func = f"add_{reg or name}", None
        out.append({
            "name": name,
            "summary": getattr(mod, "SUMMARY", ""),
            "method": method,
            "func": func,
            "svg": namespace_ids(svg, f"x-{name}"),
        })
    print(f"  rendered {len(out)} extension tiles")
    if dropped:
        print(f"  !! DROPPED from the gallery: {', '.join(dropped)}")
    return out


def render_agents() -> dict:
    """Run the agents-page demos and capture their real output. Every
    figure and every output block on that page is produced here, on
    every build — a demo that stops working fails the build."""
    from plotlet.lint import lint

    ag: dict = {}

    # The chart the seam sections inspect.
    ns: dict = {"pt": pt, "aes": aes}
    exec(compile(AGENT_CHART, "<agents:chart>", "exec"), ns)
    c = ns["c"]
    ag["chart_svg"] = namespace_ids(c.to_svg(), "ag-chart")

    # Seam 1: the journal.
    entries = pt.to_journal(c).to_dict()["entries"]
    ag["journal"] = json.dumps(entries, indent=1)

    # Seam 2: the resolved IR — show the two decisions render made
    # here: the autoscaled y limits and the palette assignment.
    panel = pt.to_ir(c).resolve().to_dict()["root"]["children"][0]
    ag["ir"] = "\n".join([
        repr({k: panel["scales"]["y"][k] for k in ("kind", "lo", "hi")}),
        repr([(a["type"], a["opts"]["label"], a["_color"])
              for a in panel["state"]["artists"]]),
    ])

    # Seam 3: the data-plotlet-* attributes in the SVG itself.
    ag["attr_fragment"] = _data_attr_fragment(c.to_svg())

    # Seam 4: chrome geometry.
    ag["regions"] = "\n".join(repr(r) for r in c.regions()[:8]) + "\n…"

    # Seam 5: lint — broken, then fixed. The build asserts the fix
    # really clears the warnings.
    ns = {"pt": pt, "aes": aes}
    exec(compile(AGENT_LINT_BROKEN, "<agents:lint>", "exec"), ns)
    broken = ns["c"]
    warnings = lint(broken)
    if not warnings:
        raise SystemExit("agents page: the lint demo no longer warns")
    ag["lint_broken_svg"] = namespace_ids(broken.to_svg(), "ag-lint-broken")
    ag["lint_broken"] = "\n".join(str(w) for w in warnings)
    exec(compile(AGENT_LINT_FIX, "<agents:lint-fix>", "exec"), ns)
    if lint(ns["c"]):
        raise SystemExit("agents page: the lint fix no longer lints clean")
    ag["lint_fixed_svg"] = namespace_ids(ns["c"].to_svg(), "ag-lint-fixed")
    ag["lint_fixed"] = repr(lint(ns["c"]))

    # Seam 6: the layout diagram, next to the grid it describes.
    ns = {"pt": pt, "aes": aes}
    exec(compile(AGENT_LAYOUT, "<agents:layout>", "exec"), ns)
    ag["layout_grid_svg"] = namespace_ids(ns["g"].to_svg(), "ag-layout-g")
    ag["layout_diagram_svg"] = namespace_ids(ns["d"].to_svg(), "ag-layout-d")

    # Pillar 3: a complete custom plot type, registered and used.
    ns = {"pt": pt, "aes": aes}
    exec(compile(AGENT_EXTEND, "<agents:extend>", "exec"), ns)
    ag["extend_svg"] = namespace_ids(ns["c"].to_svg(), "ag-extend")

    print("  rendered the agents page demos")
    return ag


def load_chapters() -> list[dict]:
    """Tutorial chapters from site/tutorials/*.py, in filename order.
    Each file defines PAGE = {slug, title, blurb, sections}."""
    chapters = []
    for path in sorted((HERE / "tutorials").glob("*.py")):
        ns: dict = {}
        exec(compile(path.read_text(), str(path), "exec"), ns)
        chapters.append(ns["PAGE"])
    return chapters


def _data_attr_fragment(svg: str) -> str:
    """A readable excerpt of the machine-facing attributes: the root tag
    and the first artist group, data-plotlet-* attrs one per line."""
    lines = []
    for tag_re in (r"<svg[^>]*>", r"<g[^>]*data-plotlet-type=[^>]*>"):
        m = re.search(tag_re, svg)
        if not m:
            continue
        tag = m.group()
        attrs = re.findall(r'(data-plotlet-[a-z0-9-]+="[^"]*")', tag)
        head = tag.split()[0].lstrip("<")
        lines.append(f"<{head}")
        lines.extend(f"   {a}" for a in attrs)
        lines.append("   …>")
    return "\n".join(lines)


def render_sections(chapter: dict) -> list[dict]:
    """Run a chapter's section snippets; the "ai" section additionally
    gets a fragment of its own SVG and its region report."""
    out = []
    for sec in chapter["sections"]:
        item = dict(sec)
        code = sec.get("code")
        if code:
            ns: dict = {"pt": pt, "aes": aes}
            exec(compile(code, f"<tutorial:{sec['id']}>", "exec"), ns)
            chart = ns.get("c")
            if chart is not None:
                item["svg"] = namespace_ids(
                    chart.to_svg(), f"tu-{chapter['slug']}-{sec['id']}")
            if sec["id"] == "ai" and chart is not None:
                item["attr_fragment"] = _data_attr_fragment(chart.to_svg())
                item["regions"] = "\n".join(
                    repr(r) for r in chart.regions()[:5]) + "\n…"
        out.append(item)
    n = sum(1 for s in out if "svg" in s)
    print(f"  {chapter['slug']}: {n} figures")
    return out


# ---------------------------------------------------------------------------
# 3. Docs — docs/*.md rendered to HTML
# ---------------------------------------------------------------------------

def _gh_slugify(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\w\- ]", "", html.unescape(text).lower())
    return text.strip().replace(" ", "-")


class _DocRenderer(mistune.HTMLRenderer):
    def block_code(self, code, info=None):
        lang = (info or "").strip().lower()
        if lang.startswith("py"):
            return f"<pre><code>{highlight(code)}</code></pre>\n"
        return f"<pre><code>{html.escape(code)}</code></pre>\n"


_MARKDOWN = mistune.create_markdown(renderer=_DocRenderer(escape=False),
                                    plugins=["table", "strikethrough"])


def _rewrite_doc_link(href: str, stem: str) -> str:
    """Map a link found in docs/<stem>.md to its site or GitHub target.
    Unresolvable relative links fail the build."""
    if re.match(r"^(https?:|mailto:|#)", href):
        return href
    path, _, anchor = href.partition("#")
    anchor = f"#{anchor}" if anchor else ""
    if path.endswith(".md"):
        target = Path(path).name[:-3]
        if target.upper() in DOC_STEMS:
            return doc_file(target.upper()) + anchor
        if target.upper() == "README":
            return GITHUB + anchor
        raise SystemExit(f"docs/{stem}.md links to unknown doc: {href}")
    resolved = (HERE.parent / "docs" / path).resolve()
    repo = HERE.parent.resolve()
    if not resolved.exists() or not resolved.is_relative_to(repo):
        raise SystemExit(f"docs/{stem}.md has a dead relative link: {href}")
    return f"{GITHUB}/blob/main/{resolved.relative_to(repo)}{anchor}"


def render_docs() -> list[dict]:
    out = []
    for stem in DOC_STEMS:
        src = (HERE.parent / "docs" / f"{stem}.md").read_text()
        body = _MARKDOWN(src)
        # Lift the leading h1 out as the page title.
        m = re.match(r"\s*<h1>(.*?)</h1>", body, re.S)
        title = (html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
                 if m else stem.title())
        if m:
            body = body[m.end():]
        # GitHub-style ids on h2/h3 so anchors and search work.
        headings = []

        def _add_id(match):
            level, text = match.group(1), match.group(2)
            hid = _gh_slugify(text)
            if level == "2":
                headings.append(
                    (html.unescape(re.sub(r"<[^>]+>", "", text)), hid))
            return f'<h{level} id="{hid}">{text}</h{level}>'

        body = re.sub(r"<h([23])>(.*?)</h\1>", _add_id, body, flags=re.S)
        body = re.sub(r'href="([^"]+)"',
                      lambda m2: f'href="{_rewrite_doc_link(m2.group(1), stem)}"',
                      body)
        out.append({"stem": stem, "title": title.strip(),
                    "body": body, "headings": headings})
        print(f"  rendered docs/{stem}.md")
    return out


# ---------------------------------------------------------------------------
# 4. Page shell — CSS, client JS, the outer frame, the sidebar
# ---------------------------------------------------------------------------

# Minimal Python syntax highlighting (cosmetic only).
_TOKEN = re.compile(
    r"""(?P<comment>\#[^\n]*)"""
    r"""|(?P<string>[rbf]*(?:'''.*?'''|\"\"\".*?\"\"\"|'[^'\n]*'|"[^"\n]*"))"""
    r"""|(?P<kw>\b(?:import|from|for|in|if|else|elif|not|and|or|def|"""
    r"""return|as|with|lambda|class|True|False|None)\b)"""
    r"""|(?P<num>\b\d+(?:\.\d+)?\b)""",
    re.DOTALL,
)


def highlight(code: str) -> str:
    pieces, pos = [], 0
    for m in _TOKEN.finditer(code):
        pieces.append(html.escape(code[pos:m.start()]))
        cls = m.lastgroup
        pieces.append(f'<span class="tok-{cls}">{html.escape(m.group())}</span>')
        pos = m.end()
    pieces.append(html.escape(code[pos:]))
    return "".join(pieces)


CSS = """
:root {
  --ink: #24243a; --muted: #6a6a80; --line: #e4e4ec; --bg: #ffffff;
  --soft: #f6f6fa; --accent: #534AB7; --accent-ink: #423a99;
  --code-bg: #f8f8fb;
}
* { box-sizing: border-box; }
html { overscroll-behavior-y: none; }
body {
  margin: 0; color: var(--ink); background: var(--bg);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, sans-serif;
  min-height: 100vh; display: flex; flex-direction: column;
}
main { flex: 1; width: 100%; }
a { color: var(--accent-ink); text-decoration: none; }
a:hover { text-decoration: underline; }
code, pre { font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

header.site {
  border-bottom: 1px solid var(--line); background: var(--bg);
  position: sticky; top: 0; z-index: 10;
}
.example, .tile, h2.cat, section[id] { scroll-margin-top: 70px; }
header.site .inner {
  max-width: 1080px; margin: 0 auto; padding: 14px 24px;
  display: flex; align-items: baseline; gap: 24px;
}
.search { margin-left: auto; position: relative; align-self: center; }
.search input {
  width: 190px; padding: 6px 12px; font-size: 14px;
  border: 1px solid var(--line); border-radius: 8px;
  background: var(--soft); color: var(--ink); outline: none;
}
.search input:focus { border-color: var(--accent); background: var(--bg); }
.search #sh {
  position: absolute; right: 0; top: calc(100% + 6px); width: 340px;
  max-height: 60vh; overflow-y: auto; background: var(--bg);
  border: 1px solid var(--line); border-radius: 10px;
  box-shadow: 0 8px 28px rgba(30, 30, 60, 0.12); z-index: 20;
}
.search #sh a {
  display: flex; justify-content: space-between; gap: 12px;
  padding: 8px 14px; font-size: 14px; color: var(--ink);
  border-bottom: 1px solid var(--soft);
}
.search #sh a:hover { background: var(--soft); text-decoration: none; }
.search #sh em { color: var(--muted); font-style: normal; font-size: 12.5px; }
.search #sh .none { padding: 10px 14px; font-size: 14px; color: var(--muted); }
@media (max-width: 720px) { .search { display: none; } }
header.site .brand { font-weight: 700; font-size: 18px; color: var(--ink); }
header.site .brand .ver { font-weight: 500; font-size: 13px; color: var(--muted); }
header.site nav { display: flex; gap: 18px; font-size: 15px; }
header.site nav a.active { color: var(--ink); font-weight: 600; }

main { max-width: 1080px; margin: 0 auto; padding: 32px 24px 64px; }

.hero { padding: 28px 0 8px; }
.hero .lead { color: var(--ink); }
.hero .lead a.main { font-weight: 700; }
.hero h1 { font-size: 34px; line-height: 1.2; margin: 0 0 10px; }
.hero h1 code { font-size: inherit; }
.hero p.tag { font-size: 19px; color: var(--muted); margin: 0 0 22px; max-width: 46em; }
.install {
  margin: 22px 0 0; display: inline-block; background: var(--code-bg);
  border: 1px solid var(--line); border-radius: 8px; padding: 9px 16px;
}

main:has(> .home) { padding: 16px 24px 26px; }
.home .hero { padding: 10px 0 0; }
.home .hero h1 {
  display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
}
.home .hero h1 .install { margin: 0; font-weight: 400; padding: 7px 14px; }
.home .hero h1 .install code { font-size: 14px; }
.home .cards { margin: 24px 0 0; }
.home .card .thumb { height: 168px; }
.home h2.rule {
  margin: 26px 0 0; padding-top: 18px; font-size: 20px;
}
.home .wayfind { margin: 14px 0 0; }

.wayfind {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 18px; margin: 34px 0 8px;
}
.wayfind a {
  border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px;
  font-size: 14.5px; color: var(--muted); line-height: 1.5;
}
.wayfind a strong { display: block; color: var(--ink); font-size: 15.5px;
  margin-bottom: 2px; }
.wayfind a:hover { text-decoration: none; border-color: var(--accent); }
.wayfind a.hi {
  border-color: var(--accent); background: #f7f6fc;
}
.wayfind a.hi strong { color: var(--accent-ink); }

.split { display: flex; gap: 32px; align-items: flex-start; flex-wrap: wrap; margin: 40px 0; }
.split > div { flex: 1 1 380px; min-width: 320px; }

.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 18px; }
.card {
  border: 1px solid var(--line); border-radius: 10px; padding: 12px;
  background: #fff; text-align: center;
}
.card .thumb { display: flex; justify-content: center; align-items: center; height: 220px; overflow: hidden; }
.card .thumb svg { max-width: 100%; max-height: 100%; height: auto; }
.card h3 { font-size: 15px; margin: 10px 0 0; font-weight: 600; }

h2.rule { border-top: 1px solid var(--line); padding-top: 28px; margin-top: 44px; }

h2.cat { font-size: 26px; margin-bottom: 4px; }

.example { padding: 26px 0 10px; }
.example h3 { margin: 0 0 6px; font-size: 19px; }
.example p.blurb { color: var(--muted); margin: 0 0 18px; max-width: 52em; }
.fig { margin: 0 0 14px; overflow-x: auto; background: #fff; }
.fig svg { max-width: 100%; height: auto; display: block; }
details.code { border: 1px solid var(--line); border-radius: 8px; background: var(--code-bg); }
details.code summary {
  cursor: pointer; padding: 8px 14px; font-size: 14px; color: var(--accent-ink);
  user-select: none;
}
details.code pre { margin: 0; padding: 4px 16px 14px; overflow-x: auto; }
.tiles {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(235px, 1fr));
  gap: 18px; margin: 18px 0 34px;
}
.tile { border: 1px solid var(--line); border-radius: 10px; padding: 12px; }
.tile h4 { margin: 0 0 8px; font-weight: 600; }
.tile h4 code { font-size: 14px; }
.tile .thumb {
  height: 165px; display: flex; align-items: center; justify-content: center;
  overflow: hidden; margin-bottom: 10px;
}
.tile .thumb svg { max-width: 100%; max-height: 100%; width: auto; height: auto; }
.tile details.code summary { padding: 5px 10px; font-size: 13px; }
.tile details.code pre { padding: 2px 10px 10px; font-size: 12px; }
.tiles-lg { grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); }
.tiles-lg .thumb { height: 235px; }
.tile p.blurb { color: var(--muted); font-size: 13px; margin: 0 0 8px; }
.tile pre.imp { margin: 0 0 8px; font-size: 12px; }
.tile a.src { font-size: 13px; }
h3.tiles-cat { font-size: 17px; margin: 26px 0 0; }
a.tile-link { display: block; color: var(--ink); }
a.tile-link:hover { text-decoration: none; border-color: var(--accent); }
aside.toc-side .side-cat { margin: 14px 0 4px; font-weight: 600;
  font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--muted); }
aside.toc-side ul.side-flat { list-style: none; margin: 0;
  padding-left: 10px; border-left: 2px solid var(--line); }
aside.toc-side ul.side-flat li { margin: 2px 0; }
aside.toc-side ul.side-flat code { font-size: 12.5px; }
aside.toc-side .side-title a { color: var(--muted); }
.doc-body { font-size: 15.5px; }
.doc-body h2 { font-size: 24px; margin: 34px 0 8px; }
.doc-body h3 { font-size: 18px; margin: 26px 0 6px; }
.doc-body pre {
  background: var(--code-bg); border: 1px solid var(--line);
  border-radius: 8px; padding: 12px 16px; overflow-x: auto;
}
.doc-body table {
  border-collapse: collapse; margin: 16px 0; font-size: 14px;
  display: block; overflow-x: auto; max-width: 100%;
}
.doc-body th, .doc-body td {
  border: 1px solid var(--line); padding: 6px 12px; text-align: left;
  vertical-align: top;
}
.doc-body th { background: var(--soft); }
.doc-body blockquote {
  margin: 16px 0; padding: 2px 18px; border-left: 3px solid var(--accent);
  background: var(--soft); border-radius: 0 8px 8px 0; color: var(--muted);
}
.doc-body img { max-width: 100%; }
pre.docstring {
  background: var(--soft); border: 1px solid var(--line);
  border-radius: 8px; padding: 14px 18px; overflow-x: auto;
  font-size: 13px; line-height: 1.55; white-space: pre-wrap;
}
.ref-meta { color: var(--muted); font-size: 14.5px; margin: 0 0 18px; }
.ref-fig { margin: 0 0 18px; overflow-x: auto; }
.ref-fig svg { max-width: 100%; height: auto; display: block; }

pre.tut-code {
  background: var(--code-bg); border: 1px solid var(--line);
  border-radius: 8px; padding: 12px 16px; overflow-x: auto;
  margin: 0 0 16px;
}
.example h4 { margin: 0 0 6px; font-size: 14.5px; color: var(--muted); }
.tut-layout { display: flex; gap: 44px; align-items: flex-start; }
.tut-content { flex: 1; min-width: 0; }
aside.toc-side {
  position: sticky; top: 77px; flex: 0 0 210px;
  font-size: 14px; line-height: 1.5;
  max-height: calc(100vh - 101px); overflow-y: auto;
  overscroll-behavior: contain;
  border-right: 1px solid var(--line); padding: 4px 20px 12px 0;
}
aside.toc-side .side-title {
  margin: 0 0 8px; font-weight: 700; font-size: 13px;
  text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted);
}
aside.toc-side ol { margin: 0; padding-left: 20px; }
aside.toc-side ol > li { margin: 5px 0; }
aside.toc-side li.current > span { font-weight: 600; color: var(--ink); }
aside.toc-side ul {
  list-style: none; margin: 4px 0 8px; padding-left: 12px;
  border-left: 2px solid var(--line);
}
aside.toc-side ul li { margin: 3px 0; }
aside.toc-side ul a { color: var(--muted); }
aside.toc-side ul a:hover { color: var(--accent-ink); }
@media (max-width: 900px) {
  .tut-layout { display: block; }
  aside.toc-side { position: static; max-height: none; border-right: 0;
    border-bottom: 1px solid var(--line); padding: 0 0 14px;
    margin-bottom: 10px; }
}
.chapter-nav { border-top: 1px solid var(--line); padding-top: 20px;
  margin-top: 36px; font-size: 15px; }
.tok-kw { color: #7c4dbe; }
.tok-string { color: #1a7f37; }
.tok-comment { color: #8b8b9e; font-style: italic; }
.tok-num { color: #b25d09; }

footer.site {
  border-top: 1px solid var(--line); color: var(--muted); font-size: 14px;
}
footer.site .inner { max-width: 1080px; margin: 0 auto; padding: 18px 24px; }
"""


# Set once in main() before any page is built; embedded in every page.
SEARCH_JSON = "[]"

# True once the extensions gallery rendered; gates its nav entry so a
# build without plotlet-extensions never links to a missing page.
HAS_EXTENSIONS = False

SEARCH_JS = """
(function () {
  var q = document.getElementById('sq'), h = document.getElementById('sh');
  if (!q) return;
  var DATA = JSON.parse(document.getElementById('sd').textContent);
  function render(v) {
    v = v.trim().toLowerCase();
    if (!v) { h.hidden = true; h.innerHTML = ''; return; }
    var hits = DATA.filter(function (d) {
      return d.t.toLowerCase().indexOf(v) !== -1 ||
             d.g.toLowerCase().indexOf(v) !== -1;
    }).slice(0, 12);
    h.innerHTML = hits.map(function (d) {
      return '<a href="' + d.u + '"><span>' + d.t + '</span><em>' +
             d.g + '</em></a>';
    }).join('') || '<div class="none">no matches</div>';
    h.hidden = false;
  }
  q.addEventListener('input', function () { render(q.value); });
  q.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      var a = h.querySelector('a');
      if (a) location.href = a.getAttribute('href');
    }
    if (e.key === 'Escape') { q.value = ''; render(''); q.blur(); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement !== q) {
      e.preventDefault(); q.focus();
    }
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.search')) { h.hidden = true; }
  });
})();
"""

# Two jobs. (1) Pin the sidebar's sticky offset to its natural resting
# position, so it never shifts when the page scrolls or jumps to an
# anchor (the CSS top is a close no-JS fallback). (2) The sidebar is
# its own scroll container, so each page load starts it at the top:
# when a sidebar link was just clicked, put the now-current item back
# at the same height it sat at before the click, so the sidebar
# appears not to move. Arriving any other way (search, top nav),
# center the current item if it's out of view; index pages have no
# current item and stay at the top.
SIDEBAR_JS = """
(function () {
  var side = document.querySelector('aside.toc-side');
  if (!side) return;
  if (getComputedStyle(side).position === 'sticky') {
    var natural = side.parentElement.getBoundingClientRect().top +
                  window.pageYOffset;
    side.style.top = natural + 'px';
    side.style.maxHeight = 'calc(100vh - ' + (natural + 24) + 'px)';
  }
  var cur = side.querySelector('.current');
  var off = sessionStorage.getItem('plotlet-side-off');
  sessionStorage.removeItem('plotlet-side-off');
  if (cur) {
    if (off !== null) {
      side.scrollTop = cur.offsetTop - off;
    } else if (cur.offsetTop < side.scrollTop ||
               cur.offsetTop > side.scrollTop + side.clientHeight - 28) {
      side.scrollTop = cur.offsetTop - side.clientHeight / 2;
    }
  }
  side.addEventListener('click', function (e) {
    var a = e.target.closest('a');
    if (!a) return;
    var item = a.closest('li') || a;
    sessionStorage.setItem('plotlet-side-off',
                           item.offsetTop - side.scrollTop);
  });
})();
"""


def page(title: str, body: str, active: str) -> str:
    def nav(href: str, label: str, key: str) -> str:
        cls = ' class="active"' if key == active else ""
        return f'<a href="{href}"{cls}>{label}</a>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(TAGLINE)}">
<style>{CSS}</style>
</head>
<body>
<header class="site"><div class="inner">
  <span class="brand">plotlet <span class="ver">v{VERSION}</span></span>
  <nav>
    {nav('index.html', 'Home', 'home')}
    {nav('tutorial.html', 'Tutorial', 'tutorial')}
    {nav('reference.html', 'Reference', 'reference')}
    {nav('extensions.html', 'Extensions', 'extensions') if HAS_EXTENSIONS else ''}
    {nav('cookbook.html', 'Cookbook', 'cookbook')}
    {nav('agents.html', 'Agents', 'agents')}
    {nav('docs-api.html', 'Docs', 'docs')}
    <a href="{GITHUB}">GitHub</a>
  </nav>
  <div class="search">
    <input id="sq" type="search" placeholder="Search&hellip; ( / )"
           autocomplete="off" spellcheck="false">
    <div id="sh" hidden></div>
  </div>
</div></header>
<main>
{body}
</main>
<footer class="site"><div class="inner">
  plotlet v{VERSION} &middot; MIT license &middot;
  <a href="{GITHUB}">source</a> &middot;
  <a href="{EXTENSIONS}">extensions</a> &middot;
  <a href="{COOKBOOK}">cookbook</a>
</div></footer>
<script id="sd" type="application/json">{SEARCH_JSON}</script>
<script>{SEARCH_JS}</script>
<script>{SIDEBAR_JS}</script>
</body>
</html>
"""


def _sidebar(title: str, groups: list[tuple[str, list[tuple[str, str | None]]]]
             ) -> str:
    """The left sidebar shared by Reference, Cookbook and Docs.
    ``title`` is trusted HTML. ``groups`` is (category, items) pairs;
    each item is (label_html, href), with href None marking the current
    page's own entry. The tutorial builds its sidebar separately — it
    is the one non-flat case (numbered chapters, with the current
    chapter's sections nested under it)."""
    parts = [f'<aside class="toc-side"><p class="side-title">{title}</p>']
    for category, items in groups:
        links = []
        for label, href in items:
            if href is None:
                links.append(f'<li class="current"><span>{label}</span></li>')
            else:
                links.append(f'<li><a href="{href}">{label}</a></li>')
        parts.append(f'<p class="side-cat">{html.escape(category)}</p>'
                     f'<ul class="side-flat">{"".join(links)}</ul>')
    parts.append("</aside>")
    return "".join(parts)


def _by_category(entries: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group tiles/concepts by category, in first-seen order."""
    cats: dict[str, list[dict]] = {}
    for e in entries:
        cats.setdefault(e["category"], []).append(e)
    return list(cats.items())


def _ref_sidebar(entries: list[dict], current: str | None) -> str:
    groups = [(cat, [(f'<code>{e["name"]}</code>',
                      None if e["name"] == current else ref_file(e["name"]))
                     for e in es])
              for cat, es in _by_category(entries)]
    return _sidebar('<a href="reference.html">Reference</a>', groups)


def group_examples(examples: list[dict]) -> list[tuple[str, list[dict]]]:
    by_slug = {e["slug"]: e for e in examples}
    groups = [(title, [by_slug[s] for s in slugs if s in by_slug])
              for title, slugs in CATEGORIES]
    return [(t, es) for t, es in groups if es]


# ---------------------------------------------------------------------------
# 5. Pages
# ---------------------------------------------------------------------------

def build_index(examples: list[dict]) -> str:
    by_slug = {e["slug"]: e for e in examples}
    cards = "".join(
        f'<a class="card" href="cookbook.html#{s}">'
        f'<div class="thumb">{by_slug[s]["svg"]}</div>'
        f'<h3>{html.escape(by_slug[s]["title"])}</h3></a>'
        for s in HIGHLIGHT_SLUGS if s in by_slug
    )

    body = f"""
<div class="home">
<section class="hero">
  <h1>A plotting library built for AI authorship.
  <span class="install"><code>pip install plotlet</code></span></h1>
  <p class="tag">plotlet assumes the author of a figure is often a
  program &mdash; an AI assistant, a test script, a CI job &mdash; that
  can&rsquo;t eyeball pixels. So every pipeline stage answers questions
  as structured data, and the same script produces the same SVG, byte
  for byte, on every machine. Figures a human can diff are the side
  effect.</p>
</section>

<div class="cards">{cards}</div>

<h2 class="rule">Where to start</h2>
<div class="wayfind">
  <a href="tutorial.html"><strong>New to plotlet?</strong>
  The tutorial teaches the whole model in seven short chapters.</a>
  <a href="reference.html"><strong>&ldquo;Does it
  have&hellip;?&rdquo;</strong> The reference has a page per built-in
  mark: minimal call, full docstring, worked examples for the common
  ones.</a>
  <a href="cookbook.html"><strong>Building something bigger?</strong>
  The cookbook has the composed, multi-panel recipes.</a>
  <a class="hi" href="agents.html"><strong>Author is an AI?</strong>
  One page walks the whole thesis with real output: inspect every
  seam, verify by diff, extend the vocabulary.</a>
</div>
</div>
"""
    return page("plotlet — a plotting library built for AI authorship",
                body, "home")


def build_tutorial(chapters: list[dict], i: int, sections: list[dict]) -> str:
    ch = chapters[i]
    side_items = []
    for j, c in enumerate(chapters):
        title = html.escape(c["title"])
        if j == i:
            secs = "".join(
                f'<li><a href="#{s["id"]}">{html.escape(s["title"])}</a></li>'
                for s in sections)
            side_items.append(f'<li class="current"><span>{title}</span>'
                              f'<ul>{secs}</ul></li>')
        else:
            side_items.append(f'<li><a href="{chapter_file(chapters, j)}">'
                              f'{title}</a></li>')
    sidebar = (f'<aside class="toc-side"><p class="side-title">Tutorial</p>'
               f'<ol>{"".join(side_items)}</ol></aside>')
    footer_nav = []
    if i > 0:
        footer_nav.append(f'<a href="{chapter_file(chapters, i - 1)}">&larr; '
                          f'{html.escape(chapters[i - 1]["title"])}</a>')
    if i + 1 < len(chapters):
        footer_nav.append(f'<a href="{chapter_file(chapters, i + 1)}">'
                          f'{html.escape(chapters[i + 1]["title"])} &rarr;</a>')

    parts = []
    for s in sections:
        block = [f'<section class="example" id="{s["id"]}">',
                 f'<h3>{html.escape(s["title"])}</h3>',
                 f'<p class="blurb">{s["prose"]}</p>']
        if s.get("code"):
            block.append(f'<pre class="tut-code"><code>'
                         f'{highlight(s["code"])}</code></pre>')
        if s.get("svg"):
            block.append(f'<div class="fig">{s["svg"]}</div>')
        if s.get("attr_fragment"):
            block.append(f"""
<div class="split">
  <div><h4>from the SVG itself</h4>
  <pre class="tut-code"><code>{html.escape(s['attr_fragment'])}</code></pre></div>
  <div><h4>c.regions()</h4>
  <pre class="tut-code"><code>{html.escape(s['regions'])}</code></pre></div>
</div>""")
        block.append("</section>")
        parts.append("".join(block))

    body = f"""
<div class="tut-layout">
{sidebar}
<div class="tut-content">
<section class="hero">
  <h1>{i + 1}. {html.escape(ch['title'])}</h1>
  <p class="tag">{ch['blurb']} Every snippet on this page is executed
  on every build &mdash; the figures are its output.</p>
</section>
{''.join(parts)}
<p class="chapter-nav">{' &nbsp;&middot;&nbsp; '.join(footer_nav)}</p>
</div>
</div>
"""
    return page(f"plotlet tutorial — {ch['title']}", body, "tutorial")


def build_reference_index(entries: list[dict]) -> str:
    parts = []
    for category, es in _by_category(entries):
        cards = "".join(f"""
<a class="tile tile-link" href="{ref_file(e['name'])}">
  <h4><code>{e.get('display', e['name'])}</code></h4>
  <div class="thumb">{e['svg']}</div>
</a>""" for e in es)
        parts.append(f'<h3 class="tiles-cat">{html.escape(category)}</h3>'
                     f'<div class="tiles">{cards}</div>')

    body = f"""
<div class="tut-layout">
{_ref_sidebar(entries, None)}
<div class="tut-content">
<section class="hero">
  <h1>Reference</h1>
  <p class="tag">Every built-in plot type and the layout machinery,
  one page each. Domain-specific types live in
  <a href="{EXTENSIONS}">plotlet-extensions</a>.</p>
</section>
{''.join(parts)}
</div>
</div>
"""
    return page("plotlet reference", body, "reference")


def build_reference_page(entry: dict, entries: list[dict],
                         examples: list[dict]) -> str:
    by_slug = {e["slug"]: e for e in examples}
    name = entry["name"]

    example = by_slug.get(EMBED_EXAMPLE.get(name, ""))
    recipe = COOKBOOK_LINKS.get(name)
    meta_extra = (f' &middot; used in the <a href="cookbook.html#{recipe}">'
                  f'{recipe.replace("-", " ")}</a> cookbook recipe'
                  if recipe else "")

    # The lead figure is the minimal call's own output — the same figure
    # as this entry's tile on the reference index, so following a tile
    # lands on the plot that was clicked. The worked example, when there
    # is one, follows as its own section.
    worked = ""
    if example:
        code = example["code"]
        worked = (f'<h3>Worked example</h3>'
                  f'<div class="ref-fig">{example["svg"]}</div>'
                  f'<pre class="tut-code"><code>'
                  f'{highlight(code)}</code></pre>')

    doc_html = (f'<h3>Docstring</h3><pre class="docstring">'
                f'{html.escape(entry["doc"])}</pre>'
                if entry["doc"] else "")

    body = f"""
<div class="tut-layout">
{_ref_sidebar(entries, name)}
<div class="tut-content">
<section class="hero">
  <h1><code>{entry.get('display', name)}</code></h1>
  <p class="ref-meta">{html.escape(entry['category'])}{meta_extra}</p>
</section>
<div class="ref-fig">{entry['svg']}</div>
<h3>Minimal call</h3>
<pre class="tut-code"><code>{highlight(entry['code'])}</code></pre>
{worked}
{doc_html}
</div>
</div>
"""
    return page(f"plotlet reference — {name}", body, "reference")


def build_cookbook(examples: list[dict], has_gallery: bool) -> str:
    groups = group_examples(examples)

    side_groups: list = [
        (title, [(html.escape(e["title"]), f'#{e["slug"]}') for e in es])
        for title, es in groups]
    sidebar = _sidebar('<a href="cookbook.html">Cookbook</a>', side_groups)

    sections = []
    for title, es in groups:
        sections.append(f'<h2 class="rule cat">{html.escape(title)}</h2>')
        for e in es:
            blurb = (f'<p class="blurb">{html.escape(e["blurb"])}</p>'
                     if e["blurb"] else "")
            sections.append(f"""
<section class="example" id="{e['slug']}">
  <h3>{html.escape(e['title'])}</h3>
  {blurb}
  <div class="fig">{e['svg']}</div>
  <details class="code"><summary>Show code</summary>
  <pre><code>{highlight(e['code'])}</code></pre></details>
</section>""")

    gallery_link = (' The <a href="extensions.html">extensions'
                    ' gallery</a> shows every artist in the catalog,'
                    ' rendered at build time.' if has_gallery else "")
    ext_section = f"""
<h2 class="rule cat">From the extensions catalog</h2>
<p class="blurb">Domain-specific plot types stay out of the core and
ship as single-file artists in
<a href="{EXTENSIONS}">plotlet-extensions</a>. A single
<code>import plotlet.extensions</code> registers the whole
catalog.{gallery_link}</p>"""

    body = f"""
<div class="tut-layout">
{sidebar}
<div class="tut-content">
<section class="hero">
  <h1>Cookbook</h1>
  <p class="tag">Composed, multi-panel recipes &mdash; the figures that
  take more than one artist. Every one is generated by the script under
  it. Single plot types live on their
  <a href="reference.html">reference</a> pages instead. Larger multi-file
  projects live in the
  <a href="{COOKBOOK}">plotlet-cookbook</a> repo.</p>
</section>
{''.join(sections)}
{ext_section}
</div>
</div>
"""
    return page("plotlet cookbook", body, "cookbook")


def build_extensions(gallery: list[dict]) -> str:
    sidebar = _sidebar('<a href="extensions.html">Extensions</a>', [
        ("Artists", [(f'<code>{d["name"]}</code>', f'#{d["name"]}')
                     for d in gallery])])

    tiles = []
    for d in gallery:
        if d["method"]:
            call = f'c.{d["method"]}(&hellip;)'
            imp = ""
        else:
            # Composition helpers register nothing — they are imported
            # and called as functions, so their tile keeps an import.
            call = f'{d["func"]}(&hellip;)'
            from_line = (f'from plotlet.extensions.{d["name"]} '
                         f'import {d["func"]}')
            imp = (f'<pre class="imp"><code>{highlight(from_line)}'
                   f'</code></pre>')
        tiles.append(f"""
<div class="tile" id="{d['name']}">
  <h4><code>{call}</code></h4>
  <div class="thumb">{d['svg']}</div>
  <p class="blurb">{html.escape(d['summary'])}</p>
  {imp}<a class="src" href="{EXTENSIONS}/blob/main/src/plotlet/extensions/{d['name']}.py">view source &rarr;</a>
</div>""")

    body = f"""
<div class="tut-layout">
{sidebar}
<div class="tut-content">
<section class="hero">
  <h1>Extensions</h1>
  <p class="tag">Every artist in the
  <a href="{EXTENSIONS}">plotlet-extensions</a> catalog &mdash;
  {len(gallery)} of them &mdash; rendered at build time from each
  module&rsquo;s own demo. One import registers the whole catalog;
  copy a module to make it yours.</p>
  <pre class="tut-code"><code>{highlight("import plotlet.extensions")}</code></pre>
</section>
<div class="tiles tiles-lg">{''.join(tiles)}</div>
</div>
</div>
"""
    return page("plotlet extensions", body, "extensions")


def build_agents(ag: dict) -> str:
    titles = dict(AGENT_SECTIONS)
    sidebar = _sidebar("Agents", [
        (gtitle, [(html.escape(t), f"#{sid}") for sid, t in secs])
        for _, gtitle, secs in AGENT_GROUPS])

    by_id: dict = {}

    def sec(sid: str, prose: str, *blocks: str) -> str:
        joined = "".join(blocks)
        by_id[sid] = (f'<section class="example" id="{sid}">'
                      f'<h3>{html.escape(titles[sid])}</h3>'
                      f'<p class="blurb">{prose}</p>{joined}</section>')
        return by_id[sid]

    def code(snippet: str) -> str:
        return (f'<pre class="tut-code"><code>'
                f'{highlight(snippet.strip())}</code></pre>')

    def out(text: str) -> str:
        return f'<pre class="docstring">{html.escape(text)}</pre>'

    def split(left: str, right: str) -> str:
        return (f'<div class="split"><div>{left}</div>'
                f'<div>{right}</div></div>')

    routing = f"""
<div class="doc-body"><table>
<tr><th>Symptom</th><th>Stage that owns it</th><th>Call</th></tr>
<tr><td>Wrong data or mapping recorded</td><td>journal</td>
<td><code>pt.to_journal(c).to_dict()["entries"]</code></td></tr>
<tr><td>Autoscale, palette or limits surprising</td><td>resolved IR</td>
<td><code>pt.to_ir(c).resolve().to_dict()</code></td></tr>
<tr><td>What the finished plot means</td><td>SVG attributes</td>
<td><code>data-plotlet-*</code> in <code>c.to_svg()</code>
(<a href="{doc_file('AI_ATTRS')}">schema</a>)</td></tr>
<tr><td>Something overlaps or clips</td><td>lint</td>
<td><code>from plotlet.lint import lint; lint(c)</code></td></tr>
<tr><td>Where exactly the chrome landed</td><td>regions</td>
<td><code>c.regions()</code></td></tr>
<tr><td>Grid or composition came out wrong</td><td>layout diagram</td>
<td><code>pt.layout_diagram(c)</code></td></tr>
</table></div>
<p class="blurb">Each fact lives at exactly one stage, so the answer
also points at the fault: if the journal shows the wrong mapping, the
script said the wrong thing; if the journal is right but the resolved
IR surprises you, the surprise is a render decision &mdash; autoscale,
palette, category order. The four sections below inspect this chart:</p>
{code(AGENT_CHART)}
<div class="fig">{ag['chart_svg']}</div>"""

    blocks = [
        sec("journal",
            "Artist calls record; nothing draws until output is asked "
            "for. The journal is that record &mdash; which data, which "
            "mapping, which kwargs. Bulk data is hoisted into a "
            "separate table, so the entries stay readable. The journal "
            "also round-trips through JSON (<code>pt.to_json</code> / "
            "<code>pt.from_json</code>) and rebuilds to a "
            "byte-identical SVG.",
            code('pt.to_journal(c).to_dict()["entries"]'),
            out(ag["journal"])),
        sec("ir",
            "Lowering the journal produces the <code>FigureIR</code>; "
            "resolving it fixes every decision render will make "
            "&mdash; autoscaled limits, palette assignment, category "
            "order &mdash; before any SVG exists. Here are two of "
            "those decisions: the y limits and the colors picked for "
            "the two lines.",
            code('panel = pt.to_ir(c).resolve()'
                 '.to_dict()["root"]["children"][0]\n'
                 '\n'
                 '{k: panel["scales"]["y"][k] for k in ("kind", "lo", "hi")}\n'
                 '[(a["type"], a["opts"]["label"], a["_color"])\n'
                 ' for a in panel["state"]["artists"]]'),
            out(ag["ir"])),
        sec("svg-attrs",
            "Every artist group in the output carries "
            "<code>data-plotlet-*</code> attributes &mdash; plot type, "
            "series label, data ranges, scales. The finished figure "
            "declares what it means, with no source code in hand. The "
            f"full schema is in <a href=\"{doc_file('AI_ATTRS')}\">"
            "AI attributes</a>.",
            "<h4>from c.to_svg()</h4>",
            out(ag["attr_fragment"])),
        sec("regions",
            "<code>c.regions()</code> reports every piece of chrome "
            "&mdash; panel, spines, ticks, title, legend &mdash; as "
            "named bounding boxes. This is how a program answers "
            "&ldquo;where did the title land?&rdquo;",
            code('c.regions()'),
            out(ag["regions"])),
        sec("lint",
            "<code>lint(c)</code> turns &ldquo;does anything overlap "
            "or clip?&rdquo; into a list. Warnings, not errors &mdash; "
            "a flagged figure can still be intentional; the point is "
            "that a program can see the problem at all. Here five long "
            "labels crowd a narrow chart:",
            code(AGENT_LINT_BROKEN),
            split(f'<div class="fig">{ag["lint_broken_svg"]}</div>',
                  out(ag["lint_broken"])),
            '<p class="blurb">The warnings name the colliding regions '
            '&mdash; <code>tick-x</code> against <code>tick-x</code> '
            '&mdash; so the fix is one call away:</p>',
            code(AGENT_LINT_FIX),
            split(f'<div class="fig">{ag["lint_fixed_svg"]}</div>',
                  out(ag["lint_fixed"]))),
        sec("layout",
            "For composed figures, <code>pt.layout_diagram(c)</code> "
            "draws the layout decisions &mdash; panel rectangles, "
            "gaps, alignment &mdash; recovered entirely from the "
            "<code>data-plotlet-*</code> attributes of the finished "
            "SVG. It returns a normal <code>Chart</code>, so it "
            "renders and composes like one.",
            code(AGENT_LAYOUT),
            split(f'<div class="fig">{ag["layout_grid_svg"]}</div>',
                  f'<div class="fig">{ag["layout_diagram_svg"]}</div>')),
        sec("new-artist",
            "The built-in vocabulary ends somewhere, and a machine "
            "author hits that edge often. A new plot type is three "
            "small functions &mdash; <code>record</code> (the call, as "
            "data), <code>xdomain</code>/<code>ydomain</code> (what "
            "autoscaling sees), <code>draw</code> (data to SVG, "
            "through the public <code>draw.*</code> API) &mdash; "
            "bundled into an <code>ArtistSpec</code>. Autoscale, "
            "gridlines, color cycling and the legend come for free. "
            "This is the complete artist from "
            f"<a href=\"{doc_file('EXTENDING')}\">Extending</a>, "
            "running here:",
            code(AGENT_EXTEND),
            f'<div class="fig">{ag["extend_svg"]}</div>',
            '<p class="blurb">The ~45 single-file artists in '
            f'<a href="{EXTENSIONS}">plotlet-extensions</a> follow '
            "exactly this shape &mdash; one import registers the "
            "method on every chart.</p>"),
        sec("bytes",
            "A program can&rsquo;t trust its eyes, but it can diff "
            "bytes. The same script produces the same SVG on every "
            "machine &mdash; text is drawn as paths from a bundled "
            "font, and there is no global state &mdash; so a committed "
            "baseline is an assertion, and a regression is a failing "
            "diff instead of a silent drift. plotlet&rsquo;s own test "
            "suite is 270+ baseline SVGs compared byte for byte in CI. "
            'The <a href="tutorial-reproducibility.html">'
            "reproducibility chapter</a> shows the round trip."),
        sec("roadmap",
            "Honest status, in three tiers. <strong>Shipped:</strong> "
            "everything above &mdash; the pipeline seams, the SVG "
            "schema, byte-identical output, and the extension path "
            "(the artist registry, the <code>draw.*</code> API, "
            f"<a href=\"{doc_file('EXTENDING')}\">Extending</a>). "
            "<strong>Being proven now:</strong> an AI agent adding a "
            "new plot type end to end, unaided, and a full "
            "self-correction session on a realistic figure &mdash; "
            "each will be published here as a case study when it "
            "exists, not before. <strong>Open but unexercised:</strong> "
            "custom coordinate systems &mdash; the "
            f"<a href=\"{doc_file('COORDINATES')}\">coordinate "
            "protocol</a> is open, but Circular is the only coordinate "
            "system shipped so far."),
    ]
    assert len(blocks) == len(AGENT_SECTIONS)

    pieces = []
    for gid, gtitle, secs in AGENT_GROUPS:
        pieces.append(f'<h2 class="rule cat" id="{gid}">'
                      f'{html.escape(gtitle)}</h2>')
        if gid == "seams":
            pieces.append(routing)
        pieces.extend(by_id[sid] for sid, _ in secs)
    sections = "".join(pieces)

    body = f"""
<div class="tut-layout">
{sidebar}
<div class="tut-content">
<section class="hero">
  <h1>For AI agents</h1>
  <p class="tag lead" id="docs-for-ai">Give your assistant
  <a class="main" href="{GITHUB}/blob/main/skills/users.md">
  skills/users.md</a> and start plotting &mdash; one short doc teaches
  an AI the whole library.</p>
  <p class="tag">What makes one doc enough is the architecture under
  it, and this page demonstrates it with real output, executed on
  every build: every pipeline seam answers questions as structured
  data, correctness is verified by diffing bytes instead of trusting
  eyes, and the plot vocabulary extends when it runs out.
  (Contributing to plotlet itself? Give your tool
  <a href="{GITHUB}/blob/main/skills/developers.md">
  skills/developers.md</a>.)</p>
</section>
{sections}
</div>
</div>
"""
    return page("plotlet — for AI agents", body, "agents")


def build_doc_page(doc: dict, docs: list[dict]) -> str:
    by_stem = {d["stem"]: d for d in docs}
    groups = [(group, [(html.escape(by_stem[s]["title"]),
                        None if s == doc["stem"] else doc_file(s))
                       for s in stems])
              for group, stems in DOC_GROUPS]

    body = f"""
<div class="tut-layout">
{_sidebar('Docs', groups)}
<div class="tut-content doc-body">
<section class="hero">
  <h1>{html.escape(doc['title'])}</h1>
</section>
{doc['body']}
</div>
</div>
"""
    return page(f"plotlet docs — {doc['title']}", body, "docs")


# ---------------------------------------------------------------------------
# 6. Search index and main
# ---------------------------------------------------------------------------

def build_search_index(examples: list[dict], entries: list[dict],
                       docs: list[dict], chapters: list[dict],
                       all_sections: list[list[dict]],
                       gallery: list[dict]) -> str:
    idx = []
    for t in entries:
        idx.append({"t": t["name"], "u": ref_file(t["name"]),
                    "g": "reference"})
    for d in gallery:
        idx.append({"t": d["method"] or d["func"],
                    "u": f"extensions.html#{d['name']}",
                    "g": "extensions"})
    for e in examples:
        if e["slug"] in COOKBOOK_SLUGS:
            idx.append({"t": e["title"], "u": f"cookbook.html#{e['slug']}",
                        "g": "cookbook"})
    idx.append({"t": "For AI agents", "u": "agents.html", "g": "agents"})
    for sid, t in AGENT_SECTIONS:
        idx.append({"t": t, "u": f"agents.html#{sid}", "g": "agents"})
    for d in docs:
        idx.append({"t": d["title"], "u": doc_file(d["stem"]), "g": "docs"})
        for text, hid in d["headings"]:
            idx.append({"t": text, "u": f"{doc_file(d['stem'])}#{hid}",
                        "g": f"docs · {d['title']}"})
    for i, (ch, secs) in enumerate(zip(chapters, all_sections)):
        fname = chapter_file(chapters, i)
        idx.append({"t": ch["title"], "u": fname, "g": "tutorial"})
        for s in secs:
            idx.append({"t": s["title"], "u": f"{fname}#{s['id']}",
                        "g": f"tutorial · {ch['title']}"})
    for entry in idx:
        entry["t"] = html.escape(entry["t"])
        entry["g"] = html.escape(entry["g"])
    return json.dumps(idx, separators=(",", ":"), ensure_ascii=True)


def main() -> int:
    global SEARCH_JSON, HAS_EXTENSIONS
    BUILD.mkdir(exist_ok=True)
    print("rendering examples…")
    examples = load_examples()
    print("rendering plot-type tiles…")
    tiles = render_tiles()
    print("rendering concept pages…")
    concepts = render_concepts()
    entries = tiles + concepts
    print("rendering tutorial chapters…")
    chapters = load_chapters()
    all_sections = [render_sections(ch) for ch in chapters]
    print("rendering the extensions gallery…")
    gallery = render_ext_gallery()
    HAS_EXTENSIONS = bool(gallery)
    print("rendering the agents page…")
    agents = render_agents()
    print("rendering docs…")
    docs = render_docs()

    SEARCH_JSON = build_search_index(examples, entries, docs,
                                     chapters, all_sections, gallery)

    (BUILD / "index.html").write_text(build_index(examples))
    written = ["index.html"]
    for i in range(len(chapters)):
        fname = chapter_file(chapters, i)
        (BUILD / fname).write_text(build_tutorial(chapters, i,
                                                  all_sections[i]))
        written.append(fname)
    (BUILD / "cookbook.html").write_text(
        build_cookbook(examples, HAS_EXTENSIONS))
    written.append("cookbook.html")
    if gallery:
        (BUILD / "extensions.html").write_text(build_extensions(gallery))
        written.append("extensions.html")
    (BUILD / "agents.html").write_text(build_agents(agents))
    written.append("agents.html")
    (BUILD / "reference.html").write_text(build_reference_index(entries))
    written.append("reference.html")
    for entry in entries:
        fname = ref_file(entry["name"])
        (BUILD / fname).write_text(
            build_reference_page(entry, entries, examples))
        written.append(fname)
    for d in docs:
        fname = doc_file(d["stem"])
        (BUILD / fname).write_text(build_doc_page(d, docs))
        written.append(fname)
    (BUILD / ".nojekyll").write_text("")
    print(f"wrote {len(written)} pages "
          f"({', '.join(written[:3])}, …, {written[-1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
