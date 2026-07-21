# Subplots / composition

plotlet composes charts via three primitives:

| Operator | Result |
|---|---|
| `a \| b` | horizontal stack |
| `a / b` | vertical stack |
| `pt.grid([[A, B], [C, D]])` | 2-D grid; `None` for blank cells |

All three return a parent **`Layout`** — it renders, saves, and composes like a `Chart`, but is its own type. Call `.show()` on the parent to render the whole SVG. A chart can be in **at most one parent**; composing a chart that already has a parent raises at composition time.

## Quick patterns

```python
import plotlet as pt

# Single row
fig = a | b | c

# 2×2 small multiples
fig = pt.grid([[a, b], [c, d]])

# Annotated heatmap — attach trees + strips to a clustered heatmap.
# `c.sectors({cluster: [members]}, axis=...)` declares the cluster
# partition; `attach_*` auto-shares the relevant axis so the gaps + leaf
# order propagate to every panel on the same scale. See the plotlet-cookbook
# repo (heatmaps/) for the worked examples.
hm.sectors(col_clusters, axis="x", divider=False, label=False)
hm.sectors(row_clusters, axis="y", divider=False, label=False)
# tidy input: `sample` column holds the x labels (one row per heatmap
# column), each gene column is a value track.
hm.add_heatmap(data=df, x="sample", values=genes, ...)
hm.attach_above(top_strip, top_tree)   # strip closest to host, tree above
hm.attach_left(left_strip, left_tree)
fig = pt.grid([[hm, pt.legend()]])

# Hstack with shared y
fig = (tree | hm).share_y()

# Fit to a specific canvas after composing
fig.fit(canvas_width=800, canvas_height=600).show()
```

## Sharing scales

```python
(a | b | c).share_y()                          # all share y; first leaf is the anchor
(a / b).share_x()                              # all share x
pt.grid([[A, B], [C, D]]).share_x("col")       # column-wise pairs
pt.grid([[A, B], [C, D]]).share_y("row")       # row-wise pairs
pt.grid([[A, B]]).share_x(True)                # all share x (same as "all")
```

Each leaf in a share-equivalence class adopts the anchor's domain (union of all members' data ranges). The shared dimension (`data_height` for shared-y, `data_width` for shared-x) is equalized; the orthogonal dimension scales proportionally to preserve aspect ratio. Inner tick labels redundant with a sharing sibling are dropped — spines and tick marks stay so each panel still reads as a closed rectangle.

`share_x(...)` / `share_y(...)` accept `hide_labels=False` (default `True`) to keep the share equivalence and column-width alignment but render every panel's axis label and tick labels — useful when each row's axis carries different meaning even though widths agree. For pure width alignment without any axis equivalence, use `align_x("col")` / `align_y("row")`.

**Auto-zero-gap**: when share-class neighbors sit adjacent (horizontally for shared-y, vertically for shared-x), the gap between them collapses to 0 — they read as one continuous frame. Same rule for `pt.legend(hm) | hm`-style "reads from immediate neighbor" cases.

## Sizing

Body-first: declare the **data region**, the canvas grows to fit content.

```python
c = pt.chart(data_width=400, data_height=300, ...)
```

Margins are floored at `spec.size.margin_floor` (default zero) and grow as needed (measure-driven from actual title / tick-label widths). The figure root render adds a separate `spec.size.outer_margin` around the whole composition for edge breathing. For a specific final SVG canvas, chain `.fit()` *after* composing:

```python
fig = (a | b | c).fit(canvas_width=1200, canvas_height=400)
```

`.fit()` rescales each leaf's data region layout-aware — fonts, spines, margins, and inter-panel gaps stay at absolute pixel sizes.

## Gaps

```python
pt.grid([[a, b], [c, d]]).gap(10)         # unified gap (between cols + rows)
(a | b).gap(0)                             # adjacent spines fuse
pt.grid([[a, b], [c, d]]).gap(x=4, y=16)   # per-axis override
```

Defaults come from `spec.json` (`layout.gap`, `layout.gap_x`, `layout.gap_y`). Gap is configured on the layout object — `pt.grid` and `|`/`/` share the same `.gap()` surface.

## Figure title

`.title("...")` on any layout draws one centered band above that layout's rect — the suptitle convention. It nests (a titled row inside a titled grid gets its own band) and works on circular layouts (band above the ring). Panel titles stay on the charts; last call wins.

```python
pt.grid([[a, b], [c, d]]).title("Figure 2")
```

## Legends

One constructor for both discrete swatches and continuous gradients — geometry follows from the source's color mapping, not the constructor name. A "colorbar" is just `pt.legend(hm)` where `hm` has a continuous cmap; no separate `pt.colorbar()` call.

```python
# Panel form — explicit grid cell
pt.grid([[hm, pt.legend(hm)]])

# Composed with | or / — appended as a sibling leaf
(A | B) | pt.legend()         # collects entries from A and B
(C | D) | pt.legend(D)        # gradient legend for D, beside (C | D)

# Group-by-chart with each chart's `title` as section header
pt.legend(a, b, c)
pt.legend(*srcs, group_by_chart=False)   # flat list

# Rename or hide per-source section headers
pt.legend(hm, names={hm: "Treatment", top: None})

# Wrap a long categorical list into columns (filled down-then-across)
pt.legend(src, ncols=3)
```

## Single-parent rule

```python
fig1 = a | b   # ok; a and b are now children of fig1
fig2 = a | c   # ERROR — a is already in fig1
```

If you need a chart in two places, build two separate charts. Children can't `.show()` themselves (raises with a pointer to the parent) — but inspection (`repr`, `chart._calls`) still works; only rendering is forbidden.

## Settled invariants

- **Cross-panel references are object handles**, not string IDs or grid positions. The chart is already in a Python variable — there's no separate naming system to maintain. (`to_json` does emit `$ref` IDs, but that's an internal translation, not a user-facing namespace.)
- **Dendrograms use the category scale.** A dendrogram on the left of a heatmap uses the heatmap's row category scale via `share_y` (or `attach_left`, which auto-shares). With `c.sectors(...)` on the panel and a matching parallel-vector `clusters=` on the dendrogram, the dendrogram's two-level cluster exposes its leaf order via `axis_order` — the heatmap on the same shared scale picks it up automatically (artist `axis_order` beats artist `frame_defaults` order in core's precedence rule, while user-explicit `c.xscale(order=...)` still wins over both).
- **Sectors follow the share class.** `c.sectors(...)` declared on a host (or via `Layout.sectors`) propagates to attached charts and to `CircularCoordinate(inner=)` side-leaves on the matching axis — anything sharing the partitioned axis inherits the partition without redeclaring. Declare `c.sectors(...)` on the side-leaf to opt out.
- **No `share_color=`.** Color isn't position-critical the way axes are; for shared gradients across heatmaps, pass matching `cmap` / `vmin` / `vmax` to each `imshow` and point one legend at any one of them.
- **Coordinated artists that span panels** (brackets, etc.) are out of scope; would land as a plotlet-cookbook recipe.
