# Philosophy

plotlet ships the **standard plotting vocabulary** plus the multi-panel
composition and reproducibility infrastructure that lets you build figures
on top of it. The library is also **designed to be extended**: domain-
specific plot types live in your own project, with AI assistance making the
per-extension cost low.

## What's in the core

- The deferred-render pipeline (Chart, replay, render)
- Scales: linear, log, category, time, symlog, power, sqrt
- Long-form (`data=df, x=, y=, hue=`) and wide-form input across the
  standard vocabulary, so a data frame plus column names is the primary
  entry point
- The standard plotting vocabulary:
  - **xy:** scatter, line, regression
  - **categorical distributions:** boxplot, violin, swarm, strip, pointplot
  - **1-D distributions:** hist, density_1d, ecdf, rug, freqpoly
  - **2-D distributions:** hexbin, kde_2d, contour, ridge, qq
  - **bars & areas:** bar (stack/dodge/fill), fill_between, area (stack), errorbar
  - **images & matrices:** imshow, heatmap, dendrogram
  - **reference lines / shapes / text:** axhline/vline/span, rect, polygon, text, annotate
- Text-as-paths rendering for cross-machine reproducibility
- The locked visual contract (`spec.json`) and theming layer

## What's *not* in the core

- **Domain-specific plot types** — genome tracks, Manhattan plots,
  phylogenetic trees, sankey, alluvial, networks, maps, ROC/PR curves,
  Kaplan–Meier, joint plots, pair plots, raincloud, mosaic, upset,
  calendar heatmap, MA / volcano / forest / funnel, parallel coordinates,
  PCA biplot, … . The standard vocabulary stops where the literature
  becomes domain-specific.
- Specialty scales beyond the basics
- Interactivity, animation, dashboarding

These belong in **your project**. Reference implementations to copy and adapt
live in [`src/plotlet/extensions/`](../src/plotlet/extensions/) (single-file artists)
and [`cookbook/`](../cookbook/) (multi-file projects like annotated heatmaps).
The line is "standard vocabulary in core, domain idioms in extensions" —
borrow elegance where it doesn't fight the core.

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

So plotlet keeps the **core focused on what every figure reaches for** and
pushes **niche feature breadth to user projects**. The codebase stays
readable; the extension points are documented and deliberate; adding a
custom plot type is a 3-step recipe, not an architecture project.

## Non-goals

plotlet will never:

- Be interactive (no hover, zoom, pan, animation, ever)
- Accept domain-specific plot types into the core (they belong in
  [`extensions/`](../src/plotlet/extensions/) or user projects — see the
  list above)

Tools that try to do everything age into legacy weight. We're not doing that.
