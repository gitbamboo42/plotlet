# plotlet

A small, hackable Python library that emits matplotlib-style SVG plots.

## Why

matplotlib is the right tool when you want the kitchen sink. plotlet's niche is **custom plot types** — genome tracks, Manhattan plots, phylogenetic trees, anything matplotlib's extension API makes painful. The whole library is ~700 lines of Python with a deliberately tiny, exposed core: adding a new plot type is a 3-step recipe, not an architecture project.

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

Not on PyPI yet — clone and install editable:

```bash
git clone <repo>
cd plotlet
pip install -e .
```

## Properties

- **Lightweight.** `fonttools` for font handling. numpy / pandas / polars inputs work transparently if you have them.
- **Static SVG output.** No interactivity, no animation. Same script → byte-identical SVG.
- **Cross-machine reproducible.** Bundled DejaVu Sans + text-as-paths means rendering is identical on Linux, macOS, Windows, headless CI.
- **Jupyter-native.** `Figure._repr_html_` auto-renders the last expression in a cell.
- **Tiny output.** Each plot is ~50 KB SVG, self-contained.

## API

`pt.chart(data, **opts)` returns a `Chart` bound to a table — any object that supports `data[col_name]` returning an iterable (pandas / polars DataFrames, dict-of-lists, dict-of-arrays). All methods return `self`; `_repr_html_` makes the chart auto-render as the last expression in a Jupyter cell.

### Frame options

Pass at construction (`pt.chart(data, title=..., grid=True, ...)`) or as chained setters (`c.title(...)`, etc.):

`title`, `xlabel`, `ylabel`, `xlim=(a, b)`, `ylim=(a, b)`, `xscale="log"|"linear"`, `yscale=...`, `grid=True/False`, `legend=True/False`, `width`, `height`

### Mark methods

| call | options |
| --- | --- |
| `.line(x=, y=, hue=, **opts)` | `color`, `label`, `linewidth`, `linestyle` (`"-"`, `"--"`, `":"`, `"-."`), `marker` (`"o"`, `"s"`, `"^"`, `"v"`, `"x"`, `"+"`), `markersize` |
| `.scatter(x=, y=, hue=, **opts)` | `color`, `label`, `s` (size), `alpha`, `marker` |
| `.bar(x=, y=, **opts)` | `color`, `label`, `alpha` |
| `.hist(x=, **opts)` | `bins`, `color`, `alpha`, `label` |
| `.fill_between(x=, y1=, y2=, **opts)` | `color`, `alpha`, `label` |

`hue=<col>` (on `.line` / `.scatter`) splits into one call per unique value with auto-labels and tab10 colors.

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
```

## Non-goals

- No interactivity (hover, zoom, click). Static rendering is the point.
- Not competing with matplotlib on standard plots; matplotlib is bigger and battle-tested.
- Not a 3D plotter, not a dashboard tool.
- Not a feature catalog — new plot types belong in user projects or `cookbook/`, not in the core.

## License

MIT
