# plotlet examples

One-file building-block demos — basic plot types built with core artists,
or with small custom artists registered via `pt.add_artist(...)`.

These are the **ingredients**, not the meals. Copy a script, swap in your
data, adjust styling, done. If you need a multi-component, domain-specific
plot (heatmap with side dendrograms and a colorbar, multi-track genome
browser, etc.), see the [`cookbook/`](../cookbook/) instead.

## Status

**This directory is a working pile.** Many recipes are pulled in unvetted
— some have bugs, rough edges, or visual quirks. They'll get fixed
incrementally. If you copy one and it misbehaves, the source is short
enough to fix on the spot.

## Visual gallery

Run `python examples/_gallery.py` to build `examples/index.html` — a
single page with every demo rendered inline, grouped by topic, and
linked to its source. Both `index.html` and the generated `<name>.svg`
files are gitignored; build on demand.

## Layout

Flat single files. No folders.

```
examples/
├── _gallery.py
├── boxplot.py            # the recipe
├── boxplot.svg           # rendered output (gitignored)
├── violin.py
├── violin.svg
└── ...
```

Every recipe declares a `SUMMARY = "..."` constant near the top — the
gallery card description comes straight from it.

## Why one file per recipe

A 30-line `boxplot.py` doesn't earn its own directory. Examples are
deliberately the *minimum* unit of useful demo: imports, a small data
generator, the plot call, `c.show()`. If you find yourself wanting to
add a data file, baseline output, or per-recipe notes alongside, that's
the signal it's not an example anymore — promote it to
[`cookbook/`](../cookbook/).

## Dependencies

Most recipes need only plotlet and the stdlib. A few reach for the
scientific-Python stack where the pure-Python equivalent would be
significantly worse:

- `scipy` for proper t / normal CDFs, linkage methods beyond
  single-linkage, analytic CIs.
- `numpy` for SVD and matrix ops.
- `statsmodels` for the LOESS smoother (degree-2 + robust iterations).

Each recipe declares its own imports — no global "you must install
scipy."

## How to use a recipe

1. Copy the file into your project.
2. If it registers a custom artist, copy the `pt.add_artist(...)` call too.
3. Adjust styling, data shape, and details for your use case.
4. Don't PR your version back — it's yours now.

## Promoting to cookbook

If a recipe outgrows single-file form (sample data file, ancillary
baseline, multiple panels with their own helper logic), move it to
[`cookbook/`](../cookbook/) as `cookbook/<name>/<name>.py` and add a
bullet to the cookbook README.
