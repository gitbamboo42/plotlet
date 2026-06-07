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
| `data-plotlet-version` | `"0.4.1"`              | the plotlet release that emitted this SVG  |
| `data-plotlet-schema`  | `"2"`                  | bumped only when names change incompatibly |
| `data-plotlet-kind`    | `"figure"` / `"layout"` | single panel vs. multi-panel composition  |

### Panel `<g>` (one per chart leaf)

| Attribute                | Example                | Notes |
|--------------------------|------------------------|-------|
| `data-plotlet-kind`      | `"panel"`              | discriminator for nested panels in layouts |
| `data-plotlet-title`     | `"Daily revenue"`      | omitted if empty |
| `data-plotlet-xlabel` / `-ylabel` | `"date"` / `"USD"` | omitted if empty |
| `data-plotlet-xscale` / `-yscale` | `"linear"` / `"log"` / `"category"` | |
| `data-plotlet-xlim` / `-ylim` | `"0,42"` / `"-1.5,1.5"` | resolved limits post-autoscale; omitted on categorical axes |
| `data-plotlet-yflip`     | `"true"`               | present only when y is rendered inverted (e.g. `imshow(origin="upper")`) |
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

Inline legends (rendered inside a panel via `chart(legend=True,
legend_position=...)`) live inside the panel `<g>` and don't carry
these attrs — their geometry is part of the panel's chrome rather than
a sibling leaf. Filter by `data-plotlet-kind` to distinguish.

### Artist `<g class="plotlet-artist">` (one per recorded artist)

Common attrs (always emitted):

| Attribute              | Example         |
|------------------------|-----------------|
| `data-plotlet-type`    | `"line"`, `"bar"`, `"hist"`, `"imshow"`, … |
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
| `axhline` / `axvline` | `y` / `x`                                                              |
| `axhspan` / `axvspan` | `ymin`, `ymax` / `xmin`, `xmax`                                        |
| `imshow`        | `rows`, `cols`, `vmin`, `vmax`, `cmap`, `extent`, `data-encoding` (`"rects"` below ~10000 cells, `"png"` above) |

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
c = pt.chart()
c.title("Daily revenue").xlabel("day").ylabel("USD")
c.line(data={"day": [1, 2, 3, 4], "usd": [10.5, 12.3, 11.0, 14.7]},
       x="day", y="usd", label="actual")
print(c.to_svg())
```

What an AI sees, semantically:

```
SVG kind=figure plotlet=0.4.1 schema=2
  PANEL title="Daily revenue" xlabel=day ylabel=USD
        xscale=linear xlim=1.0,4.0  yscale=linear ylim=10.0,15.0
    ARTIST 0 type=line label=actual color=#1f77b4
           n=4 x-min=1 x-max=4 y-min=10.5 y-max=14.7
```

All recoverable with one XML parse — no glyph-path OCR, no pixel→data
inversion.

---

## Schema-only consumer: `pt.layout_diagram`

[`pt.layout_diagram(chart)`](../src/plotlet/layout_diagram.py) is a debug
visualizer that reads *only* `data-plotlet-*` attrs — no private imports.
Treat its source as the canonical worked example for building your own
schema consumer (layout linter, AI inspection script, etc.).
