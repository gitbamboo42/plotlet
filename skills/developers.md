# plotlet developer guide

AI-oriented onboarding for working on the plotlet codebase. Vendor-neutral
— symlink to it as `CLAUDE.md`, `.cursorrules`, `AGENTS.md`, or whatever
your tool expects. Human contributors can read it directly.

> **Docs in this repo help us make decisions — they are not textbooks.**
> This applies to every Markdown file: `skills/developers.md`, `README.md`, `docs/*.md`.
> If a fact is derivable from `ls src/plotlet/` or reading a well-named module,
> it doesn't belong in any of them. Policies, non-obvious whys, project
> direction, and reference tables that need to be explicit do.
> Growth is the failure mode — when a doc starts repeating itself, restating
> the code, or accumulating "for reference" content nobody reads, trim it
> (or move the detail to a code comment at the point of use).

## What plotlet is

Deferred-rendering SVG plot library — artist calls record into a
journal, and rendering lowers it journal → `FigureIR` → SVG. The
recording half (the `record/` package) never imports
the render half at module level; the [`render/`](src/plotlet/render/)
package never imports the recording half at all — the `FigureIR` is the
one contract between them ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), enforced by
`tests/test_import_boundary.py`). Product positioning and why-not-X
live in [README.md](README.md) and [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md).

## Load-bearing policies (not derivable from code)

- **Core vs extensions split.** A plot type is core if it passes **either** gate: (1) **generic vocabulary** — shipped as a primitive in ≥2 of matplotlib / seaborn / ggplot2; (2) **plotlet's differentiators** — it belongs to the reproducibility / coordinate / sector / track systems or the niche vocabulary built on them. Everything else defaults to [`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions) (single-file) / [`plotlet-cookbook`](https://github.com/gitbamboo42/plotlet-cookbook) (multi-file). (Internal framing; not for public docs.)
- **Lean flexible on existing core artists.** Add kwargs (alpha, per-side styling) over hand-rolled workarounds. ~1 line of user code vs 20+ lines of workaround → add the kwarg.
- **No interactivity. Forever, not deferred.** Hover, zoom, pan, click, animation kill byte-identical reproducibility — the foundation for baseline-image testing.
- **No global state.** Themes, defaults, anything: per-chart, deterministic. Same script → byte-identical SVG everywhere.
- **No dual y-axes (`twinx`).** Bad design. Not considered.
- **One coordinate system per panel.** Mixing two spatial mappings in one frame is worse than `twinx` — the reader can't parse either axis. Use separate panels. Enforced at record time in `_replay`.
- **API names for clarity.** Equally-clear candidates → prefer the more conventional one for muscle memory. Don't pick a worse name just because someone else uses it.
- **Variable/kwarg naming: reference popular plot libs first.** When naming a new kwarg or parameter, check matplotlib / seaborn / ggplot2 / d3 / plotly for prior art before inventing one. Only diverge with a concrete reason.
- **Visual constants live in [`spec.json`](src/plotlet/spec.json); theme overrides in [`src/plotlet/themes/`](src/plotlet/themes/).** Typing a number into render code → ask whether it belongs in the spec.
- **No premature abstraction.** Three uses before extracting.
- **`draw.*` is the public SVG-emission API for extensions.** Don't hand-roll `<line>` / `<rect>` f-strings in extensions.
- **Before hand-rolling a new artist, check the [`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions) package.** ~45 vetted single-file artists already live there (sankey, alluvial, raincloud, mosaic, calendar_heatmap, upset_plot, parallel_coordinates, …) — its `src/plotlet/extensions/` listing is the index. Usage: `import plotlet.extensions.<name>` registers the artist, then `c.<name>(...)`. `Chart.__getattr__` hints with the import line when an extension method is called without the import. (Core ships no in-tree extensions folder — everything under `src/plotlet/artists/` is a built-in registered on `import plotlet`.)

## Deep dives

- The render pipeline and the FigureIR contract → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Custom plot types → [docs/EXTENDING.md](docs/EXTENDING.md)
- Coordinate systems (Circular, custom projections) → [docs/COORDINATES.md](docs/COORDINATES.md)
- Multi-panel layouts, `share_x` / `share_y` → [docs/SUBPLOTS.md](docs/SUBPLOTS.md)
- Themes → [docs/THEMES.md](docs/THEMES.md)
- AI-readable SVG attrs → [docs/AI_ATTRS.md](docs/AI_ATTRS.md)

## Running tests

`pip install -e ".[test]"` then `pytest tests/` (add `--update` after intentional visual changes to regenerate baselines). For per-set gallery HTML: `python tests/gen_gallery.py <set>` or `python tests/gen_gallery.py all`. Machine-specific Python paths in `CLAUDE.local.md` (gitignored).

## Debugging rendered output

For layout/chrome questions (title, panel, spines, ticks, legend bboxes, overlap, clipping) use `c.regions()` — returns structured `{"kind","bbox","name","meta"}` dicts.

When debugging a bug that spans the pipeline, maintain a `debug.md` at the
repo root as you go: dump the figure's state at each layer (recorded
journal, lowered `FigureIR`, what the render half does with it) and state
your diagnosis — which layer is at fault and why — so the human author can
follow the reasoning, not just the conclusion. `debug.md` is gitignored;
never commit it.

## Style

Plain Python. Top-to-bottom readable. No metaclasses, no clever decorators. Match what's there.
