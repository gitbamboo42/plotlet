# Philosophy

plotlet is a **scaffold**, not a feature catalog. The library ships a small,
well-scoped core; users build their own custom plot types in their own
projects, with AI assistance making the per-extension cost low.

## What's in the core

- The deferred-render pipeline (Chart, _replay, _render)
- Scales: linear, log, category
- Standard plots: line, scatter, bar, hist, fill_between
- Font handling and text-as-paths rendering
- The locked visual contract (`spec.json`)

## What's *not* in the core

- Domain-specific plot types (genome tracks, Manhattan plots, phylogenetic
  trees, sankey, networks, maps, …)
- Specialty scales beyond the basics

These belong in **your project**, written for your specific data shape and
needs. The [`cookbook/`](../cookbook/) directory has reference implementations
to copy and adapt.

## Why this shape

Code is becoming cheap. The cost of writing a 100-line custom plot type
keeps dropping as AI assistance improves. The cost of *understanding* a
30,000-line library, by contrast, doesn't drop — and that mental model is
what gates productivity.

So plotlet trades feature-completeness for understandability. The core is
small enough to read in an afternoon. The extension points are documented and
deliberate. Adding a custom plot type is a 3-step recipe, not an architecture
project.

## Non-goals

plotlet will never:

- Be interactive (no hover, zoom, pan, animation, ever)
- Compete with matplotlib for the "kitchen-sink" role
- Accept third-party plot types into the core

Tools that try to do everything age into legacy weight. We're not doing that.
