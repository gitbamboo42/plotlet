# CLAUDE.md

> **Docs in this repo help us make decisions — they are not textbooks.**
> This applies to every Markdown file: `CLAUDE.md`, `README.md`, `docs/*.md`.
> If a fact is derivable from `ls src/plotlet/` or reading a well-named module,
> it doesn't belong in any of them. Policies, non-obvious whys, project
> direction, and reference tables that need to be explicit do.
> Growth is the failure mode — when a doc starts repeating itself, restating
> the code, or accumulating "for reference" content nobody reads, trim it
> (or move the detail to a code comment at the point of use).

## What plotlet is

Deferred-rendering SVG plot library — artist calls record into a list,
`show()` walks it and emits one self-contained SVG. Product positioning
and why-not-X live in [README.md](README.md) and [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md).

## Load-bearing policies (not derivable from code)

- **Core vs extensions split.** Core covers the **standard plotting vocabulary** (the set listed in [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md)). **Domain-specific plot types** default to [`src/plotlet/extensions/`](src/plotlet/extensions/) (single-file) or [`cookbook/`](cookbook/) (multi-file projects). Decision rule for borderline cases: a plot type qualifies as "standard vocabulary" if **two or more** of matplotlib / seaborn / ggplot2 ship it as a primitive. Domain idioms (Sankey, Manhattan, ROC, KM, mosaic, calendar heatmap, etc.) don't qualify even if one popular lib has them. (Internal-only framing; not for public docs.)
- **Lean flexible on existing core artists.** Add kwargs (alpha, per-side styling) over hand-rolled workarounds. ~1 line of user code vs 20+ lines of workaround → add the kwarg.
- **No interactivity. Forever, not deferred.** Hover, zoom, pan, click, animation kill byte-identical reproducibility — the foundation for baseline-image testing.
- **No global state.** Themes, defaults, anything: per-chart, deterministic. Same script → byte-identical SVG everywhere.
- **No dual y-axes (`twinx`).** Bad design. Not considered.
- **API names for clarity.** Equally-clear candidates → prefer the more conventional one for muscle memory. Don't pick a worse name just because someone else uses it.
- **Variable/kwarg naming: reference popular plot libs first.** When naming a new kwarg or parameter, check matplotlib / seaborn / ggplot2 / d3 / plotly for prior art before inventing one. Only diverge with a concrete reason.
- **Visual constants live in [`spec.json`](src/plotlet/spec.json); theme overrides in [`src/plotlet/themes/`](src/plotlet/themes/).** Typing a number into render code → ask whether it belongs in the spec.
- **No premature abstraction.** Three uses before extracting.
- **`draw.*` is the public SVG-emission API for extensions.** Don't hand-roll `<line>` / `<rect>` f-strings in extensions.

## Deep dives

- Custom plot types → [docs/EXTENDING.md](docs/EXTENDING.md)
- Multi-panel layouts, `share_x` / `share_y` → [docs/SUBPLOTS.md](docs/SUBPLOTS.md)
- Themes → [docs/THEMES.md](docs/THEMES.md)
- AI-readable SVG attrs → [docs/AI_ATTRS.md](docs/AI_ATTRS.md)

## Running tests

`pip install -e .` then `python tests/test_chart.py` (add `--update` after intentional visual changes). Machine-specific Python paths in `CLAUDE.local.md` (gitignored).

## Style

Plain Python. Top-to-bottom readable. No metaclasses, no clever decorators. Match what's there.
