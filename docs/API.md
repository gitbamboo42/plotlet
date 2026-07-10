# API reference

`pt.chart(data=None, **opts)` returns a `Chart`. Table-shaped marks
(`scatter`, `line`, `bar`, `hist`, `ecdf`, …) take long-form input
only: pass `data=` (any object supporting `data[col_name]` — pandas /
polars / dict-of-lists / dict-of-arrays) and refer to columns by name
(`x="col"`, `y="col"`, `color="col"`, `fill="col"` on fill-defaulted
artists). `data=` set on `pt.chart(...)` propagates to every mark, so
per-call `data=` is optional once it's set at chart level. `heatmap` is
also table-shaped (`data=df, x=, values=`, see below). The remaining
shape marks (`imshow`, `contour`, `dendrogram`, `axhline`/`axvline`,
`rect`, `polygon`) take their natural positional input — there's no
"column name" version for a 2-D matrix or a single y-value. All methods
return `self`, so they chain.

## Frame options

Pass at construction or as chained setters:

`title`, `xlabel`, `ylabel`, `xlim=(a, b)`, `ylim=(a, b)`, `xscale`,
`yscale`, `grid=True/False`, `legend=True/False`, `clip=True/False`,
`data_width`, `data_height`, `theme` (see [THEMES.md](THEMES.md)),
`font` (see [Fonts](#fonts)).

`c.legend(True, position=...)` places the in-frame legend. Outside
tokens (reserve margin space beside the data area): `"right"` (default),
`"left"`, `"top"`, `"bottom"`. Inside tokens (overlay the data area):
`"top-right"`, `"top-left"`, `"bottom-right"`, `"bottom-left"`,
`"center"`. Outside positions emit no frame; inside positions get a
translucent background for readability over plot marks. `ncols=N`
(also on `pt.legend(...)`) wraps discrete entries into N columns,
filled down-then-across; `"top"` / `"bottom"` default to one
horizontal row until `ncols=` switches them to the grid.

Per-artist `legend={...}` customizes that artist's entries wherever they
render (in-frame or `pt.legend()` panel): `{"label": ..., "ticks": [...]}`
on a continuous source retitles its gradient strip; `{"glyph": "rect"}`
swaps the series swatch for the standard rectangle — the readable choice
when the plot mark itself is tiny (e.g. `scatter` with `size=1.5`);
aesthetic keys (`alpha`, `size`, `marker`, `markersize`, `linewidth`,
`linestyle`) override that value in the legend key only — ggplot2's
`override.aes`. So `scatter(..., alpha=0.2, legend={"alpha": 1})` plots
translucent points with an opaque legend key. Aesthetic guides
(scatter's graded size dots) keep their own glyphs.

Sizes accept bare pixels (`400`) or unit-suffixed strings (`"4in"`,
`"10cm"`, `"100mm"`, `"72pt"`). The **data region** is the user-facing
primitive — the canvas grows to fit titles and tick labels. To target
a specific SVG canvas, chain `.fit(canvas_width=…, canvas_height=…)`
after composing.

`clip=False` lets artists bleed past the data area into the margin
space; default `True` clips at the data boundary so off-axis data can't
paint over tick labels.

### Coordinates

`c.coordinate(pt.CircularCoordinate(...))` switches a panel to a non-Cartesian
coord system. One coordinate per panel; for two coordinate systems, use two
panels (composed via `pt.grid` / `|` / `/`).

`CircularCoordinate` is the only coordinate shipped in core today (ring /
annulus geometry; set `r_inner=0` for a full polar disc). Each coord opts
in its supporting artists via `pt.declare_coord_support(name, [...])`;
the renderer raises if you mix a coord with an artist not in that list.
See [`plotlet-cookbook/circle/`](https://github.com/gitbamboo42/plotlet-cookbook/tree/main/circle) for a worked example and the
protocol notes at the top of
[`src/plotlet/coordinates.py`](../src/plotlet/coordinates.py).

### Scales

`xscale` / `yscale` values:

| value | notes |
| --- | --- |
| `"linear"` | default |
| `"log"` | log10; respect positive data |
| `"category"` | for strings; auto-selected when data is string-valued. `c.xscale("category", order=[...], padding=0)` for explicit ordering. `padding=0` makes bands contiguous (heatmap-track look). For grouped categories with visual gaps, use `c.sectors({cluster: [members]}, axis="x")` — see [Sectors](#sectors) below. The dendrogram's `clusters=` kwarg is a parallel grouping vector that drives the two-level scipy cluster (per-block + centroid linkage); it doesn't push gap layout onto the scale — declare `c.sectors(...)` for that. |
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

`fontstyle="italic"` / `fontweight="bold"` restyle the tick labels
(sector-name labels on that axis inherit the style) with the real
Italic/Bold faces of the active family — see [Fonts](#fonts).
`decoration="underline" | "overline" | "line-through"` adds the
matching stroke line.

`format="{:.0%}"` or `format=lambda v: f"${v/1000:.0f}K"` formats
auto-generated tick labels — string and callable both work; explicit
labels still override.

`minor=True` adds auto-positioned minor ticks (5 per major-gap on linear
scales; sub-decade on log); `minor=[v1, v2, …]` for explicit positions.

Density overrides: `step=0.25` forces a fixed spacing; `count=4` requests
roughly that many major ticks (the nice-numbers algorithm still picks
the actual values).

## Text in labels & annotations

All text (titles, labels, ticks, legend, `text`/`annotate`) accepts any
Unicode character the active font covers ([Fonts](#fonts); the default
DejaVu Sans covers the full scientific set) — just type it, no markup:
Greek (`α μ Σ`), super/subscripts (`10⁻⁵`, `H₂O`, `μm²`, `log₂ FC`),
operators (`× ± ≤ ≈ → √ ∫`). Unicode super/subscripts exist only for
digits, `+ − ( )`, and a few letters — no `x^{n+1}` markup (unbuilt).
`\n` stacks lines: `"Fold change\n(log₂)"`.

## Fonts

Text renders as SVG path outlines from an explicitly named font file —
never an OS font lookup — so output is byte-identical across machines
and viewers need no font installed. Three tiers:

1. **Default — DejaVu Sans** (bundled). Zero config. It stays the
   default for coverage: Greek, Mathematical Operators, arrows, and
   super/subscripts all render without tofu.
2. **Bundled families** — `font="Arimo"`, the journal look:
   metric-compatible with Helvetica/Arial, and the aliases
   `"Helvetica"` / `"Arial"` select it. Arimo covers Greek and
   super/subscripts but few math operators or arrows; glyphs a face
   lacks render as `.notdef` boxes.
3. **Escape hatch** — `font="/path/to/MyFont.ttf"` loads any TTF/OTF
   on disk. Only the author needs the file at render time; the output
   stays self-contained and carries the font's family name, never the
   file path. ⚠️ Embedding a proprietary font's outlines in published
   SVGs may be restricted by its EULA — check before shipping.

`font=` at construction or chained `c.font(...)`; per-chart like
`theme=`, and the two compose (`theme="dark", font="Arimo"`). Unknown
font names raise — no silent fallback, no OS resolution.

Both bundled families ship all four faces (Regular / Bold / Italic /
BoldItalic), so per-text `fontstyle="italic"` / `fontweight="bold"`
(on tick labels and `draw.text_path`) render real drawn variants. A
path-loaded font is one file: italic falls back to a synthetic -12°
skew, and `fontweight="bold"` raises — pass the bold file's path as
`font=` instead.

## Sectors

`c.sectors(spec, axis="x" | "y", ...)` partitions an axis into named
regions. Two kinds, picked from the spec shape:

- **Continuous** — values are numeric lengths. Each artist's value
  column (named via `column=`) is offset into a single global
  coordinate so the standard linear scale covers every sector.

  ```python
  c.sectors({"warmup": 100, "training": 500, "cooldown": 50},
            column="phase")
  c.scatter(data=df, x="t", y="v")   # df has a 'phase' column
  ```

- **Categorical** — values are lists of category labels. Sectors group
  the categorical axis members; the category scale inserts visual gaps
  between groups and reorders cells. This is the unification of heatmap
  row/column clustering with continuous-axis partitioning.

  ```python
  c.sectors({"clusterA": ["c1", "c2"],
             "clusterB": ["c3"]}, axis="x")
  # tidy input: the `col` column holds the x labels (one table row per
  # heatmap column); the remaining columns are the value tracks.
  c.heatmap(data=df, x="col")
  ```

| kwarg | notes |
| --- | --- |
| `axis="x"` / `"y"` | which axis to partition |
| `column=` | continuous only — the data row's sector tag column |
| `divider=True` | draw boundary divider lines |
| `label=True` | draw sector-name labels at sector centers |
| `gap=None` | inter-sector pixel pad (categorical); `None` → spec default (6 px) |

Typical usage picks one of *gap* (categorical default) or *divider line*
(continuous default) — both at once reads as redundant clutter. For
heatmap clusters with visible gap whitespace and no labels, pass
`divider=False, label=False` so sectors drive axis layout only:
```python
c.sectors({"clusterA": ["c1", "c2"], "clusterB": ["c3"]},
          axis="x", divider=False, label=False)
c.heatmap(data=df, x="col")   # df["col"] = ["c1","c2","c3"]
```

Layout-level sugar fans out one declaration to every leaf:
```python
pt.grid([[t1], [t2], [t3]]).share_x("col").sectors(PHASES, column="phase")
```

## Mark methods

The tables below give a cross-artist at-a-glance comparison. For each
artist's full docstring (usage examples, special behaviors, coord-specific
kwargs like `arc=False`), read it directly via `help(c.line)` or `c.line?`
in Jupyter — `Chart.__getattr__` surfaces each artist's module docstring
on the recorder.

Every data mark is long-form: a `data` source plus column-name
aesthetics. Three equivalent call shapes — pick whichever reads
cleanest at the call site:

```python
c = pt.chart(df)                            # df on the chart
c.line(x="t", y="v")                        # inherits df

c.line(df, x="t", y="v")                    # df positional (sugar)
c.line(data=df, x="t", y="v")               # df as kwarg
```

The primary grouping aes is `color=` for stroke-defaulted artists
(line, scatter, regression, density_1d, ecdf, freqpoly, rug) and
`fill=` for fill-defaulted ones (bar, hist, area, boxplot, violin,
strip, swarm). Each accepts a literal color string or a column name;
column → one series per unique level.

`line` and `scatter` accept additional column-driven aes:
`group=` (invisible split — no color/legend burn; e.g. one polyline per
subject within a cohort) and `alpha=` (opacity per level, linearly
interpolated through `alphas=(min, max)`, default `(0.3, 1.0)`).
`line` additionally accepts `linestyle=` — literal dash spec (`"--"`,
`":"`, `"-."`, …) or a column name (cycle dashes per level). Not on
`scatter` since there's no line to dash.

These chart-level aes can be set once on the constructor —
`pt.chart(df, color=, group=, linestyle=, alpha=, fill=)` — and are
inherited by `line`/`scatter` calls that don't override them. Other
artists (boxplot, bar, hist, etc.) accept only the relevant subset for
their geometry; chart-level aes they don't support pass through silently.

The tables list styling kwargs; the grouping/long-form pattern is
universal and not repeated.

### xy and 1-D distributions

| call | options |
| --- | --- |
| `.line(x=, y=, color=, group=, linestyle=, alpha=, **opts)` | `palette`, `alphas=(min, max)`, `label`, `linewidth`, `marker`, `size` (marker radius px), `curve` (`"linear"`, `"step-before"`, `"step-after"`, `"step-mid"`) — `linestyle=` dispatches: literal (`"-"`, `"--"`, `":"`, `"-."`, …) → fixed dash; column name → cycle dashes per level. `estimator="mean"\|"median"` collapses replicate rows per x with a CI band (`ci="t"\|"boot"\|None`, `level`, `n_boot`, `seed`, `band_alpha`) — seaborn lineplot |
| `.step(x=, y=, where=, **opts)` | sugar over `line(curve=…)`; `where=` is `"pre"` / `"post"` (default) / `"mid"` |
| `.scatter(x=, y=, color=, group=, alpha=, size=, style=, **opts)` | `palette`, `alphas=(min, max)`, `label`, `marker`, `sizes=(min, max)`, `size_legend={"breaks": [...], "labels": [...]}`, `cmap`, `vmin`, `vmax`, `norm` — `color=<col>` dispatches on dtype: numeric col → cmap, categorical → palette. `size=` dispatches: number → fixed radius (px), list → per-point, column → graded via `sizes=(lo, hi)` |
| `.regression(x=, y=, color=, **opts)` | `palette`, `level=0.95`, `alpha=0.2`, `linewidth=1.8` — OLS fit + Student-t band. `order=` fits a polynomial; `robust=True` a Huber IRLS fit with a bootstrap band (`n_boot=200`, `seed=0`) |
| `.hist(x=, fill=, **opts)` | `color` (stroke), `palette`, `bins`, `density`, `histtype` (`"bar"` / `"step"` / `"stepfilled"`), `orientation` |
| `.density_1d(x=, color=, **opts)` | `palette`, `bw`, `n_grid=200`, `fill=True/False`, `alpha` — Gaussian KDE |
| `.ecdf(x=, color=, **opts)` | `palette`, `complement=False` (survival), `linewidth` |
| `.rug(x=, color=, axis="x", **opts)` | `palette`, `length=0.04`, `alpha` — tick marks at observations |
| `.freqpoly(x=, color=, **opts)` | `palette`, `bins`, `density` — line version of hist |
| `.qq(sample=, color=, **opts)` | `dist=` accepts `"normal"`, any `scipy.stats` RV, or another sample; `color=<col>` → one series + reference line per level (`palette=`) |

### Categorical distributions

| call | options |
| --- | --- |
| `.boxplot(x=, y=, fill=, **opts)` | `color` (stroke), `palette`, `orientation`, `notch`, `width`, `whis=1.5`, `flier_size` |
| `.violin(x=, y=, fill=, **opts)` | `color` (stroke), `palette`, `inner="box"\|"quartile"\|None`, `trim`, `bw_adjust`, `fill_alpha` |
| `.swarm(x=, y=, fill=, **opts)` | `color` (outline), `palette`, `size`, `linewidth` — collision-resolved jitter |
| `.strip(x=, y=, fill=, **opts)` | `color` (outline), `palette`, `size`, `jitter` — raw jittered points |
| `.pointplot(x=, y=, color=, **opts)` | `estimator="mean"`, `ci="t"\|"boot"\|None`, `level=0.95`; `color=<col>` → one series per level (`palette=`) |

### Bars, areas, errorbars

| call | options |
| --- | --- |
| `.bar(x=, y=, fill=, position=, **opts)` | `color` (stroke), `palette`, `position="stack"\|"dodge"\|"fill"` for multi-series, `orientation`, `bottom`, `width`, `gap`; `yerr=`/`xerr=` (same specs as errorbar) draw whiskers at bar/slot centers with `ecolor`, `capsize` — defaults `position` to `"dodge"` and requires one row per (category, group). `stat="count"` (drop y=; seaborn countplot) or `stat="mean"` (mean per cell + CI error bars: `ci="t"\|"boot"\|None`, `level`, `n_boot`, `seed`; seaborn barplot) aggregate raw rows |
| `.area(x=, y=, fill=, **opts)` | multi-series stacks when given a list-of-series or `fill=<col>`; `palette`, `base`, `curve`, `alpha` |
| `.fill_between(x=, y1=, y2=, **opts)` | `color`, `alpha`, `curve`, `label` |
| `.errorbar(x=, y=, yerr=, xerr=, **opts)` | scalar, sequence, or `(lower, upper)` tuple for asymmetric bars; `color=` column → grouped series (`palette=`), dodged on a categorical axis with bar-matching `width`/`gap` defaults |

### 2-D distributions

| call | options |
| --- | --- |
| `.hexbin(xs, ys, **opts)` | `gridsize=20`, `cmap`, `mincnt`, `log_count` |
| `.hist2d(x=, y=, **opts)` | `bins=30`, `binwidth`, `binrange` (scalar or per-axis pair), `cmap`, `vmin`, `vmax` — rectangular bins colored by count, empty cells transparent |
| `.kde_2d(x=, y=, color=, **opts)` | `bw`, `n_grid=60`, `levels`, `cmap`, `fill=True` (filled level regions), `alpha` — iso-density contours; `color=<col>` → one single-colored density per level (`palette=`) |
| `.contour(grid, **opts)` | `levels`, `extent=(x0, x1, y0, y1)`, `cmap`, `fill=True` (mpl contourf), `alpha` — pre-computed 2-D grid |
| `.ridge(x=, y=, color=, **opts)` | `overlap=1.4`, `bw`, `alpha` — joyplot; `color=<col>` → overlaid sub-densities per row (`palette=`) |

### Images, matrices, reference, shapes, text

| call | options |
| --- | --- |
| `.imshow(data, **opts)` | `cmap` (~180 vendored, default `"viridis"`), `vmin`, `vmax`, `extent`, `annot`, `fmt`, `annot_color`, `annot_fontsize` |
| `.heatmap(data=df, x=, values=, sector=, **opts)` | Tidy input: each table row → a heatmap column (x-position from the `x` column — numeric → continuous axis, string → categorical), each value column → a track row (`values=` selects/orders them, default = all non-`x`/`sector` columns). A numeric `x` is auto-sorted (row order carries no meaning); duplicate or NaN positions raise. Opts: `cmap`, `vmin`, `vmax`, `norm`, `center`, `palette`, `absent_fill`, `legend`, `annot`, `fmt`, `annot_color`, `annot_fontsize`, `linewidth`, `linecolor`, `border`. `sector=` (a column) + `c.sectors(...)` draws gaps; for categorical-x clusters call `c.sectors({cluster: [members]}, axis=...)` — see [Sectors](#sectors). A bare matrix is not accepted; reshape it into a table first. |
| `.dendrogram(data, **opts)` | `orient="top"\|"left"\|"right"\|"bottom"`, `labels`, `method="single"\|"complete"\|"average"\|"ward"\|...` (scipy), `metric`, `linkage_matrix=<Z>` (raw scipy Z, skip clustering math), `tree=<SplitTree>` (skip clustering entirely), `clusters=[...]` (parallel grouping vector for two-level cluster), `parent=True\|<frac>` (render centroid tree above per-block trees). Visual gap whitespace lives on the panel as `c.sectors(...)` — see [Sectors](#sectors). |
| `.axhline(y, **opts)` / `.axvline(x, **opts)` | `color`, `linewidth`, `linestyle`, `alpha`, axes-fraction `xmin`/`xmax` |
| `.axhspan(ymin, ymax, **opts)` / `.axvspan(xmin, xmax, **opts)` | `color`, `alpha`, `label` |
| `.rect(x, y, w, h, **opts)` / `.polygon(xs, ys, **opts)` / `.polyline(xs, ys, **opts)` | data-coord shapes — `polygon` is closed-and-fillable, `polyline` is open stroke-only |
| `.text(data=df, x=, y=, label=, **opts)` / `.annotate(text, xy=, xytext=, **opts)` | `ha`, `va`, `fontsize`, `arrow=True/False` |

### Notes

- A column-driven grouping aes (`color=<col>` or `fill=<col>`) splits into one call per unique value with auto-labels and tab10 colors; the palette is overridable per-artist via `palette=` — a name string (`"Set2"`), a color list, or a `{category: color}` dict (see [Palettes](#palettes)).
- `color=` is the stroke and `fill=` is the fill — independent kwargs. So an outlined bar is `fill=<col>, color="black"`; previously inexpressible.
- On `line` / `scatter`, `group=<col>` is the **invisible** split — finer-grained sub-records (one polyline per subject, say) without burning a color channel or a legend row. `alpha=<col>` interpolates opacity per level via `alphas=(min, max)`. `line` additionally has `linestyle=<col>` (dash cycle per level); not on `scatter`. When `color=` and `linestyle=` (or `alpha=`) map the *same* column, the existing color legend swatches inherit the dash / opacity — the canonical pattern for colorblind-safe or B&W-print redundancy.
- Reference lines / spans default to black, are drawn outside the data color cycle, and don't participate in autoscaling.
- On `scatter`, `size=<col>` maps a numeric column to per-point radius (px, rescaled into `sizes=(min, max)` — default `(2, 7)`); `style=<col>` cycles markers per unique value (`o`, `s`, `^`, `v`, `x`, `+`). `color`, `group`, `size`, `style`, `alpha` all compose.
- `.imshow` emits one `<rect>` per cell for small grids (≤10000 cells, vector-clean at any zoom) and a base64 PNG above that. `.heatmap` is the tidy-table companion — each table row is a heatmap column (x-position from the `x` column), each value column a track row. A numeric `x` gives a continuous axis that `share_x`-aligns with a scatter/line; a string `x` gives categorical bands so a top/left dendrogram pairs cleanly via `share_x` / `share_y` (or `attach_above` / `attach_left`, which auto-share).
- On both, `annot=True` overlays each cell's value as a text label (correlation / confusion matrices). `annot=<2D array>` uses custom labels — numbers formatted via `fmt`, strings verbatim — so labels independent of cell values (e.g. significance asterisks over a correlation cmap) are a string-array away. `fmt=".2g"` is the format spec (passed to `format(value, fmt)`); palette-mode heatmap labels skip `fmt` and render verbatim (identifiers/counts, not measurements). `annot_color="auto"` picks black or white per cell via luminance; pass any CSS color for uniform text.
- **Cluster gaps.** Heatmap row/column clusters are declared via `c.sectors({cluster: [members]}, axis="x" | "y")` on the panel — the category scale picks up the implied split positions and inserts a 6-px (default) gap at every block boundary, and the heatmap reorders cells at draw time to match the sector cat order. Pass the *same* grouping info as a parallel list to `.dendrogram(clusters=[...])` and it runs scipy *per block* for within-block leaf order plus once more on the per-block centroids for between-block order — a two-level cluster. The dendrogram exposes the resulting leaf order via `axis_order`, so the heatmap follows automatically when both share a category axis (`attach_above` / `attach_left`). `parent=True` on the dendrogram also renders the centroid tree above the per-block trees in the same panel. See [`plotlet-cookbook/heatmaps/`](https://github.com/gitbamboo42/plotlet-cookbook/tree/main/heatmaps) for the worked examples.

## Clustering helpers

Independent of any artist; the dendrogram and `curved_tree` extension both build on these.

| call | returns | notes |
| --- | --- | --- |
| `pt.linkage(data, labels=, method=, metric=)` | `SplitTree` | One scipy.linkage on `data`; wraps as a one-block `SplitTree`. |
| `pt.linkage_split(data, split=, labels=, method=, metric=)` | `SplitTree` | Two-level cluster: scipy.linkage per group (within-block) plus scipy.linkage on the per-group centroids (between-block order). |
| `pt.SplitTree(blocks=, between_order=, between_Z=)` | dataclass | `blocks: [(Z, labels), ...]` + display order + the centroid linkage. Pass as `dendrogram(tree=...)` / `curved_tree(tree=...)` to skip redundant scipy work when the same cluster drives multiple charts. |

Deeper layout helpers — `layout_tree(tree)`, `layout_parent(tree)`, `fit_parent(...)`, `leaf_position(...)`, `block_apex_centers(...)`, `parent_leaf_px(...)`, `build_tree(...)`, `tree_frame_defaults(...)` — exist for writing new tree-shaped artists; import via `from plotlet.cluster import <helper>`. See [`EXTENDING.md`](EXTENDING.md).

## Color shortcuts

- `"C0"`, `"C1"`, … → tab10 cycle (wraps past `"C9"`)
- Named: `"blue"`, `"orange"`, `"green"`, `"red"`, `"purple"`, `"brown"`, `"pink"`, `"gray"`, `"olive"`, `"cyan"` — tab10-flavored, not CSS
- Single-letter: `"b"`, `"g"`, `"r"`, `"c"`, `"m"`, `"y"`, `"k"`, `"w"`
- Grayscale strings: `"0"` (black) – `"1"` (white), e.g. `"0.5"`
- `(r, g, b)` / `(r, g, b, a)` tuples of floats in [0, 1]
- Any hex / CSS color string passes through

## Palettes

- `pt.palette(name)` → list of hex colors. Qualitative names (`pt.list_palettes()`: `"Set1"`–`"Set3"`, `"Pastel1"`/`"Pastel2"`, `"Dark2"`, `"Accent"`, `"Paired"`, `"tab10"`/`"tab20"`/`"tab20b"`/`"tab20c"`) return the full palette; `n` truncates or cycles past the end.
- `pt.palette(name, n)` also samples any continuous colormap (`pt.list_colormaps()`) at `n` evenly-spaced points — e.g. `pt.palette("viridis", 12)` for 12 hex colors, no matplotlib round-trip.
- `"_r"` suffix reverses either kind.
- Artists' `palette=` accepts a name string directly: `c.bar(..., fill="group", palette="Set2")` — alongside the existing list and `{category: color}` dict forms.

## User-defined colormaps

```python
pt.register_colormap("bwr2", ["#2166ac", "white", "#b2182b"])
c.heatmap(data, x="col", y="row", value="z", cmap="bwr2", center=0)
```

- Colors interpolate linearly in RGB, evenly spaced or at explicit `stops=` (positions in [0, 1], first 0 and last 1, strictly increasing).
- The reversed `name + "_r"` variant registers alongside; the name then works everywhere a built-in does — `cmap=` kwargs, colorbars, `pt.palette(name, n)`.
- Anchoring the midpoint at a data value is the norm's job: pass `center=` (or `vmin=`/`vmax=`) to the artist rather than encoding data values in stops.
- Registration is per-process, like `register_theme` — a serialized journal naming a user colormap needs the same `register_colormap` call before re-rendering in a fresh process. Built-in names can't be shadowed.

## Inset axes

```python
c.line(data=df, x="x", y="y")
inset = c.inset(rect=(0.55, 0.55, 0.42, 0.4), xlim=(0, 1), ylim=(0.8, 1))
inset.line(data=df, x="x", y="y")
```

`c.inset(rect=(x, y, w, h))` returns a fresh `Chart` sized as a fraction
of the parent's data area (origin at the bottom-left). It has its own
scales, ticks, and frame; record artists on it normally. The parent's
`to_svg` embeds the inset on top of the data layer.
