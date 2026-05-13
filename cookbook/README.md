# plotlet cookbook

Reference implementations of plot types **not** included in the core library.

These exist to be **read, copied, and adapted**, not imported. Each file is a
working example of how to use plotlet's deferred-render pattern to build a
custom plot type for your own project.

The point of the cookbook is the opposite of a feature catalog. **plotlet
deliberately does not grow a long list of built-in plot types.** Instead:

- The core ships ~5 standard plots (line, scatter, bar, hist, fill_between).
- The cookbook shows how to write your own.
- For your custom needs, copy a cookbook example, modify it for your data, and
  use it in your project. AI assistance makes this fast.

## Layout

Each recipe lives in its own folder so it can carry whatever it needs —
script, sample data, baseline output, per-recipe notes — without bleeding
into the others:

```
cookbook/
└── <name>/
    ├── <name>.py     # the recipe
    └── <name>.svg    # generated output (gitignored)
```

## Recipes

Custom plot types (register a new artist):

- [`lollipop/`](lollipop/) — stem-and-circle chart for sparse comparisons,
  plus an optional `legend_swatch` so the legend entry looks like a mini
  lollipop.
- [`numeric_bar/`](numeric_bar/) — bars anchored at *numeric* x positions
  with an explicit `width=` (data units), for cases where the built-in
  categorical `bar` doesn't fit (genome coordinates, time-series with
  numeric x, etc.).

Composition recipes (no new artists, just core plus `|` / `/` / `share_x`):

- [`dendrogram_heatmap/`](dendrogram_heatmap/) — column dendrogram on
  top of a heatmap with `share_x` keeping columns aligned. Shows the
  manual pattern: compute the linkage with scipy, reorder the matrix
  with the leaf permutation, compose with `/`, attach labels at the
  heatmap level.

Domain recipes (combine custom artists with composition):

- [`omics_heatmap/`](omics_heatmap/) — annotated heatmap in the
  ComplexHeatmap shape: top categorical track + left dendrogram +
  central heatmap + unified colorbar / legend panel. Built from
  `pt.grid([[None, top, None], [tree, hm, pt.legend()]], share_x="col",
  share_y="row")` plus a tiny `annotation_strip` custom artist for
  per-group colored cells with discrete legend swatches.

## How to use a recipe

1. Copy the recipe file (or its whole folder) into your own project.
2. Register your artist with `pt.add_artist(pt.ArtistSpec(...))` — see
   [`docs/EXTENDING.md`](../docs/EXTENDING.md) for the full API.
3. Adjust styling, data shape, and details for your specific use case.
4. Don't PR your version back here — your version is for your project.

## Why no upstream contributions?

plotlet's value is the **scaffold**, not the catalog. Adding plot types to
the core would grow it, complicate maintenance, and erode the "small enough to
read end-to-end" property. The cookbook is intentionally a **reference set**,
not a catalog. We accept fixes to existing examples and improvements to the
core; we don't accept new plot types.

If you wrote something useful, **publish it in your project.** With AI search,
the next person who needs it will find your version anyway.
