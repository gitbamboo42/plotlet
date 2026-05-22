# Philosophy

plotlet is **designed to be extended**. The library ships a well-scoped
core, and users build their own custom plot types in their own projects,
with AI assistance making the per-extension cost low.

## What's in the core

- The deferred-render pipeline (Chart, replay, render)
- Scales: linear, log, category
- A small set of standard plots (line, scatter, bar, hist, fill_between, area, imshow, …)
- Text-as-paths rendering for cross-machine reproducibility
- The locked visual contract (`spec.json`) and theming layer

## What's *not* in the core

- Domain-specific plot types (genome tracks, Manhattan plots, phylogenetic
  trees, sankey, networks, maps, …)
- Specialty scales beyond the basics

These belong in **your project**. Reference implementations to copy and adapt
live in [`src/plotlet/extensions/`](../src/plotlet/extensions/) (single-file artists)
and [`cookbook/`](../cookbook/) (multi-file projects like annotated heatmaps).

## The replay model

A `Chart` is a journal, not a state machine. `c.xlim(1, 10)` doesn't set a
limit — it appends `("xlim", (1, 10), {})` to `Chart._calls`. The renderer
never sees user method calls directly; it sees the list. `_replay` is a
pure fold of `(calls, artist registry) → state dict`, which `_render` then
turns into SVG.

Several features fall out of this rather than being designed separately:

- **Byte-identical re-renders.** `to_svg()` re-walks the same list; calling it twice produces the same bytes.
- **Themes.** `c.theme(...)` appends into the same journal. A user's `c.xlim(...)` after `c.theme(...)` naturally wins by journal order; no precedence rules to maintain.
- **Facets.** `pt.facet(...)` is a chart-shaped recorder; one set of artist calls is replayed against each group's subset.
- **Shared scales.** `share_x="col"` does a pre-pass replay to discover per-panel data domains, then unions them by column before the real render.
- **Extension.** `add_artist(name, record=..., draw=...)` just registers a pair of pure functions; the journal needs no extension points.

The price is that `record()` runs before scales and colors exist, so
artists can't resolve pixel positions or palettes at record time — see
[EXTENDING.md](EXTENDING.md).

## Why this shape

Code is becoming cheap. The cost of writing a 100-line custom plot type
keeps dropping as AI assistance improves. The cost of *understanding* a
30,000-line library, by contrast, doesn't drop — and that mental model is
what gates productivity.

So plotlet keeps the core focused and pushes feature breadth to user
projects. The codebase stays readable; the extension points are documented
and deliberate; adding a custom plot type is a 3-step recipe, not an
architecture project.

## Non-goals

plotlet will never:

- Be interactive (no hover, zoom, pan, animation, ever)
- Aim for full coverage of standard statistical plots (those needs are well-served elsewhere)
- Accept third-party plot types into the core

Tools that try to do everything age into legacy weight. We're not doing that.
