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
live in [`src/plotlet/recipes/`](../src/plotlet/recipes/) (single-file artists)
and [`cookbook/`](../cookbook/) (multi-file projects like annotated heatmaps).

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
