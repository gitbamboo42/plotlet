# CLAUDE.md

Project memory for **plotlet** — a Python library for SVG plots, with multi-panel composition and an extension API for custom plot types.

This file gives Claude (or any collaborator) the context needed to be useful from the first message of a new session. Read it before suggesting changes.

---

## What this project is

plotlet is a Python library that produces matplotlib-flavored SVG plots. The architecture is a deferred-rendering pipeline: artist methods record into a list, then `show()` walks the list and emits one self-contained SVG string. Output is rendered by the consumer's browser/viewer; plotlet has no rendering engine of its own.

Product positioning — "scaffold, not catalog", why-not-matplotlib, custom plots in user projects — lives in [README.md](README.md) and [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md). This file focuses on *how plotlet is built and changed*.

---

## Core design principles

1. **Few lines, full plot.** A typical plot is ~5 lines: figure, plot call, labels, legend. If something common takes more, the API is wrong.
2. **Deferred rendering.** `line()`, `xlabel()`, `legend()` only *record* what to draw. `show()` does the actual rendering. This lets the framework compute correct axis limits, lay out legends, and compose new plot types with everything else for free.
3. **matplotlib-flavored — where matplotlib is good.** Visual conventions mirror pyplot: `"C0"`–`"C9"` color shortcuts, `"--"` `":"` linestyle codes, `"o"` `"s"` `"^"` markers, tab10 cycle, DejaVu Sans, black 0.8 px spines, outward 3.5 px ticks on bottom + left only (matching matplotlib's rcParams `xtick.direction=out`, `xtick.top=False`, `ytick.right=False`), optional dashed grid. Most method names too (`scatter`, `bar`, `hist`, `xlabel`, `legend`). But where matplotlib's name is clearly worse than the modern consensus, plotlet departs deliberately: `c.line()` not `c.plot()` (matches seaborn/plotly/altair/bokeh), `curve="step-after"` not `drawstyle="steps-post"` (matches d3). The look should be instantly recognizable to a matplotlib user; the API doesn't slavishly copy bad names. Top / right ticks are opt-in via `xticks(top=True)` / `yticks(right=True)`.
4. **Static and reproducible.** No interactivity, no animation, no zoom. Same script → byte-identical SVG → visually identical rendering on every machine. This is what unlocks publication-quality output and baseline-image testing.
5. **Custom plot types are first-class — but they live in user projects.** Adding a new artist is ~50–100 lines following the documented recipe. The core stays small specifically to make this easy. In-package reference implementations live in [`src/plotlet/recipes/`](src/plotlet/recipes/) (single-file artists), with bigger multi-file projects in [`cookbook/`](cookbook/) — never in the core.

---

## Architecture

### File layout

```
plotlet/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── src/
│   └── plotlet/
│       ├── __init__.py          # public API
│       ├── _spec.py             # loads spec.json; active_theme() ctx
│       ├── spec.json            # locked default visual spec — package data
│       ├── themes.py            # theme loader + register_theme()
│       ├── themes/              # built-in theme overrides (dark, minimal, void)
│       ├── utils.py             # to_list / to_list_2d / broadcast / histogram
│       ├── scales.py            # _LinearScale, _LogScale, _CategoryScale, nice ticks
│       ├── draw/                # PUBLIC drawing primitives (pixel-coord helpers)
│       │   ├── __init__.py      # segment / rect / circle / path / polyline / polygon
│       │   │                    # / errorbar_v / errorbar_h / marker / text_path / op
│       │   ├── colors.py        # color shortcuts & resolution
│       │   ├── colormaps.py     # 180 vendored matplotlib colormaps (continuous, value→RGB)
│       │   ├── _cm_data.py      # generated LUT data — do not edit by hand
│       │   ├── font.py          # _measure_text, _glyph (DejaVu Sans glyph extraction)
│       │   ├── _png.py          # tiny stdlib-only PNG encoder for imshow's large-image path
│       │   └── fonts/DejaVuSans.ttf  # bundled font (~700 KB)
│       ├── artists.py           # SVG-emitting helpers for the built-in plot types
│       ├── dendrogram.py        # scipy-backed hierarchical-clustering artist
│       ├── registry.py          # ArtistSpec + add_artist — the extension API
│       ├── builtin_artists.py   # registers the built-in artists at import
│       ├── core.py              # render engine — free functions over Chart state
│       ├── chart.py             # Chart class (leaf + parent + composition + recording)
│       ├── layout.py            # subplot rect computation + multi-panel SVG assembly
│       ├── legend.py            # layout-level legend (pt.legend / parent.legend)
│       ├── layout_diagram.py    # pt.layout_diagram — schema-only debug visualizer
│       └── recipes/             # in-package custom-artist examples (smoke-tested)
├── cookbook/                    # multi-file reference projects (heatmaps, genomic tracks)
├── notebooks/
├── tests/
│   ├── baseline_images/         # committed SVG baselines (chart/, subplots/, legend/, …)
│   ├── _runner.py               # shared CLI: --update, --gallery, default = check
│   ├── test_chart.py            # plot defs for the pt.chart() API
│   ├── test_themes.py           # one chart × each theme (classic / dark / minimal / void)
│   └── test_recipes.py          # smoke test: import + demo() + non-empty SVG for every recipe
└── docs/
    ├── PHILOSOPHY.md
    ├── EXTENDING.md
    ├── SUBPLOTS.md
    └── AI_ATTRS.md
```

### Running tests / notebooks

Install editable into a Python 3.10+ environment, then run the test scripts:
```bash
pip install -e .
python tests/test_chart.py            # check vs. committed baselines (default)
python tests/test_chart.py --update   # regenerate after intentional visual changes
python tests/test_chart.py --gallery  # build tests/baseline_images/chart/index.html
jupyter nbconvert --to notebook --execute notebooks/01_basics.ipynb --output /tmp/out.ipynb
```

The test runner plumbing lives in `tests/_runner.py`. Machine-specific interpreter paths and env quirks live in `CLAUDE.local.md` (gitignored).

### The deferred-rendering pattern (the heart of the library)

Every artist method records a tuple `(name, args, kwargs)` into `Chart._calls`. A name is recordable if it's a frame-state method (`title`, `xlim`, …) or a registered artist:

```python
def __getattr__(self, name):
    if name in _FRAME_METHODS or get_artist(name) is not None:
        def recorder(*args, **kwargs):
            self._calls.append((name, list(args), dict(kwargs)))
            return self
        return recorder
```

Then `to_svg()` does five phases:

1. **Replay** — walks `_calls` to build a state dict (`artists`, `title`, `xlim`, …). Each artist call goes through its registered `spec.record(args, kwargs)`.
2. **Domain compute** — `_scan_domain` walks the artists and calls each one's `spec.xdomain(a)` / `spec.ydomain(a)` to gather autoscale values. Each axis first asks `_is_categorical_axis`: if any artist's `xdomain`/`ydomain` returns a string, the axis is categorical and we collect alphabetical unique values via `_collect_categories` instead of a numeric scan. Two remaining wrinkles: hist pre-binning, and `force_zero` for hist/bar so numeric y anchors at zero.
3. **Scale build** — `_LinearScale`, `_LogScale`, `_CategoryScale`. The category scale fires whenever the axis is categorical (auto-detected from string data, or via explicit `xscale="category"` / `yscale="category"`); `order=[...]` picks an explicit layout, alphabetical otherwise. Ticks come from the standard 1/2/5 × 10ⁿ "nice numbers" algorithm.
4. **Render artists** — three layers (`background` → `data` → `foreground`); each artist's `spec.draw(a, ctx)` emits SVG. `RenderContext` carries the scales, dimensions, color, and defaults.
5. **Frame, ticks, labels, legend** — spines, tick lines, text-as-paths labels, then the in-frame legend box (today's `chart.legend()` overlay). Tick rendering honors the matplotlib-style `xticks(positions, labels, *, rotation, fontsize, direction, marks)` / `yticks(...)` overrides — `[]` hides, `marks=False` keeps labels but skips the lines, `direction="out"|"inout"` flips the inward default. Custom artists can supply `spec.legend_swatch` (discrete entries) and/or `spec.legend_gradient` (continuous color mapping → gradient strip in the layout-level legend). Layout-level multi-panel rendering in `layout.py` does a separate two-pass walk (data leaves first to assign `_color`, then legend leaves harvest those colors), with `legend.py` owning the legend renderer.

### AI-readable SVG attributes (0.3.0)

Every plotlet SVG carries `data-plotlet-*` attributes describing plot type, axes, scales, ranges, and series labels. The root `<svg>` gets `data-plotlet-version` / `-schema` / `-kind`, each panel `<g>` gets title / xlabel / ylabel / xscale / yscale / xlim / ylim / panel-bbox / data-area (where `panel-bbox` is the full-rect figure-coords placement and `data-area` is the data region in panel-local coords), each artist `<g class="plotlet-artist">` gets type / index / label / color plus type-specific extras (n, x-min/max, marker, …). Categorical axes emit a child `<metadata data-plotlet-payload="xcategories">` JSON blob with the labels. The schema (`data-plotlet-schema="2"`) is semver-stable — additive changes only. Custom artists hook in by declaring an optional `data_attrs=` callback on their `ArtistSpec` for type-specific attrs; common attrs (type, index, label, color) come automatically. Full schema reference: [docs/AI_ATTRS.md](docs/AI_ATTRS.md). The schema's value-added is concrete: [`pt.layout_diagram`](src/plotlet/layout_diagram.py) is a debug visualizer that imports nothing private — it only reads `data-plotlet-*` — so it doubles as a worked example of what a schema consumer looks like.

### Adding a new plot type

The three-step recipe (`record`, `xdomain`/`ydomain`, `draw`, all bundled in an `ArtistSpec` and handed to `add_artist(...)`) is plotlet's central hackability claim — no edits to `core.py`, no monkey-patching. **For most custom plots, the right home is your own project (or [`src/plotlet/recipes/`](src/plotlet/recipes/)) — not the core.** The `draw` callback composes pixel-coordinate primitives from [`plotlet.draw`](src/plotlet/draw/__init__.py) (`segment`, `rect`, `circle`, `path`, `polyline`, `polygon`, `errorbar_v`/`errorbar_h`, `marker`, `text_path`) rather than hand-rolling SVG f-strings — keeps recipes short and lets format changes propagate for free. Full guide: [docs/EXTENDING.md](docs/EXTENDING.md); worked recipe: [`src/plotlet/recipes/lollipop.py`](src/plotlet/recipes/lollipop.py).

### Text rendering — text-as-paths via fontTools

Instead of emitting `<text>` elements that depend on the consumer's installed fonts, plotlet extracts glyph outlines from the bundled DejaVu Sans (`fonts/DejaVuSans.ttf`) and emits `<path d="…">` elements. This unlocks:

- **Cross-machine reproducibility.** Same SVG renders identically on Linux, macOS, Windows, headless CI.
- **Exact text measurement.** `_measure_text(s, size)` returns the precise pixel width by summing glyph advances. The legend box auto-sizes to fit; no `len(text) * 6.2` magic numbers.
- **Self-contained output.** SVG files don't need fonts on the recipient's machine.

Tradeoff: text in the output isn't selectable / searchable. matplotlib makes the same trade for the same reason.

### Visual spec + themes

All visual constants — colors, font sizes, spine widths, default alphas, legend dimensions, background — live in [`src/plotlet/spec.json`](src/plotlet/spec.json), the locked default look. `_spec.py` loads it at import and exposes live dicts (`_D`, `_FRAME`, `_GRIDSPEC`, `_FONTSPEC`, `_LEGSPEC`, `_FIGSPEC`, …) that other modules import once and read repeatedly. Built-in themes (`dark`, `minimal`, `void`) live as partial JSON files in [`src/plotlet/themes/`](src/plotlet/themes/) and deep-merge over `spec.json` at render time.

A theme is a partial JSON override under `themes/` (or registered at runtime via `pt.register_theme`). `c.theme("dark")` records the theme name into `_calls`; at render time, [`active_theme(name)`](src/plotlet/_spec.py) deep-merges the theme over classic and *mutates the contents* of the live spec dicts for the duration of one render, restoring on exit. The mutate-in-place trick is what lets every module keep its `from ._spec import _D` import without a 100-site dependency-injection refactor — the dict identity is stable, only its contents change.

Multi-panel layouts apply each leaf's theme independently — the swap is restored between panels. The outer SVG background still comes from whatever theme is active at the root (defaults to `classic`); set a theme on every leaf if you want a fully dark figure. See [docs/THEMES.md](docs/THEMES.md).

Changing a value in `spec.json` is the *only* way to alter the locked default look. Don't reintroduce hard-coded literals in render code — if you find yourself typing a number, it belongs in the spec.

### State on a leaf Chart

Each leaf `Chart` accumulates:

- `_calls` — list of recorded artist + styling calls
- `_data_width`, `_data_height`, `_canvas_width`, `_canvas_height`, `_margin` — figure dimensions. The user-facing primitive is the *data region* (`data_width=` / `data_height=`); canvas is derived from data + margin (grown to fit content at render time). To fit a composition into a specific SVG canvas, users chain `.fit(canvas_width=…, canvas_height=…)` after composing — it rescales each leaf's data dims layout-aware (fonts, spines, margins, and gaps stay at their absolute pixel sizes). Canvas-first sizing was removed in 0.4.0. Non-data leaves (legend, diagram) bypass the body-first path: they get explicit canvas dims via `Chart._new_sized_leaf(...)` because they have no data region.

Parent Charts (composed via `|`, `/`, `pt.grid`) carry no leaf state — they only hold `_children` and `_layout_kind`. Their dimensions emerge at render time from summing their children plus gaps.

The replay function (`core._replay(calls)`) reconstructs `title`, `xlabel`, `ylabel`, `xlim`, `ylim`, `xscale`, `yscale`, `grid`, `legend`, `artists` from `_calls` each render. Stateless rendering = same output every time. For body-first leaves, `core._effective_margin(leaf, st)` combines the floor-applied user margin with `_required_margin(st, dw, dh)` (measured from actual title / axis labels / tick labels) so the canvas grows to fit content rather than letting it overflow.

---

## Conventions for collaboration

**Dependencies.** plotlet depends on Python 3.10+ and `fonttools` (parses the bundled DejaVu Sans). numpy / pandas / polars inputs are accepted because `utils.to_list` calls `.tolist()` defensively, but the implementation doesn't currently need them. Add deps when they earn their keep — don't avoid them on principle.

When suggesting changes or adding features:

- **Decide core vs recipes first.** Recipes (in [`src/plotlet/recipes/`](src/plotlet/recipes/), or the user's own project) are the default for new plot types; core is only for shared infrastructure (this is how `imshow` got in — it carries the colormap registry and the PNG encoder, both reusable) or genuine essentials.
- **Refuse new core plot types by default.** "Let's add a Sankey to the core" is almost always wrong; the right answer is a recipe in `src/plotlet/recipes/<name>.py` (or [`cookbook/`](cookbook/) for multi-file reference projects), or the user's own project.
- **`draw.*` is the public extension API.** When a recipe's `draw` callback needs SVG, reach for `plotlet.draw` (`segment`, `rect`, `circle`, `path`, `polyline`, `polygon`, `errorbar_v`/`errorbar_h`, `marker`, `text_path`) — don't hand-roll `<line>`/`<rect>` f-strings. If a new compound pattern appears in three+ recipes, add a helper to `draw/__init__.py` rather than copy-pasting.
- **Lean flexible on existing core artists.** Once an artist is in core, prefer adding kwargs (alpha, color, per-side spine styling, etc.) over telling users to work around their absence. Cost test: how many lines of user code does the result take, with vs. without lib support? If it's ~1 line vs. 20+ lines of fragile workaround (post-processing SVG, monkey-patching globals, drawing parallel artists with the built-in turned off), add the kwarg. Exception: if the customization would noticeably bloat a core artist *and* the user could equivalently implement it as a small cookbook artist, leave it for cookbook. The "refuse new core plot types" rule above keeps the *vocabulary* small; this rule keeps the existing vocabulary friendly.
- **Match existing code style.** Plain Python, top-to-bottom readable, no clever metaclasses or classes-everywhere.
- **Preserve matplotlib API parity** for standard plots. If matplotlib calls it `axhline`, don't call it `horizontalLine`.
- **No premature abstraction.** Three is the threshold — leave duplicated code alone until there's a third use site.
- **Visual constants live in `spec.json`.** If you find yourself typing a number into render code, ask whether it should be there (themable) or hardcoded by design.
- **Test with baselines.** Core changes get added to `tests/test_chart.py` with a committed SVG. Recipes are smoke-tested only (`tests/test_recipes.py` checks each `demo()` imports + serializes); they evolve faster than core, so 64 baseline files would bloat the repo without adding much coverage.
- **Mention matplotlib quirks that aren't replicated** and why, when relevant.
- **Layout / multi-panel code lives in its own module** (`layout.py` for rect computation + multi-panel assembly; `legend.py` for the layout-level legend), not in `core.py`. Keep responsibilities split: pixel-coord primitives in `draw/`; per-artist SVG emission in `artists.py` / `dendrogram.py`; framework state + frame/ticks in `core.py` / `registry.py` / `scales.py`; composition + multi-panel in `layout.py` / `legend.py`.

The actual mechanics of adding an artist (`ArtistSpec`, `add_artist`, `RenderContext`) are in [docs/EXTENDING.md](docs/EXTENDING.md).

---

## Non-goals

User-facing non-goals (no interactivity, no 3D, no production dashboard, not a matplotlib competitor for standard plots) are listed in [README.md](README.md). Contributor-only reminders:

- **Interactivity is out forever, not deferred.** Hover, zoom, pan, click, animation are *not* "maybe later" — they kill the byte-identical reproducibility that makes baseline-image testing possible. Don't soften this in code review.
- **Not aiming for 100% matplotlib coverage.** Just the parts the author actually uses, plus whatever shared infrastructure is forced by core artists. Reject "we should add this for parity" arguments.

Strategic positioning (long-term direction, competitor landscape, the razor for gray-area requests) lives in [CLAUDE.local.md](CLAUDE.local.md) — collaborator-internal, gitignored.
