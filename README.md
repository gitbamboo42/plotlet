# plotlet

A Python library for SVG plots — with multi-panel composition, shared-axis layouts, and an extension API for custom plot types.

## What it's for

plotlet is built for **multi-panel scientific figures with custom plot types** — genome tracks, spike rasters, climate stacks, Manhattan plots, phylogenetic trees. The core ships ~5 standard plots plus multi-panel composition (`|`, `/`, `share_x()`). Custom plot types are a 3-step recipe and live in your own project (or [`src/plotlet/recipes/`](src/plotlet/recipes/)). See [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) for the framing.

```python
import plotlet as pt

data = {
    "x":      [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
    "y":      [1, 4, 9, 16, 25, 1, 8, 27, 64, 125],
    "series": ["squares"] * 5 + ["cubes"] * 5,
}

c = pt.chart(data, title="Hello", xlabel="x", ylabel="y", legend=True, grid=True)
c.line(x="x", y="y", hue="series")
c                                        # auto-renders in Jupyter
```

## Install

```bash
pip install plotlet
```

## Properties

- **Minimal dependencies.** `fonttools` for font handling. numpy / pandas / polars inputs work transparently.
- **Static and reproducible.** No interactivity, no animation. Same script → byte-identical SVG, identical across Linux / macOS / Windows / headless CI (bundled DejaVu Sans + text-as-paths).
- **Jupyter-native.** `Chart._repr_html_` auto-renders the last expression in a cell.
- **Compact output.** Each plot is ~50 KB SVG, self-contained.
- **Compositional.** Multi-panel layouts via `|`, `/`, `pt.grid`; share scales with `(a | b).share_x()` or `pt.grid(..., share_x="col")`; layout-level legend covers both discrete swatches and continuous gradients (the colorbar) via one constructor.
- **AI-readable.** Every figure ships `data-plotlet-*` attributes describing plot type, axes, scales, ranges, and series labels — readable in one XML parse. Schema: [docs/AI_ATTRS.md](docs/AI_ATTRS.md).

## API

`pt.chart(data, **opts)` returns a `Chart` bound to a table — any object that supports `data[col_name]` returning an iterable (pandas / polars / dict-of-lists / dict-of-arrays). All methods return `self`.

### Frame options

Pass at construction or as chained setters:

`title`, `xlabel`, `ylabel`, `xlim=(a, b)`, `ylim=(a, b)`, `xscale="linear"|"log"|"category"|"symlog"|"power"|"sqrt"`, `yscale=...`, `grid=True/False`, `legend=True/False`, `data_width`, `data_height`. Sizes accept bare pixels (`400`) or unit-suffixed strings (`"4in"`, `"10cm"`, `"100mm"`, `"72pt"`). `"symlog"` accepts `linthresh=` (default `1.0`) to size the linear region around zero; `"power"` accepts `exponent=`. `"sqrt"` is shorthand for `"power"` with `exponent=0.5`.

The data region is the user-facing primitive — the canvas grows to fit titles and tick labels. To target a specific SVG canvas, chain `.fit(canvas_width=…, canvas_height=…)` after composing.

String-valued data on either axis auto-switches to a categorical scale (alphabetical by default). `c.xscale("category", order=[...], padding=0)` for explicit ordering; `padding=0` makes bands contiguous (heatmap-track look).

Tick overrides: `c.xticks([0, 5, 10], ["A","B","C"], rotation=45, fontsize=12, direction="out", marks=False)`. Pass `[]` to hide. `yticks(...)` same shape. `format="{:.0%}"` or `format=lambda v: f"${v/1000:.0f}K"` formats auto-generated tick labels — string and callable both work; explicit labels still override.

### Mark methods

| call | options |
| --- | --- |
| `.line(x=, y=, hue=, **opts)` | `color`, `label`, `linewidth`, `linestyle` (`"-"`, `"--"`, `":"`, `"-."`), `marker` (`"o"`, `"s"`, `"^"`, `"v"`, `"x"`, `"+"`), `markersize` |
| `.scatter(x=, y=, hue=, size=, style=, **opts)` | `color`, `label`, `s` (size), `alpha`, `marker`, `sizes=(min, max)` |
| `.bar(x=, y=, **opts)` | `color`, `label`, `alpha` |
| `.hist(x=, **opts)` | `bins`, `color`, `alpha`, `label` |
| `.fill_between(x=, y1=, y2=, **opts)` | `color`, `alpha`, `label` |
| `.axhline(y, **opts)` / `.axvline(x, **opts)` | `color`, `linewidth`, `linestyle`, `alpha`, `label`, axes-fraction `xmin`/`xmax` (or `ymin`/`ymax`) |
| `.axhspan(ymin, ymax, **opts)` / `.axvspan(xmin, xmax, **opts)` | `color`, `alpha`, `label`, axes-fraction `xmin`/`xmax` (or `ymin`/`ymax`) |
| `.imshow(data, **opts)` | `cmap` (any of ~180 vendored colormaps, default `"viridis"`), `vmin`, `vmax`, `extent=(left, right, bottom, top)` |
| `.heatmap(df, **opts)` | `cmap`, `vmin`, `vmax`, `norm`, `center`, `xticklabels`, `yticklabels`, `legend` |

`hue=<col>` splits into one call per unique value with auto-labels and tab10 colors. Reference lines / spans default to black, are drawn outside the data color cycle, and don't participate in autoscaling.

On `scatter`, `size=<col>` maps a numeric column to per-point area (pixels², rescaled into `sizes=(min, max)` — default `(20, 200)`); `style=<col>` cycles markers per unique value (`o`, `s`, `^`, `v`, `x`, `+`). All three (`hue`, `size`, `style`) compose.

`.imshow` emits one `<rect>` per cell for small grids (`≤10000` cells, vector-clean at any zoom) and a base64 PNG above that. `.heatmap` is the DataFrame-aware companion — `df.index` becomes row labels, `df.columns` becomes column labels; cells render at integer + 0.5 centers so a top/left dendrogram pairs cleanly via `share_x` / `share_y`.

### Subplots

```python
a | b                  # side-by-side
a / b                  # stacked
a | b | c              # left-fold flatten — one row of three, not nested

pt.grid([[a, b],       # 2-D grid; cells may be None
         [c, d]])

# Share x or y across panels — collapses the gap between them
# and unions data ranges; the first leaf is the anchor.
(top / main).share_x()

# Layout-level legend — gradient strip for continuous sources,
# swatch list for discrete, both in one constructor.
hm = pt.chart(); hm.imshow(matrix, cmap="viridis")
hm | pt.legend(hm)             # heatmap + colorbar

# Multi-source — groups by chart, each chart's title as section header.
parent = (a | b); parent.legend()        # sugar for parent | pt.legend()
```

A composed chart owns its children; render the parent. Calling `.show()` on a child raises. Full reference: [docs/SUBPLOTS.md](docs/SUBPLOTS.md).

### Faceting

```python
g = pt.facet(df, by="species", col_wrap=3)   # one panel per unique value
g.scatter(x="bill_length", y="bill_depth")    # replayed against each subset
g.show()
```

`pt.facet` is a chart-shaped recorder: every mark / frame method you'd call on a `Chart` works the same way, but the call is replayed against each group's subset of `df`. `share_x` / `share_y` default to `True`; the per-panel title defaults to the group label (overridable with a recorded `.title(...)` call). `col_wrap` controls grid width; if omitted, the grid lays out as `ceil(sqrt(n_groups))` columns.

### Render / save

```python
c.show()                     # explicit display() in a cell
c.to_svg()                   # raw SVG string
c.save_svg("plot.svg")       # SVG file
c.write_html("plot.html")    # standalone HTML
```

### Color shortcuts

- `"C0"`–`"C9"` → tab10 palette
- Named: `"blue"`, `"orange"`, `"green"`, `"red"`, `"purple"`, `"brown"`, `"pink"`, `"gray"`, `"olive"`, `"cyan"`
- Single-letter: `"k"`, `"w"`, `"b"`, `"g"`, `"r"`
- Any hex / CSS color string passes through

### Themes

Per-chart visual presets. Ships four:

| `classic` (default) | `minimal` | `dark` | `void` |
| --- | --- | --- | --- |
| white bg, four black spines, no grid | white bg, no spines, light dashed grid on | dark bg, light spines, soft grid on | white bg, no spines, no ticks |

```python
c = pt.chart(theme="dark", title="hits", xlabel="t", ylabel="hits")
# or chained: c.theme("minimal")
```

Multi-panel layouts may mix themes per leaf. Define your own with `pt.register_theme(name, dict_or_path)`. Full reference: [docs/THEMES.md](docs/THEMES.md).

## Adding a new plot type

A 3-step recipe (~50–100 lines) gets axes, scales, legend, grid, and composability for free. The `draw` callback uses pixel-coordinate helpers from `plotlet.draw` — no hand-rolling SVG. Recommended home: your own project, or [`src/plotlet/recipes/`](src/plotlet/recipes/) as reference. Full guide: [docs/EXTENDING.md](docs/EXTENDING.md).

## Testing

```bash
python tests/test_chart.py            # check vs. committed baselines
python tests/test_chart.py --update   # regenerate (review the diff!)
python tests/test_chart.py --gallery  # build tests/baseline_images/chart/index.html
python tests/test_subplots.py         # subplot baselines + composition invariants
python tests/test_themes.py           # one chart × each shipped theme
```

## Non-goals

- No interactivity (hover, zoom, click). Static rendering is the point.
- Not aiming for full coverage of standard statistical plots — those needs are well-served elsewhere.
- Not a 3D plotter, not a dashboard tool.
- Not a feature catalog — new plot types belong in user projects or `src/plotlet/recipes/`, not core.

## License

MIT
