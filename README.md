# plotlet

A small, hackable Python library that emits matplotlib-style SVG plots.

## Why

matplotlib is the right tool when you want the kitchen sink. plotlet's niche is **custom plot types** — genome tracks, Manhattan plots, phylogenetic trees, anything matplotlib's extension API makes painful. The whole library has a deliberately tiny, exposed core: adding a new plot type is a 3-step recipe, not an architecture project.

It's a **scaffold, not a feature catalog**: the core ships ~5 standard plots and the infrastructure for extending. Custom plot types live in your own project (or [`cookbook/`](cookbook/)), not upstream. See [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) for the full framing.

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

- **Lightweight.** `fonttools` for font handling. numpy / pandas / polars inputs work transparently if you have them.
- **Static SVG output.** No interactivity, no animation. Same script → byte-identical SVG.
- **Cross-machine reproducible.** Bundled DejaVu Sans + text-as-paths means rendering is identical on Linux, macOS, Windows, headless CI.
- **Jupyter-native.** `Figure._repr_html_` auto-renders the last expression in a cell.
- **Tiny output.** Each plot is ~50 KB SVG, self-contained.
- **Compositional.** Multi-panel layouts via `|`, `/`, `pt.grid`; share scales with `share_x=` / `share_y=`; layout-level legend with `pt.legend()` covering both discrete swatches and continuous gradients (the colorbar).

## API

`pt.chart(data, **opts)` returns a `Chart` bound to a table — any object that supports `data[col_name]` returning an iterable (pandas / polars DataFrames, dict-of-lists, dict-of-arrays). All methods return `self`; `_repr_html_` makes the chart auto-render as the last expression in a Jupyter cell.

### Frame options

Pass at construction (`pt.chart(data, title=..., grid=True, ...)`) or as chained setters (`c.title(...)`, etc.):

`title`, `xlabel`, `ylabel`, `xlim=(a, b)`, `ylim=(a, b)`, `xscale="linear"|"log"|"category"` (chained: `c.xscale("category", order=[...], padding=0)`), `yscale=...`, `grid=True/False`, `legend=True/False`, `width`, `height`

String-valued data on either axis (`scatter(["a","b","c"], ...)`, `bar`, …) auto-switches to a categorical scale, alphabetical by default. `padding=0` makes category bands contiguous (heatmap-track look).

Tick customization: `c.xticks([0, 5, 10], ["A","B","C"], rotation=45, fontsize=12, direction="out", marks=False)`. Pass `[]` to hide. `yticks(...)` works the same way.

### Mark methods

| call | options |
| --- | --- |
| `.line(x=, y=, hue=, **opts)` | `color`, `label`, `linewidth`, `linestyle` (`"-"`, `"--"`, `":"`, `"-."`), `marker` (`"o"`, `"s"`, `"^"`, `"v"`, `"x"`, `"+"`), `markersize` |
| `.scatter(x=, y=, hue=, **opts)` | `color`, `label`, `s` (size), `alpha`, `marker` |
| `.bar(x=, y=, **opts)` | `color`, `label`, `alpha` |
| `.hist(x=, **opts)` | `bins`, `color`, `alpha`, `label` |
| `.fill_between(x=, y1=, y2=, **opts)` | `color`, `alpha`, `label` |
| `.axhline(y, **opts)` / `.axvline(x, **opts)` | `color`, `linewidth`, `linestyle`, `alpha`, `label`, axes-fraction `xmin`/`xmax` (or `ymin`/`ymax`) |
| `.axhspan(ymin, ymax, **opts)` / `.axvspan(xmin, xmax, **opts)` | `color`, `alpha`, `label`, axes-fraction `xmin`/`xmax` (or `ymin`/`ymax`) |
| `.imshow(data, **opts)` | `cmap` (any matplotlib name, default `"viridis"`), `vmin`, `vmax`, `extent=(left, right, bottom, top)` |

`hue=<col>` (on `.line` / `.scatter`) splits into one call per unique value with auto-labels and tab10 colors. Reference lines and spans default to black; spans use `alpha=0.2`. They're drawn outside the data color cycle and don't participate in autoscaling — they're decorations on the frame, not data.

`.imshow(data)` renders a 2-D array as a colored grid. Small grids (`nrows × ncols ≤ 10000`) emit one `<rect>` per cell and stay vector-clean at any zoom; larger grids encode as a single base64 PNG and quantize to 256 levels. Image row 0 is rendered at the top of its rectangle; the y axis stays Cartesian (small at bottom). All ~180 matplotlib colormaps are vendored — see `pt.list_colormaps()`.

### Subplots

Compose multi-panel layouts with operators on `Chart`:

```python
a | b                  # side-by-side
a / b                  # stacked
a | b | c              # left-fold flatten — one row of three, not nested

pt.grid([[a, b],       # 2-D grid; cells may be `None`
         [c, d]])

# Share x or y across panels — collapses the gap between them
# and forces both onto the source's scale.
top  = pt.chart()
main = pt.chart(share_x=top)
top / main             # vertically stacked, x-axis joined

# Layout-level legend (covers colorbar and discrete swatches in
# one constructor — geometry follows from the source's color mapping).
hm = pt.chart(); hm.imshow(matrix, cmap="viridis")
hm | pt.legend(hm)             # heatmap + colorbar (gradient strip)

# Multi-source: groups by chart, using each chart's title as
# section header. `names={chart: "Override"}` renames a header,
# `names={chart: None}` hides it, `group_by_chart=False` flattens.
(hm | top) | pt.legend()       # auto-collects from siblings
parent = a | b; parent.legend()  # sugar for parent | pt.legend()
```

A composed chart owns its children; render the parent (`(a | b).show()` or `.to_svg()` / `.save_svg(...)`). Calling `.show()` on a child raises. See [`docs/SUBPLOTS.md`](docs/SUBPLOTS.md) for the design rationale.

### Render / save

```python
c.show()                     # explicit display() inside a cell
c.to_svg()                   # raw SVG string
c.save_svg("plot.svg")       # SVG file
c.write_html("plot.html")    # standalone HTML
```

### Color shortcuts

- `"C0"`–`"C9"` → tab10 (matches matplotlib)
- Named: `"blue"`, `"orange"`, `"green"`, `"red"`, `"purple"`, `"brown"`, `"pink"`, `"gray"`, `"olive"`, `"cyan"`
- Single-letter: `"k"`, `"w"`, `"b"`, `"g"`, `"r"`
- Any hex / CSS color string passes through

## Adding a new plot type

plotlet's central hackability claim: a custom plot type is a 3-step recipe (~50–100 lines) that gets axes, scales, legend, grid, and composability for free. The recommended home is your own project, or [`cookbook/`](cookbook/) as reference. Full guide: [docs/EXTENDING.md](docs/EXTENDING.md).

## Testing

```bash
python tests/test_chart.py            # check vs. committed baselines
python tests/test_chart.py --update   # regenerate (review the diff!)
python tests/test_chart.py --gallery  # build tests/baseline_images/chart/index.html
python tests/test_subplots.py         # subplot baselines + composition invariants
```

## Non-goals

- No interactivity (hover, zoom, click). Static rendering is the point.
- Not competing with matplotlib on standard plots; matplotlib is bigger and battle-tested.
- Not a 3D plotter, not a dashboard tool.
- Not a feature catalog — new plot types belong in user projects or `cookbook/`, not in the core.

## License

MIT
