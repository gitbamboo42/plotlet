# Extending plotlet

Adding a custom plot type is a 3-step recipe: write three small functions,
bundle them into an `ArtistSpec`, hand it to `add_artist(...)`. After that,
`c.<your_name>(...)` Just Works on any `Chart` — autoscaling, gridlines,
color cycling, and the legend integrate for free. No edits to plotlet internals,
no monkey-patching. Custom artists live in your project or in the separate
[`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions)
package — both are good references.

---

## The three steps

```python
import plotlet as pt
from plotlet.utils import to_list, pack_opts
from plotlet.draw import segment, circle


# 1. record(...) -> dict
#    Turn c.<name>(...) into the artist dict stored in Chart._calls.
#    Pure data — no scales yet. Write an EXPLICIT signature: the
#    parameter list IS your artist's kwarg vocabulary, so Python itself
#    rejects a typo like `c.lollipop(..., widht=2)` at render, and
#    `c.lollipop?` shows the real parameters. `data=` first lets a caller
#    pass the table positionally (`c.lollipop(df, x=, y=)`). Style kwargs
#    the record doesn't consume go into `opts` via `pack_opts` (which
#    drops the None defaults, so the draw side's `.get(k, default)` still
#    falls through to your defaults).
def my_record(data=None, x=None, y=None, color=None, linewidth=None,
              label=None):
    if data is None or x is None or y is None:
        raise TypeError("lollipop requires data=, x=, y=.")
    return {"type": "lollipop",
            "xs": to_list(data[x]),
            "ys": to_list(data[y]),
            "opts": pack_opts(color=color, linewidth=linewidth, label=label)}


# 2. xdomain(a) / ydomain(a) -> Iterable[float] | None
#    Yield every value that should participate in axis autoscaling. Return
#    None if your artist doesn't constrain that axis (e.g. axhline ignores x).
def my_xdomain(a): return a["xs"]
def my_ydomain(a): return list(a["ys"]) + [0]   # always include 0 for stems


# 3. draw(a, ctx) -> str
#    Emit the SVG fragment. ctx carries scales, dimensions, color, defaults.
#    Read style back from opts with a default — an unset kwarg simply
#    isn't in opts, so `.get(k, default)` supplies it.
def my_draw(a, ctx):
    color = a["opts"].get("color") or ctx.color
    width = a["opts"].get("linewidth", 1.5)
    out = []
    y0 = ctx.y_scale(0)
    for x, y in zip(a["xs"], a["ys"]):
        px, py = ctx.x_scale(x), ctx.y_scale(y)
        out.append(segment(px, y0, px, py, color=color, width=width))
        out.append(circle(px, py, 5, fill=color))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="lollipop",
    record=my_record, xdomain=my_xdomain, ydomain=my_ydomain, draw=my_draw,
))

c = pt.chart()
c.lollipop({"x": [1, 2, 3, 4, 5], "y": [3, 7, 2, 9, 4]},
           x="x", y="y", label="A")
c.title("Lollipop chart").gridlines(True).legend(True).save_svg("out.svg")
```

Worked example: [`lollipop.py`](https://github.com/gitbamboo42/plotlet-extensions/blob/main/src/plotlet/extensions/lollipop.py)
in the `plotlet-extensions` package — basic artist plus an optional
`legend_entries` so the legend entry looks like a tiny lollipop. Every
extension in [`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions)
is a working reference; skim a couple before writing your own.

## When your functions run

None of them run when the user calls `c.lollipop(...)` — that only
appends the raw call to the journal. Everything executes inside
`to_svg()`, split across the two render passes
([ARCHITECTURE.md](ARCHITECTURE.md)):

| Hook | Pass | What exists at that point |
|---|---|---|
| `record` | resolve | Nothing but the raw kwargs. No scales, no pixels — its *output* is what domains and scales get built from. Re-runs on every render (re-renders replay the journal), so it must return the same result every time and touch nothing outside itself. |
| `xdomain` / `ydomain`, `axis_order`, `frame_defaults` | resolve | The record dict from `record`. Still data-space only. |
| `draw`, `legend_entries`, `data_attrs` | emit | Everything is already decided: `ctx` carries the final pixel scales, panel size, and resolved color. Turn the record into SVG text here; do not make any new decisions. |

Two things follow from this: an error raised in `record` appears when the
chart is rendered, not on the line where the user typed the call; and
rendering a `ResolvedIR` twice only re-runs the emit column — `record`
already ran once, at resolve.

---

## Drawing helpers — `plotlet.draw`

Pixel-coordinate primitives. Compose them in `draw` with `"".join(...)`; the
framework wraps your fragment in a `<g>` that carries `data-plotlet-*` attrs.

| Helper | What it emits |
|---|---|
| `segment(x1, y1, x2, y2, *, color, width, dash, alpha)` | One `<line>`. |
| `rect(x, y, w, h, *, fill, stroke, stroke_width, alpha, fill_alpha, stroke_alpha)` | One `<rect>`. `fill=None` (default) → outline-only. |
| `circle(cx, cy, r, *, fill, stroke, stroke_width, alpha, fill_alpha, stroke_alpha)` | One `<circle>`. |
| `path(d, *, fill, stroke, stroke_width, dash, alpha, fill_alpha, stroke_alpha)` | `<path>` with arbitrary `d`. Use when polyline / polygon aren't shaped right. |
| `polyline(points, *, color, width, dash, alpha)` | Stroked polyline through `[(x, y), …]`. No fill. |
| `polygon(points, *, fill, stroke, stroke_width, alpha, fill_alpha, stroke_alpha)` | Closed shape (auto-trailing `Z`) through `[(x, y), …]`. |
| `errorbar_v(x, y_lo, y_hi, *, capsize, color, width, alpha)` | Vertical bar with two caps; `capsize=0` drops the caps. |
| `errorbar_h(y, x_lo, x_hi, *, capsize, color, width, alpha)` | Horizontal bar with two caps. |
| `marker(kind, x, y, size, color, alpha, edgecolor=, edgewidth=)` | One of `"o" "s" "^" "v" "<" ">" "x" "+" "*" "D" "h"` at pixel `(x, y)`; `edgecolor=` outlines the filled kinds. |
| `text_path(s, x, y, size, anchor, color, fontstyle=, fontweight=)` | Text as glyph paths (font-independent across machines); `fontstyle="italic"` / `fontweight="bold"` select the active family's real variant faces. |
| `arc(x0, y0, x1, y1, *, height, **path_kwargs)` | Half-ellipse arc between two points; `height` sets the apex distance (sign picks the side). |
| `split_rect(x, y, w, h, n, i, *, ...)` / `split_pie(x, y, w, h, n, i, *, ...)` | Sector `i` of a rect perimeter / pie divided into `n` sectors — glyphs for set-membership marks. |

`dash=` accepts the short codes (`"--"`, `":"`, `"-."`) or a raw SVG
dasharray (`"6,3"`). `fill_alpha` / `stroke_alpha` override `alpha` per
channel — leave them `None` for the lean single-`opacity` path.

When no helper fits — Bézier curves, `<text>`, `<image>`, gradients — drop
to a raw f-string. It's just SVG.

---

## ArtistSpec fields

The authoritative field list, signatures, and defaults are the
`ArtistSpec` dataclass in [`registry.py`](../src/plotlet/registry.py) —
`name`, `record`, and `draw` are required; everything else is an opt-in
behavior. What each opt-in is *for*:

| Field | When you need it |
|---|---|
| `accepts_data_positional` | Default `True` — enables the `c.<artist>(df, x=, y=)` sugar that hoists a single positional arg into `kw["data"]`. Set `False` for matrix-input or single-primary-input artists (`heatmap`, `imshow`, `axhline`, `annotate`) so their `args[0]` doesn't get swallowed. Multi-positional artists (rect, polygon, …) are unaffected either way because the sugar only triggers on `len(args) == 1`. |
| `xdomain` / `ydomain` | Your artist's data should drive axis limits. Return `None` for decorative artists (axhline, axvline). |
| `xdomain_log` / `ydomain_log` | Domain contribution under a **log** scale when it must differ from the plain hook — e.g. a CI band whose non-positive bounds would poison a log domain. `None` (default) → the plain hook serves every scale kind. |
| `layer` | `"background"` for fills (drawn first), `"foreground"` for reference lines (drawn last). Default `"data"`. |
| `uses_color_cycle` | Set `False` for artists that pick their own color (reflines, image artists). Set `default_color` for the fallback. |
| `legend_entries` | Return the legend entries this artist contributes (zero or more). Each entry is `{"label": str, "color": str}` plus optional `"alpha"`, `"group"` (clusters entries under one header), and `"paint"` — `paint(a, ctx, x0, y_mid) -> svg_fragment` overrides the default rect swatch. Most one-series-per-call artists return zero or one entry depending on whether `label=` was set. |
| `legend_gradient` | For artists with a continuous color mapping. Returns `{"kind": "continuous", "cmap": ..., "vmin": ..., "vmax": ...}`. |
| `data_attrs` | AI-readable type-specific attrs. Keys land on the artist's `<g>` as `data-plotlet-<key>`. Common attrs (type, index, label, color) are automatic — see [`AI_ATTRS.md`](AI_ATTRS.md). |
| `flips_y_axis` | Return `True` when this artist needs the y-axis inverted (top → bottom). Used by `imshow` / `heatmap` so row 0 sits at the top. |
| `tight_domain` | When `True`, the artist's `xdomain` / `ydomain` are used as-is — no `expand` padding added. For artists whose extents are exact (image bounds, raster cell edges). |
| `force_zero_x` / `force_zero_y` | Anchor that axis to zero: if the artist contributes to autoscaling and data lo > 0, push lo down to 0 (and suppress that side's expand). Built-in `bar` and `hist` set `force_zero_y=True`. May be a callable `(a) -> bool` so e.g. a bar with `orientation='h'` forces zero on x instead. |
| `axis_order` | Contribute a canonical order for a categorical axis. Returns `{"x": [...]}` / `{"y": [...]}`. Use when ordering is load-bearing (dendrogram leaves). User's explicit `xscale("category", order=...)` still wins. |
| `frame_defaults` | Return a list of `(call_name, args, kwargs)` recorded *before* your artist. Use for strong defaults (e.g. dendrogram hides all spines). User calls *after* `c.<your_artist>()` still win. |
| `crosses_sectors` | Set `True` for artists whose geometry spans sector boundaries (chord_links, chord_ribbon). Suppresses the inter-sector divider walls while the artist is active — walls cutting through a cross-sector curve read as a layering bug. Sector labels still render. |

Coord support lives with the coord — see the "Coordinate classes" section.

---

## RenderContext

Second argument to `draw` and to legend-entry `paint` callbacks. Bundles
render state so call sites stay short.

| Field | Notes |
|---|---|
| `x_scale`, `y_scale` | `scale(value) -> pixel`. On a categorical axis, returns the band *center*; `.bandwidth` is also available (bars subtract `bandwidth/2` for the rect's left edge). |
| `iw`, `ih` | Inner figure width / height in pixels (after margins). |
| `color` | The resolved color for this artist. `None` if `uses_color_cycle=False` and no `default_color` (e.g. `imshow`). |
| `defaults` | The `spec.json` defaults dict (`linewidth`, `markersize`, `scatter_s`, …). Use these instead of literals. |
| `dash` | Linestyle codes → SVG `stroke-dasharray` strings. The `draw.*` helpers already accept the codes directly via `dash=`. |
| `project` | Set by `c.coordinate(...)` for non-affine coords; `None` for Cartesian and affine coords. `project(t, r) -> (px, py)` maps data-space directly to canvas pixels — use it when you want to draw straight in the target coord (e.g. radial line from `r=0` to `r=1` at angle `t`). |
| `warp` | Set by `c.coordinate(...)` for non-affine coords; `None` for Cartesian and affine coords. `warp(x_px, y_px) -> (px, py)` remaps a pre-warp Cartesian pixel through the coord. Artists opted-in via `declare_coord_support` pass this to `draw.*` helpers via `project=` so segments subdivide, polygons curve, and markers land correctly. |

---

## Artist-dict conventions

Whatever you return from `record(...)` ends up in `Chart._calls`
and is passed to `xdomain` / `ydomain` / `draw` as `a`. Two conventions:

- **Always set `"type"` to your artist name** — used for the registry
  lookup and small special-cases (`force_zero` for bar/hist y, hist
  pre-binning).
- **Always set `"opts"` to the kwargs dict** — color resolution, label
  collection, `linestyle`, `linewidth`, `alpha`, `marker` etc. all live
  there.

Keys starting with `_` (e.g. `_bins`, `_data`, `_color`) are conventionally
"computed during render, used during draw" — see how `imshow` and `hist`
stash pre-processed data in [`artists/`](../src/plotlet/artists/).

Respect deferred rendering: `record` runs early, `draw` runs at `to_svg()`
time. Don't compute scales or colors in `record` — they don't exist yet.

---

## Tree-shaped artists

If you're writing a dendrogram variant (radial, icicle, curved branches,
sunburst, …), don't reach for `scipy.cluster.hierarchy` directly — the
`plotlet.cluster` module exposes the full layout pipeline so a third-party
tree artist is purely a *renderer*. Canonical example: the `curved_tree`
test fixture ([`tests/_curved_tree.py`](../tests/_curved_tree.py)), a
curved-branch renderer built entirely on the public cluster API.

The helpers below live in the `plotlet.cluster` module, reachable either
as `pt.cluster.<helper>` or via `from plotlet.cluster import layout_tree,
fit_parent, ...`. The two driver functions are top-level: `pt.linkage`
and `pt.linkage_split`.

| Public helper | Use |
|---|---|
| `pt.linkage(data, labels=, method=, metric=)` | One scipy.linkage → `SplitTree` (one block). |
| `pt.linkage_split(data, split=, labels=, …)` | Two-level cluster (within-block + centroid between-block) → multi-block `SplitTree`. |
| `build_tree(data, split, tree=, linkage_matrix=, method=, metric=, labels=)` | Standard input dispatch over `tree=` / `linkage_matrix=` / `data`; returns `(SplitTree, had_labels)`. Forward your tree artist's matching parameters straight into it. |
| `layout_tree(tree)` | `SplitTree` → `(blocks, offsets, final_labels)` ready for drawing. Per-block scipy.dendrogram + pooled height normalize. |
| `layout_parent(tree)` | The optional centroid tree's `(icoord, dcoord, leaves)`, or `None` for single-block trees. |
| `fit_parent(blocks, parent_layout, parent_frac, gap_frac=)` | Shrinks per-block dcoords + drops parent leaves to each block's apex so both fit in one panel. |
| `leaf_position(scale, labels, disp)` | Float leaf-position → pixel; gap-aware on split scales. |
| `block_apex_centers(scale, labels, offsets, blocks)` | x-center of each block's topmost merge bar — where parent leaves should land. |
| `parent_leaf_px(midpoints, x)` | Interpolate between block midpoints for fractional parent-tree x values. |
| `tree_frame_defaults(kw)` | Standard `frame_defaults` boilerplate for tree artists: spines off, hide height-axis ticks, root-side expand. (For block gap whitespace, declare `c.sectors(...)` on the panel.) |

A new tree variant is then ~3 callbacks (record / draw / axis_order),
each a thin wrapper around these helpers — the clustering and layout
are not your concern. The visible API stays uniform: `c.<artist>(data,
labels=, orientation=, clusters=, parent=, ...)`.

---

## Coordinate classes

Custom (t, r) → pixel projections — rings, polar discs, future spirals —
live under their own protocol. See [`COORDINATES.md`](COORDINATES.md) for
the model, the hook table, and a minimal worked example.
