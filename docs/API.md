# API reference

`pt.chart(data=None, **opts)` returns a `Chart`. When `data` is given —
any object supporting `data[col_name]` returning an iterable (pandas /
polars / dict-of-lists / dict-of-arrays) — every mark method accepts
long-form `(x="col", y="col", hue="col")`. Otherwise marks take wide-form
positional arrays. All methods return `self`, so they chain.

## Frame options

Pass at construction or as chained setters:

`title`, `xlabel`, `ylabel`, `xlim=(a, b)`, `ylim=(a, b)`, `xscale`,
`yscale`, `grid=True/False`, `legend=True/False`, `clip=True/False`,
`data_width`, `data_height`.

Sizes accept bare pixels (`400`) or unit-suffixed strings (`"4in"`,
`"10cm"`, `"100mm"`, `"72pt"`). The **data region** is the user-facing
primitive — the canvas grows to fit titles and tick labels. To target
a specific SVG canvas, chain `.fit(canvas_width=…, canvas_height=…)`
after composing.

`clip=False` lets artists bleed past the data area into the margin
space; default `True` clips at the data boundary so off-axis data can't
paint over tick labels.

### Scales

`xscale` / `yscale` values:

| value | notes |
| --- | --- |
| `"linear"` | default |
| `"log"` | log10; respect positive data |
| `"category"` | for strings; auto-selected when data is string-valued. `c.xscale("category", order=[...], padding=0)` for explicit ordering. `padding=0` makes bands contiguous (heatmap-track look). |
| `"symlog"` | accepts `linthresh=` (default `1.0`) sizing the linear region around zero |
| `"power"` | accepts `exponent=` |
| `"sqrt"` | shorthand for `"power"` with `exponent=0.5` |
| `"time"` | auto-selected for `datetime.date` / `datetime.datetime` values. Ticks snap to calendar boundaries (year / month / day / hour / minute / second) at a resolution matching the axis span; labels format accordingly. Force with `c.xscale("time")` when data is already epoch-seconds floats; `xlim` accepts datetime or epoch-seconds endpoints. |

### Tick overrides

```python
c.xticks([0, 5, 10], ["A","B","C"], rotation=45, fontsize=12,
         direction="out", marks=False)   # `[]` to hide
c.yticks(...)                            # same shape
```

`format="{:.0%}"` or `format=lambda v: f"${v/1000:.0f}K"` formats
auto-generated tick labels — string and callable both work; explicit
labels still override.

`minor=True` adds auto-positioned minor ticks (5 per major-gap on linear
scales; sub-decade on log); `minor=[v1, v2, …]` for explicit positions.

Density overrides: `step=0.25` forces a fixed spacing; `count=4` requests
roughly that many major ticks (the nice-numbers algorithm still picks
the actual values).

## Mark methods

Every method accepts long-form `(data=df, x="col", y="col", hue="col")`
when the chart was constructed with `pt.chart(data, …)`, and wide-form
positional `(xs, ys)` arrays otherwise. The tables list styling kwargs;
the long-form keyword pattern is universal and not repeated.

### xy and 1-D distributions

| call | options |
| --- | --- |
| `.line(x=, y=, hue=, **opts)` | `color`, `label`, `linewidth`, `linestyle` (`"-"`, `"--"`, `":"`, `"-."`), `marker`, `markersize`, `curve` (`"linear"`, `"step-before"`, `"step-after"`, `"step-mid"`) |
| `.step(x=, y=, where=, **opts)` | sugar over `line(curve=…)`; `where=` is `"pre"` / `"post"` (default) / `"mid"` |
| `.scatter(x=, y=, hue=, size=, style=, **opts)` | `color`, `label`, `s`, `alpha`, `marker`, `sizes=(min, max)` |
| `.regression(x=, y=, **opts)` | `level=0.95`, `alpha=0.2`, `linewidth=1.8` — OLS fit + Student-t band |
| `.hist(x=, hue=, **opts)` | `bins`, `density`, `histtype` (`"bar"` / `"step"` / `"stepfilled"`), `orientation` |
| `.density_1d(x=, hue=, **opts)` | `bw`, `n_grid=200`, `fill`, `alpha` — Gaussian KDE |
| `.ecdf(x=, hue=, **opts)` | `complement=False` (survival), `linewidth` |
| `.rug(x=, hue=, axis="x", **opts)` | `length=0.04`, `alpha` — tick marks at observations |
| `.freqpoly(x=, hue=, **opts)` | `bins`, `density` — line version of hist |
| `.qq(values, dist="normal")` | `dist=` accepts any `scipy.stats` RV or another sample |

### Categorical distributions

| call | options |
| --- | --- |
| `.boxplot(x=, y=, hue=, **opts)` | `orientation`, `notch`, `width`, `whis=1.5`, `flier_size` |
| `.violin(x=, y=, hue=, **opts)` | `inner="box"\|"quartile"\|None`, `trim`, `bw_adjust`, `fill_alpha` |
| `.swarm(x=, y=, hue=, **opts)` | `size`, `dodge`, `palette` — collision-resolved jitter |
| `.strip(x=, y=, hue=, **opts)` | `size`, `dodge`, `jitter` — raw jittered points |
| `.pointplot(cats, values_per_cat, **opts)` | `estimator="mean"`, `ci="t"\|"boot"\|None`, `level=0.95` |

### Bars, areas, errorbars

| call | options |
| --- | --- |
| `.bar(x=, y=, hue=, position=, **opts)` | `position="stack"\|"dodge"\|"fill"` for multi-series, `orientation`, `bottom`, `width`, `gap` |
| `.area(x=, y=, hue=, **opts)` | multi-series stacks when given a list-of-series or `hue=`; `base`, `curve`, `alpha` |
| `.fill_between(x=, y1=, y2=, **opts)` | `color`, `alpha`, `curve`, `label` |
| `.errorbar(x=, y=, yerr=, xerr=, **opts)` | scalar, sequence, or `(lower, upper)` tuple for asymmetric bars |

### 2-D distributions

| call | options |
| --- | --- |
| `.hexbin(xs, ys, **opts)` | `gridsize=20`, `cmap`, `mincnt`, `log_count` |
| `.kde_2d(xs, ys, **opts)` | `bw`, `n_grid=60`, `levels`, `cmap` — iso-density contours |
| `.contour(grid, **opts)` | `levels`, `extent=(x0, x1, y0, y1)`, `cmap` — pre-computed 2-D grid |
| `.ridge(labels, samples_per_label, **opts)` | `overlap=1.4`, `bw`, `alpha` — joyplot |

### Images, matrices, reference, shapes, text

| call | options |
| --- | --- |
| `.imshow(data, **opts)` | `cmap` (~180 vendored, default `"viridis"`), `vmin`, `vmax`, `extent` |
| `.heatmap(df, **opts)` | `cmap`, `vmin`, `vmax`, `norm`, `center`, `xticklabels`, `yticklabels`, `legend` |
| `.dendrogram(matrix, **opts)` | `orient="top"\|"left"\|"right"\|"bottom"`, `linkage="single"\|"average"\|"complete"`, `metric` |
| `.axhline(y, **opts)` / `.axvline(x, **opts)` | `color`, `linewidth`, `linestyle`, `alpha`, axes-fraction `xmin`/`xmax` |
| `.axhspan(ymin, ymax, **opts)` / `.axvspan(xmin, xmax, **opts)` | `color`, `alpha`, `label` |
| `.rect(x, y, w, h, **opts)` / `.polygon(pts, **opts)` | data-coord shapes, `fill`, `stroke` |
| `.text(x, y, s, **opts)` / `.annotate(text, xy=, xytext=, **opts)` | `ha`, `va`, `fontsize`, `arrow=True/False` |

### Notes

- `hue=<col>` splits into one call per unique value with auto-labels and tab10 colors.
- Reference lines / spans default to black, are drawn outside the data color cycle, and don't participate in autoscaling.
- On `scatter`, `size=<col>` maps a numeric column to per-point area (pixels², rescaled into `sizes=(min, max)` — default `(20, 200)`); `style=<col>` cycles markers per unique value (`o`, `s`, `^`, `v`, `x`, `+`). `hue`, `size`, `style` compose.
- `.imshow` emits one `<rect>` per cell for small grids (≤10000 cells, vector-clean at any zoom) and a base64 PNG above that. `.heatmap` is the DataFrame-aware companion — `df.index` becomes row labels, `df.columns` becomes column labels; cells render at integer + 0.5 centers so a top/left dendrogram pairs cleanly via `share_x` / `share_y`.

## Color shortcuts

- `"C0"`–`"C9"` → tab10 palette
- Named: `"blue"`, `"orange"`, `"green"`, `"red"`, `"purple"`, `"brown"`, `"pink"`, `"gray"`, `"olive"`, `"cyan"`
- Single-letter: `"k"`, `"w"`, `"b"`, `"g"`, `"r"`
- Any hex / CSS color string passes through

## Inset axes

```python
c.line(xs, ys)
inset = c.inset(rect=(0.55, 0.55, 0.42, 0.4), xlim=(0, 1), ylim=(0.8, 1))
inset.line(xs, ys)
```

`c.inset(rect=(x, y, w, h))` returns a fresh `Chart` sized as a fraction
of the parent's data area (origin at the bottom-left). It has its own
scales, ticks, and frame; record artists on it normally. The parent's
`to_svg` embeds the inset on top of the data layer.
