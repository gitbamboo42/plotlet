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
| `data-plotlet-version` | `"0.3.0"`              | the plotlet release that emitted this SVG   |
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
| `data-plotlet-data-area` | `"60,24,500,300"`      | `"x,y,w,h"` in SVG coords                        |

For categorical axes, the actual category list is emitted as a child
`<metadata>` with `data-plotlet-payload="xcategories"` or
`"ycategories"` carrying a JSON array (see "Categorical lists" below).

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

fig = pt.figure()
fig.title("Daily revenue").xlabel("day").ylabel("USD")
fig.plot([1, 2, 3, 4], [10.5, 12.3, 11.0, 14.7], label="actual")
print(fig.to_svg())
```

What an AI sees in the output (skipping geometry):

```
SVG kind=figure plotlet=0.3.0 schema=1
  PANEL title="Daily revenue" xlabel=day ylabel=USD
        xscale=linear xlim=1.0,4.0  yscale=linear ylim=10.0,15.0
    ARTIST 0 type=plot label=actual color=#1f77b4
           n=4 x-min=1 x-max=4 y-min=10.5 y-max=14.7
```

All of that is recoverable with a single XML parse — no glyph-path OCR,
no pixel→data inversion.
