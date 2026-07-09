# Extending plotlet

Adding a custom plot type is a 3-step recipe: write three small functions,
bundle them into an `ArtistSpec`, hand it to `add_artist(...)`. After that,
`c.<your_name>(...)` Just Works on any `Chart` — autoscaling, gridlines,
color cycling, and the legend integrate for free. No edits to `core.py`,
no monkey-patching. Custom artists live in your project, in the separate
[`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions)
package, or (for the few core depends on) in
[`src/plotlet/extensions/`](../src/plotlet/extensions/) — all good references.

---

## The three steps

```python
import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import segment, circle


# 1. record(args, kwargs) -> dict
#    Turn c.<name>(...) kwargs into the artist dict stored in Chart._calls.
#    Pure data — no scales yet. Long-form is plotlet's standard: pull
#    `data=` and column names out of kw and refuse positional arrays.
#    The dispatch layer hoists a single positional arg into `data=` (the
#    `c.lollipop(df, x="x", y="y")` sugar), so `if args` here just guards
#    against accidental wide-form calls.
def my_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "lollipop requires long-form input: "
            "c.lollipop(data=df, x='col', y='col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    if data is None or x_col is None or y_col is None:
        raise TypeError("lollipop requires data=, x=, y=.")
    return {"type": "lollipop",
            "xs": to_list(data[x_col]),
            "ys": to_list(data[y_col]),
            "opts": kw}


# 2. xdomain(a) / ydomain(a) -> Iterable[float] | None
#    Yield every value that should participate in axis autoscaling. Return
#    None if your artist doesn't constrain that axis (e.g. axhline ignores x).
def my_xdomain(a): return a["xs"]
def my_ydomain(a): return list(a["ys"]) + [0]   # always include 0 for stems


# 3. draw(a, ctx) -> str
#    Emit the SVG fragment. ctx carries scales, dimensions, color, defaults.
def my_draw(a, ctx):
    out = []
    y0 = ctx.y_scale(0)
    for x, y in zip(a["xs"], a["ys"]):
        px, py = ctx.x_scale(x), ctx.y_scale(y)
        out.append(segment(px, y0, px, py, color=ctx.color, width=1.5))
        out.append(circle(px, py, 5, fill=ctx.color))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="lollipop",
    record=my_record, xdomain=my_xdomain, ydomain=my_ydomain, draw=my_draw,
))

c = pt.chart()
c.lollipop({"x": [1, 2, 3, 4, 5], "y": [3, 7, 2, 9, 4]},
           x="x", y="y", label="A")
c.title("Lollipop chart").grid(True).legend(True).save_svg("out.svg")
```

Worked example: [`lollipop.py`](https://github.com/gitbamboo42/plotlet-extensions/blob/main/src/plotlet/extensions/lollipop.py)
in the `plotlet-extensions` package — basic artist plus an optional
`legend_entries` so the legend entry looks like a tiny lollipop. Every
extension in [`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions)
(and the few kept in [`src/plotlet/extensions/`](../src/plotlet/extensions/))
is a working reference; skim a couple before writing your own.

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
| `marker(kind, x, y, size, color, alpha)` | One of `"o" "s" "^" "v" "x" "+"` at pixel `(x, y)`. |
| `text_path(s, x, y, size, anchor, color, fontstyle=, fontweight=)` | Text as glyph paths (font-independent across machines); `fontstyle="italic"` / `fontweight="bold"` select the active family's real variant faces. |

`dash=` accepts the short codes (`"--"`, `":"`, `"-."`) or a raw SVG
dasharray (`"6,3"`). `fill_alpha` / `stroke_alpha` override `alpha` per
channel — leave them `None` for the lean single-`opacity` path.

When no helper fits — Bézier curves, `<text>`, `<image>`, gradients — drop
to a raw f-string. It's just SVG.

---

## ArtistSpec fields

```python
ArtistSpec(
    name: str,
    record: (args, kwargs) -> dict,           # required
    draw: (artist_dict, ctx) -> str,          # required, returns SVG fragment
    xdomain: (artist_dict) -> Iterable | None = lambda a: None,
    ydomain: (artist_dict) -> Iterable | None = lambda a: None,
    accepts_data_positional: bool = True,
    layer: "background" | "data" | "foreground" = "data",
    uses_color_cycle: bool = True,
    default_color: str | None = None,
    legend_entries: (a) -> list[dict] | None = None,
    legend_gradient: (a) -> dict | None = None,
    data_attrs: (a) -> dict | None = None,
    flips_y_axis: (a) -> bool | None = None,
    tight_domain: bool = False,
    force_zero_x: bool | (a) -> bool = False,
    force_zero_y: bool | (a) -> bool = False,
    axis_order: (a) -> dict | None = None,
    frame_defaults: (args, kwargs) -> list[tuple] | None = None,
    crosses_sectors: bool = False,
)
```

| Field | When you need it |
|---|---|
| `accepts_data_positional` | Default `True` — enables the `c.<artist>(df, x=, y=)` sugar that hoists a single positional arg into `kw["data"]`. Set `False` for matrix-input or single-primary-input artists (`heatmap`, `imshow`, `axhline`, `annotate`) so their `args[0]` doesn't get swallowed. Multi-positional artists (rect, polygon, …) are unaffected either way because the sugar only triggers on `len(args) == 1`. |
| `xdomain` / `ydomain` | Your artist's data should drive axis limits. Return `None` for decorative artists (axhline, axvline). |
| `layer` | `"background"` for fills (drawn first), `"foreground"` for reference lines (drawn last). Default `"data"`. |
| `uses_color_cycle` | Set `False` for artists that pick their own color (reflines, image artists). Set `default_color` for the fallback. |
| `legend_entries` | Return the legend entries this artist contributes (zero or more). Each entry is a `{"label": str, "color": str, "paint": callable}` dict where `paint(a, ctx, x0, y_mid) -> svg_fragment` draws the swatch. Most one-series-per-call artists return zero or one entry depending on whether `label=` was set. |
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

Whatever you return from `record(args, kwargs)` ends up in `Chart._calls`
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
tree artist is purely a *renderer*. Canonical example:
[`extensions/curved_tree.py`](../src/plotlet/extensions/curved_tree.py).

The helpers below live in `plotlet.cluster`; import them with
`from plotlet.cluster import layout_tree, fit_parent, ...`. The top-level
`pt.cluster` / `pt.cluster_split` names are the two driver functions
themselves, not the module — the import-from form is what you want for
everything else.

| Public helper | Use |
|---|---|
| `pt.cluster(data, labels=, method=, metric=)` | One scipy.linkage → `SplitTree` (one block). |
| `pt.cluster_split(data, split=, labels=, …)` | Two-level cluster (within-block + centroid between-block) → multi-block `SplitTree`. |
| `build_tree(args, kw, split)` | Standard input dispatch: pops `tree=` / `linkage=` / `data=` from `kw` and returns `(SplitTree, had_labels)`. Drop into your artist's `record`. |
| `layout_tree(tree)` | `SplitTree` → `(blocks, offsets, final_labels)` ready for drawing. Per-block scipy.dendrogram + pooled height normalize. |
| `layout_parent(tree)` | The optional centroid tree's `(icoord, dcoord, leaves)`, or `None` for single-block trees. |
| `fit_parent(blocks, parent_layout, frac, gap_frac=)` | Shrinks per-block dcoords + drops parent leaves to each block's apex so both fit in one panel. |
| `leaf_position(scale, labels, disp)` | Float leaf-position → pixel; gap-aware on split scales. |
| `block_apex_centers(scale, labels, offsets, blocks)` | x-center of each block's topmost merge bar — where parent leaves should land. |
| `parent_leaf_px(midpoints, x)` | Interpolate between block midpoints for fractional parent-tree x values. |
| `tree_frame_defaults(kw)` | Standard `frame_defaults` boilerplate for tree artists: spines off, hide height-axis ticks, root-side expand. (For block gap whitespace, declare `c.sectors(...)` on the panel.) |

A new tree variant is then ~3 callbacks (record / draw / axis_order),
each a thin wrapper around these helpers — the clustering and layout
are not your concern. The visible API stays uniform: `c.<artist>(data,
labels=, orient=, clusters=, parent=, ...)`.

---

## Coordinate classes

Custom (t, r) → pixel projections — rings, polar discs, future spirals —
live under their own protocol. See [`COORDINATES.md`](COORDINATES.md) for
the model, the hook table, and a minimal worked example.
