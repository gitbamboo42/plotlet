# plotlet cookbook

Worked examples of **multi-component, domain-specific plots** — annotated
heatmap layouts, genome browser tracks, and similar substantial recipes
that compose custom artists with plotlet's layout algebra.

These are the **full meals**, not the ingredients. For single-file demos
of standard plot types (boxplot, violin, scatter density, etc.), see
[`../examples/`](../examples/).

The cookbook is intentionally small. **plotlet deliberately does not grow
a long list of built-in plot types**, and the cookbook follows the same
discipline:

- Each recipe earns its directory by needing ancillary material (sample
  data, baselines, helper logic, per-recipe notes).
- Recipes here demonstrate something a competent user wouldn't reach for
  unaided — non-obvious composition, custom artists wired into layouts,
  domain conventions like ComplexHeatmap.
- Anything that fits in one file lives in `examples/` instead.

## Visual gallery

Run `python cookbook/_gallery.py` to build `cookbook/index.html` — a
single page with every recipe rendered inline, linked to its source.
Both `index.html` and the generated `<recipe>.svg` files are gitignored;
build on demand.

## Layout

```
cookbook/
├── _gallery.py
└── <name>/
    ├── <name>.py           # the recipe (SUMMARY = "..." near the top)
    ├── <name>.svg          # rendered output (gitignored)
    └── sample_data.csv     # optional ancillary material
```

Every recipe declares a `SUMMARY = "..."` constant near the top — the
gallery card description comes straight from it.

## Projects

- [`dendrogram_heatmap/`](dendrogram_heatmap/) — column dendrogram on
  top of a heatmap with `share_x` keeping columns aligned. Shows the
  manual pattern: compute the linkage with scipy, reorder the matrix
  with the leaf permutation, compose with `/`, attach labels at the
  heatmap level.
- [`omics_heatmap/`](omics_heatmap/) — annotated heatmap in the
  ComplexHeatmap shape: top categorical track + left dendrogram +
  central heatmap + unified colorbar / legend panel. Built from
  `pt.grid([[None, top, None], [tree, hm, pt.legend()]], share_x="col",
  share_y="row")` plus a tiny `annotation_strip` custom artist for
  per-group colored cells with discrete legend swatches.
- [`genomic_tracks/`](genomic_tracks/) — genome-wide tracks across
  chromosome-proportional subplots. *(work in progress)*

## How to use a recipe

1. Copy the recipe folder into your project.
2. Register any custom artists with `pt.add_artist(pt.ArtistSpec(...))`
   — see [`docs/EXTENDING.md`](../docs/EXTENDING.md) for the full API.
3. Adjust styling, data shape, and details for your use case.
4. Don't PR your version back — it's yours now.

## Why no upstream contributions?

plotlet's value is the **scaffold**, not the catalog. Adding plot types
to the core would grow it, complicate maintenance, and erode the "small
enough to read end-to-end" property. The cookbook is intentionally a
**reference set of substantial worked examples**, not a catalog. We
accept fixes to existing recipes and improvements to the core; we
don't accept new plot types here. Single-file demos belong in
[`../examples/`](../examples/), not the cookbook.

If you wrote something useful, **publish it in your project.** With AI
search, the next person who needs it will find your version anyway.
