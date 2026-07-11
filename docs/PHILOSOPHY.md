# Philosophy

plotlet ships the **standard plotting vocabulary** plus the multi-panel
composition and reproducibility infrastructure that lets you build figures
on top of it. The library is also **designed to be extended**: domain-
specific plot types live in your own project, with AI assistance making the
per-extension cost low.

## What's in the core

- The deferred-render pipeline (Chart, replay, render)
- Scales: linear, log, category, time, symlog, power, sqrt
- Axis partitioning: `c.sectors(...)` — named regions along an axis,
  either continuous (length-weighted) or categorical (grouped members).
  Peer of scales: any artist works inside a sectored axis without
  modification, since the partition lives on the panel and reshapes
  `x_scale`/`y_scale`. Unifies multi-track layouts and heatmap row /
  column clusters under one concept.
- Long-form input (`data=df, x=, y=, color=`/`fill=`) for table-shaped
  marks across the standard vocabulary — a data frame plus column
  names is the primary entry point. Matrix and shape marks (heatmap,
  imshow, contour, dendrogram, refline/refspan, rect/polygon) take
  their natural positional input.
- The standard plotting vocabulary:
  - **xy:** scatter, line, regression
  - **categorical distributions:** boxplot, violin, swarm, strip, pointplot
  - **1-D distributions:** hist, density_1d, ecdf, rug, freqpoly, qq
  - **2-D distributions:** hexbin, hist2d, kde_2d, contour, ridge
  - **bars & areas:** bar (stack/dodge/fill), fill_between, area (stack), errorbar
  - **images & matrices:** imshow, heatmap, dendrogram
  - **reference lines / shapes / text:** axhline/vline/span, axline, hlines/vlines, rect, polygon, text, annotate
- Text-as-paths rendering for cross-machine reproducibility
- The locked visual contract (`spec.json`) and theming layer

## What's *not* in the core

- **Domain-specific plot types** — sankey, alluvial, networks, maps,
  ROC/PR curves, joint plots, pair plots, raincloud, mosaic, upset,
  calendar heatmap, funnel, parallel coordinates, … . The standard
  vocabulary stops where the literature becomes domain-specific.
- Specialty scales beyond the basics
- Interactivity, animation, dashboarding

These belong in **your project**. Reference implementations to copy and adapt
live in the separate [`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions)
package (single-file artists) and the [`plotlet-cookbook`](https://github.com/gitbamboo42/plotlet-cookbook)
repo (multi-file projects like annotated heatmaps).
The line is "standard vocabulary in core, domain idioms in extensions" —
borrow elegance where it doesn't fight the core.

## The replay model

A `Chart` is a journal, not a state machine. `c.xlim(1, 10)` doesn't set a
limit — it appends `("xlim", (1, 10), {})` to `Chart._calls`. The renderer
never sees user method calls directly; it sees the list. `_replay` is a
pure fold of `(calls, artist registry) → state dict`, which the layout
engine then turns into SVG.

Several features fall out of this rather than being designed separately:

- **Byte-identical re-renders.** `to_svg()` re-walks the same list; calling it twice produces the same bytes.
- **Themes.** `c.theme(...)` appends into the same journal. A user's `c.xlim(...)` after `c.theme(...)` naturally wins by journal order; no precedence rules to maintain.
- **Facets.** `pt.facet(...)` is a chart-shaped recorder; one set of artist calls is replayed against each group's subset.
- **Shared scales.** `share_x="col"` does a pre-pass replay to discover per-panel data domains, then unions them by column before the real render.
- **Extension.** `add_artist(ArtistSpec(name, record=..., draw=...))` just registers a pair of pure functions; the journal needs no extension points.

The price is that `record()` runs before scales and colors exist, so
artists can't resolve pixel positions or palettes at record time — see
[EXTENDING.md](EXTENDING.md).

## Why this shape

Three claims:

1. **Reproducibility.** Text rendered as paths, deterministic replay — same
   script, byte-identical output, any machine. Baseline-image tests work;
   "looks fine on my laptop" stops being a bug class.

2. **Composition is the hard part.** Annotated heatmaps and faceted
   layouts aren't single plots; they're coordinated panels with shared
   scales, attached tracks, and shared axis partitions. `pt.grid`,
   `share_x`/`share_y`, `c.sectors(...)` (layout-level fan-out),
   `attach_above`/`attach_left`, `|`/`/` are core, not glue.

3. **Focused core, clear extension surface.** Standard vocabulary lives in
   core; domain idioms live in the separate
   [`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions)
   package and [`plotlet-cookbook`](https://github.com/gitbamboo42/plotlet-cookbook) as copy-and-adapt examples. The
   boundary is explicit ("What's *not* in the core" above), the
   extension API is `ArtistSpec` — two required callbacks (`record`,
   `draw`) plus opt-in hooks — and the replay model means custom
   artists compose like built-in ones.

The cost: if your plot type isn't shipped, you write it.

## Non-goals

plotlet will never:

- Be interactive (no hover, zoom, pan, animation, ever)
- Accept domain-specific plot types into the core (they belong in
  [`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions)
  or user projects — see the
  list above)

Tools that try to do everything age into legacy weight. We're not doing that.
