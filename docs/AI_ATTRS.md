# AI-readable SVG attributes

Every plotlet SVG carries `data-plotlet-*` attributes describing plot
type, axes, scales, ranges, and series labels. AI tools can read plot
semantics directly — without OCR-ing text-as-paths or inverting pixel
positions — in one XML parse.

A typical use is AI-assisted plot iteration: asking an AI whether the
title is clipping, whether the axis range covers the data, whether the
legend overlaps the data area, whether the colormap is discriminable.
The structural metadata below is what makes those questions answerable.

The schema is semver-stable from 0.3.0, declared via
`data-plotlet-schema="1"` on the root `<svg>`.

---

## Schema reference

### Root `<svg>`

| Attribute              | Example                | Notes                                       |
|------------------------|------------------------|---------------------------------------------|
| `data-plotlet-version` | `"0.3.1"`              | the plotlet release that emitted this SVG   |
| `data-plotlet-schema`  | `"1"`                  | bumped only when names change incompatibly  |
| `data-plotlet-kind`    | `"figure"` / `"layout"` | single panel vs. multi-panel composition   |

### Panel `<g>` (one per chart leaf)

| Attribute                | Example                | Notes                                            |
|--------------------------|------------------------|--------------------------------------------------|
| `data-plotlet-kind`      | `"panel"`              | discriminator for nested panels in layouts      |
| `data-plotlet-title`     | `"Daily revenue"`      | omitted if empty                                 |
| `data-plotlet-xlabel`    | `"date"`               | omitted if empty                                 |
| `data-plotlet-ylabel`    | `"USD"`                | omitted if empty                                 |
| `data-plotlet-xscale`    | `"linear"` / `"log"` / `"category"` |                                     |
| `data-plotlet-yscale`    | `"linear"` / `"log"` / `"category"` |                                     |
| `data-plotlet-xlim`      | `"0,42"`               | resolved limits, post-autoscale; omitted on categorical |
| `data-plotlet-ylim`      | `"-1.5,1.5"`           | omitted on categorical                           |
| `data-plotlet-yflip`     | `"true"`               | present only when the y-axis is rendered inverted (larger data y at smaller pixel y); set automatically e.g. by `imshow(origin="upper")` |
| `data-plotlet-panel-bbox`| `"0,0,560,348"`        | `"x,y,w,h"` of the full panel rect (margins included) in figure-SVG coords |
| `data-plotlet-data-area` | `"60,24,500,300"`      | `"x,y,w,h"` of the data region in *panel-local* coords; add the bbox's `(x, y)` for figure-SVG coords |

For categorical axes, the actual category list is emitted as a child
`<metadata>` with `data-plotlet-payload="xcategories"` or
`"ycategories"` carrying a JSON array (see "Categorical lists" below).

### Diagram `<g>` (debug visualizer leaves)

`pt.layout_diagram(c)` returns a leaf that, when composed into a
multi-panel SVG, renders as a `<g>` with `data-plotlet-kind="diagram"`
carrying a pre-built debug schematic. Consumers can identify and skip
these `<g>`s when scanning for data panels:

```python
for g in svg.iter("{http://www.w3.org/2000/svg}g"):
    if g.get("data-plotlet-kind") == "panel":     # data leaf
        ...
    elif g.get("data-plotlet-kind") == "diagram": # debug viz, skip
        continue
```

The diagram `<g>` carries no `panel-bbox` / `data-area` / xlim / ylim
attrs of its own — it isn't a chart panel and has no axes. Its
contents are just rects, paths, and text laid out in the leaf's
allocated rect.

### Artist `<g class="plotlet-artist">` (one per recorded artist)

Common attrs (always emitted):

| Attribute              | Example         |
|------------------------|-----------------|
| `data-plotlet-type`    | `"plot"`, `"bar"`, `"hist"`, `"imshow"`, … |
| `data-plotlet-index`   | `"0"`, `"1"`, … |
| `data-plotlet-label`   | `"actual"` (only if user passed `label=`) |
| `data-plotlet-color`   | `"#1f77b4"` (resolved hex) |

Type-specific attrs:

| Artist          | Type-specific attrs                                                        |
|-----------------|-----------------------------------------------------------------------------|
| `plot`          | `n`, `x-min`, `x-max`, `y-min`, `y-max`, `linestyle`, `marker`              |
| `scatter`       | `n`, `x-min`, `x-max`, `y-min`, `y-max`, `marker`                            |
| `bar`           | `n`, `y-min`, `y-max`                                                        |
| `hist`          | `n` (raw observations), `bins`, `x-min`, `x-max`, `count-max`                |
| `fill_between`  | `n`, `x-min`, `x-max`, `y-min`, `y-max`                                      |
| `axhline`       | `y`                                                                          |
| `axvline`       | `x`                                                                          |
| `axhspan`       | `ymin`, `ymax`                                                               |
| `axvspan`       | `xmin`, `xmax`                                                               |
| `imshow`        | `rows`, `cols`, `vmin`, `vmax`, `cmap`, `extent`, `data-encoding`            |

`imshow` is always raster (PNG-embedded above ~10000 cells, individual
`<rect>`s below). `data-encoding` records which.

### Categorical lists

Category labels live in a `<metadata>` child of the panel `<g>`, so the
attribute namespace stays simple and labels can contain arbitrary
characters (commas, pipes, anything):

```xml
<g transform="..." data-plotlet-kind="panel" data-plotlet-xscale="category" ...>
  <metadata data-plotlet-payload="xcategories"><![CDATA[["Q1","Q2","Q3","Q4"]]]></metadata>
  ...
</g>
```

The CDATA wrap lets values contain `<` `>` `&` without XML escaping;
`json.dumps` won't produce `]]>`, so the wrap is safe.

---

## Adding the schema to a custom artist

When you register a custom artist with `add_artist(ArtistSpec(...))`,
one optional field hooks into this schema:

```python
add_artist(ArtistSpec(
    name="lollipop",
    record=...,
    draw=...,
    # Type-specific attrs — keys become data-plotlet-<key> on the wrapper <g>.
    # Common attrs (type, index, label, color) are added automatically.
    data_attrs=lambda a: {
        "n": len(a["xs"]),
        "x-min": min(a["xs"]),
        "x-max": max(a["xs"]),
    },
))
```

The field is optional. Without it, your artist still gets the common
attrs (type, index, label, color) for free — an AI consumer can address
the artist by index, see its type and color, and get all the panel
context. Type-specific attrs (`n`, ranges, etc.) only appear if you
declare them.

---

## A worked example

```python
import plotlet as pt

c = pt.chart()
c.title("Daily revenue").xlabel("day").ylabel("USD")
c.plot([1, 2, 3, 4], [10.5, 12.3, 11.0, 14.7], label="actual")
print(c.to_svg())
```

What an AI sees in the output (skipping geometry):

```
SVG kind=figure plotlet=0.3.1 schema=1
  PANEL title="Daily revenue" xlabel=day ylabel=USD
        xscale=linear xlim=1.0,4.0  yscale=linear ylim=10.0,15.0
    ARTIST 0 type=plot label=actual color=#1f77b4
           n=4 x-min=1 x-max=4 y-min=10.5 y-max=14.7
```

All of that is recoverable with a single XML parse — no glyph-path OCR,
no pixel→data inversion.

---

## A schema-only consumer: `pt.layout_diagram`

`pt.layout_diagram(chart)` (in [`src/plotlet/layout_diagram.py`](../src/plotlet/layout_diagram.py))
is a debug visualizer that *only* reads `data-plotlet-*` attrs — it
imports nothing from `plotlet.layout` or `plotlet.core`. Pass it a chart
and it returns a separate SVG showing the panel bboxes (dashed),
data areas (solid, sized to scale so the colored ring between them
visually encodes margin proportions), and gaps between adjacent panels
(hatched slabs labeled with pixel size, recovered by pairwise scan of
the bboxes — joined share-pair joints filter out automatically).

Worth treating as the canonical worked example: anything `layout_diagram`
does, your own consumer can do too. Read the source, copy the parsing
helpers, build whatever debug tool, layout linter, or AI inspection
script your project needs.
