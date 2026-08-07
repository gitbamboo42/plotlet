# AI-readable SVG attributes

Every plotlet SVG carries `data-plotlet-*` attributes describing plot
type, axes, scales, ranges, and series labels — so an AI tool can read
plot semantics directly without OCR-ing text-as-paths or inverting pixel
positions. Schema is semver-stable, declared via `data-plotlet-schema="2"`
on the root.

---

## Schema reference

### Root `<svg>`

| Attribute              | Example                | Notes                                      |
|------------------------|------------------------|--------------------------------------------|
| `data-plotlet-version` | `"0.6.2"`              | the plotlet release that emitted this SVG  |
| `data-plotlet-schema`  | `"2"`                  | bumped only when names change incompatibly |
| `data-plotlet-kind`    | `"layout"`             | always `"layout"` — a lone chart is a 1x1 layout |

The root's first child is the figure-background `<rect>`; it carries no
`data-plotlet-*` attributes — skip it when walking for tagged elements.

### Panel `<g>` (one per chart leaf)

| Attribute                | Example                | Notes |
|--------------------------|------------------------|-------|
| `data-plotlet-kind`      | `"panel"`              | discriminator for nested panels in layouts |
| `data-plotlet-title`     | `"Daily revenue"`      | omitted if empty |
| `data-plotlet-xlabel` / `-ylabel` | `"date"` / `"USD"` | omitted if empty |
| `data-plotlet-xscale` / `-yscale` | `"linear"` / `"log"` / `"category"` | |
| `data-plotlet-xlim` / `-ylim` | `"0,42"` / `"-1.5,1.5"` | resolved limits post-autoscale; omitted on categorical axes |
| `data-plotlet-yflip`     | `"true"`               | present only when y is rendered inverted (e.g. `image_cmap(origin="upper")`, image_rgba's default) |
| `data-plotlet-panel-bbox`| `"0,0,560,348"`        | `"x,y,w,h"` of the full panel rect in figure-SVG coords |
| `data-plotlet-data-area` | `"60,24,500,300"`      | `"x,y,w,h"` of the data region in *panel-local* coords; add the bbox's `(x,y)` for figure-SVG coords |

For categorical axes, the label list is emitted as a child `<metadata>` —
see "Categorical lists" below.

### Diagram `<g>` (debug-visualizer leaves)

`pt.layout_diagram(c)` produces a leaf with `data-plotlet-kind="diagram"`
and no panel/axis attrs (it's not a chart). Consumers can identify and
skip these when scanning for data panels.

### Legend `<g>` (standalone legend leaves)

`pt.legend(...)` produces a leaf with `data-plotlet-kind="legend"` and:

| Attribute                    | Example         | Notes |
|------------------------------|-----------------|-------|
| `data-plotlet-legend-bbox`   | `"640,32,80,256"` | `"x,y,w,h"` of the legend's allocated rect in figure-SVG coords |

Inline legends (rendered inside a panel via `c.legend(True,
position=...)`) live inside the panel `<g>` and don't carry
these attrs — their geometry is part of the panel's chrome rather than
a sibling leaf. Filter by `data-plotlet-kind` to distinguish.

### Inset `<g>` (inset axes)

`c.inset(...)` renders inside the parent panel's `<g>` as a nested
`<g data-plotlet-kind="inset">` wrapping a complete inner SVG — the
inset's own panel/artist attrs live inside it, so a consumer walking
for panels should recurse into (or deliberately skip) inset groups.

### Artist `<g class="plotlet-artist">` (one per recorded artist)

Common attrs (always emitted):

| Attribute              | Example         |
|------------------------|-----------------|
| `data-plotlet-type`    | `"line"`, `"bar"`, `"hist"`, `"image_cmap"`, … |
| `data-plotlet-index`   | `"0"`, `"1"`, … |
| `data-plotlet-label`   | `"actual"` (only if user passed `label=`) |
| `data-plotlet-color`   | `"#1f77b4"` (resolved hex) |

Type-specific attrs:

| Artist          | Extras                                                                       |
|-----------------|------------------------------------------------------------------------------|
| `line`          | `n`, `x-min`, `x-max`, `y-min`, `y-max`, `linestyle`, `marker`, `curve`      |
| `scatter`       | `n`, `x-min`, `x-max`, `y-min`, `y-max`, `marker`                            |
| `bar`           | `n`, `y-min`, `y-max`                                                        |
| `hist`          | `n` (raw obs), `bins`, `x-min`, `x-max`, `count-max`                         |
| `fill_between`  | `n`, `x-min`, `x-max`, `y-min`, `y-max`, `curve`                             |
| `area`          | `n`, `x-min`, `x-max`, `y-min`, `y-max`, `base`, `curve`                     |
| `rect` / `polygon` | `n`, `x-min`, `x-max`, `y-min`, `y-max`                                   |
| `errorbar`      | `n`, `x-min`, `x-max`, `y-min`, `y-max`, `marker`                            |
| `axhline` / `axvline` | `y` / `x`                                                              |
| `axhspan` / `axvspan` | `ymin`, `ymax` / `xmin`, `xmax`                                        |
| `axline`        | `x1`, `y1` plus `slope` (point + slope form) or `x2`, `y2` (two-point form)  |
| `hlines` / `vlines` | `n`, `x-min`, `x-max`, `y-min`, `y-max`                                  |
| `text`          | `n`, `x-min`, `x-max`, `y-min`, `y-max`                                      |
| `annotate`      | `x`, `y` (annotated point), `tx`, `ty` (text position), `text`               |
| `image_cmap`    | `rows`, `cols`, `vmin`, `vmax`, `cmap`, `extent`, `data-encoding` (`"rects"` below ~10000 cells, `"png-embedded"` above); `downsampled="true"` when the embedded PNG was mean-pooled below one pixel per cell; when non-default: `origin`, `norm`, `center`, `annot` (`"values"`/`"custom"`) |
| `image_rgba`    | `rows`, `cols`, `channels` (3 or 4; fully-opaque RGBA canonicalizes to 3), `extent`, `data-encoding`, `downsampled` as above; `origin` only when non-default (`"lower"`) |
| `heatmap`       | `rows`, `cols`, `data-encoding` plus either `vmin`, `vmax`, `cmap` (value mode) or `mode="categorical"`, `categories` (palette mode); `downsampled="true"` when the embedded PNG was pooled below one pixel per cell; numeric-`x` charts add `x-axis="continuous"`, `x-extent`; when non-default: `norm`, `center`, `annot` |
| `hist2d`        | `n` (raw obs), `bins-x`, `bins-y`, `count-max`                               |
| `dendrogram`    | `orientation`, `n-leaves`, `max-height`, `leaves` (concatenated scipy leaf order) |

### Categorical lists

Category labels live in a `<metadata>` child of the panel `<g>` so the
attribute namespace stays simple and labels can contain arbitrary
characters:

```xml
<g data-plotlet-kind="panel" data-plotlet-xscale="category" ...>
  <metadata data-plotlet-payload="xcategories"><![CDATA[["Q1","Q2","Q3","Q4"]]]></metadata>
  ...
</g>
```

CDATA lets values contain `<` `>` `&` unescaped; `json.dumps` won't
produce `]]>`, so the wrap is safe.

---

## Custom artists

Set `ArtistSpec.data_attrs` (optional) to add type-specific attrs. Common
attrs (type, index, label, color) come automatically.

```python
add_artist(ArtistSpec(
    name="lollipop", record=..., draw=...,
    data_attrs=lambda a: {
        "n": len(a["xs"]),
        "x-min": min(a["xs"]),
        "x-max": max(a["xs"]),
    },
))
```

---

## Worked example

```python
import plotlet as pt
from plotlet import aes

df = {"day": [1, 2, 3, 4], "usd": [10.5, 12.3, 11.0, 14.7]}
c = pt.chart()
c.title("Daily revenue").xlabel("day").ylabel("USD")
c.add_line(df, aes(x="day", y="usd"), label="actual")
print(pt.describe(c))
```

```
SVG 700×405 plotlet=0.6.4 schema=2
  PANEL 0 title="Daily revenue" xlabel="day" ylabel="USD"
    xscale=linear xlim=0.85,4.15  yscale=linear ylim=10.29,14.91
    ARTIST 0 line label="actual" color=#1f77b4 n=4 x-min=1 x-max=4 y-min=10.5 y-max=14.7
```

`pt.describe` reads only these attrs, so its keys are the schema names
above — a line greps straight back to the SVG. All of it recoverable
with one XML parse: no glyph-path OCR, no pixel→data inversion.

---

## Schema-only consumers: `pt.describe` and `pt.layout_diagram`

[`pt.describe(chart)`](../describe.py) (text summary, above) and
[`pt.layout_diagram(chart)`](../layout_diagram.py) (visual layout
schematic) both read *only* `data-plotlet-*` attrs — no private
imports. Treat their sources as the canonical worked examples for
building your own schema consumer (layout linter, AI inspection
script, etc.).
