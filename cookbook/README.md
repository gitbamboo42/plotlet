# plotlet cookbook

Worked examples of **multi-component, domain-specific plots** — annotated
heatmap layouts, genome browser tracks, and similar substantial recipes
that compose custom artists with plotlet's layout algebra.

The cookbook is intentionally small. Each recipe earns its directory by
needing ancillary material (sample data, baselines, helper logic) and
demonstrating non-obvious composition, custom artists, or coordinate
patterns (e.g. [`circle/`](circle/) shows non-affine coordinates via
post-render SVG warping). Each recipe is self-contained — browse the
subdirectories directly; there is no central index.

## How to use a recipe

1. Copy the recipe folder into your project.
2. Register any custom artists with `pt.add_artist(pt.ArtistSpec(...))`
   — see [`docs/EXTENDING.md`](../docs/EXTENDING.md) for the full API.
3. Adjust styling, data shape, and details for your use case.
