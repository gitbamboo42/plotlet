# Philosophy

plotlet ships the **standard plotting vocabulary** plus the infrastructure
to build figures on top of it: multi-panel composition, swappable
coordinate systems (Cartesian and circular), and reproducible output. The
library is also **designed to be extended**: domain-specific plot types —
and even new coordinate systems — can live in extensions, with AI assistance
making the per-extension cost low.

## What's in the core

- The deferred-render pipeline — journal → figure IR → resolved IR →
  SVG, every stage inspectable (`to_ir`, `.resolve()`, `.to_dict()`,
  `c.regions()`)
- Scales: linear, log, category, time, symlog, power, sqrt
- Coordinate systems: Cartesian by default; swap the per-panel projection
  with `c.coordinate(pt.CircularCoordinate(...))` for circular / ring
  layouts. The projection protocol is open — any object matching it adds a
  new one ([COORDINATES.md](COORDINATES.md)).
- Axis partitioning: `c.sectors(...)` — named regions along an axis,
  either continuous (length-weighted) or categorical (grouped members).
  Peer of scales: any artist works inside a sectored axis without
  modification, since the partition lives on the panel and reshapes
  `x_scale`/`y_scale`. Unifies multi-track layouts and heatmap row /
  column clusters under one concept.
- Long-form input (a data table plus an explicit `aes(x=, y=,
  color=/fill=)` column mapping; bare kwargs stay literal) for
  table-shaped marks across the standard vocabulary — a data frame
  plus `aes(...)` is the primary entry point. Matrix and shape marks
  (imshow, contour, dendrogram, refline/refspan, rect/polygon) take
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

These live outside the core. The separate [`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions)
package holds single-file artists you install and import (`pip install plotlet-extensions`,
then `import plotlet.extensions.<name>`); the [`plotlet-cookbook`](https://github.com/gitbamboo42/plotlet-cookbook)
repo holds multi-file projects (like annotated heatmaps) to copy and adapt.

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

Four claims:

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

4. **Verification over trust.** The pipeline is a ladder of observable
   checkpoints — journal → figure IR → resolved IR → debug-attributed
   SVG → baseline images — each answering one question (what was said /
   what figure is that / what was decided / where did it land / what
   are the bytes). A wrong change fails loudly at the stage that owns
   it, so correctness is checked by diffing artifacts, not by trusting
   whoever (or whatever) wrote the code — the property that makes
   heavy AI-assisted development safe. The seams are enforced by
   tests, not convention ([ARCHITECTURE.md](ARCHITECTURE.md)); each
   fact lives at exactly one stage and flows forward.

The cost: if your plot type isn't shipped, you write it.

## Non-goals

plotlet will never:

- Be interactive (no hover, zoom, pan, animation, ever)
- Accept domain-specific plot types into the core (they belong in
  [`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions),
  [`plotlet-cookbook`](https://github.com/gitbamboo42/plotlet-cookbook), or
  user projects — see the list above)
