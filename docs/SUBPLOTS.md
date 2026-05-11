# Subplots / composition — design pass

> **Update (subplots-2.0):** the per-leaf `share_x=A` / `share_y=A`
> kwargs that appear throughout the historical examples below have been
> replaced by parent-level methods and `pt.grid` kwargs. Modern usage:
>
> ```python
> (a | b | c).share_y()                         # all share y; one anchor
> pt.grid([[A, B], [C, D]], share_x="col")     # column-wise sharing
> pt.grid([[A, B], [C, D]], share_y="row")     # row-wise sharing
> pt.grid([[A, B]], share_x=True)              # all share x ("all")
> ```
>
> Sharing forces equal anchor-side dimension; orthogonal dimension
> scales proportionally to preserve aspect ratio. Data range becomes
> the union across share-class members. The historical descriptions
> below predate this rewrite — the *mechanism* (auto-zero-gap, inner
> margin collapse, scale sharing, etc.) is unchanged; only the *API*
> by which sharing is declared has moved from leaf constructors to
> the parent.

Status: **steps 1, 2, and 3 landed.** Composition primitives (`|`, `/`,
`pt.grid`), single-parent invariant, show-on-child raise, default +
auto-zero-gap for share-equivalence-class neighbors are in (step 1).
Step 2 layers scale sharing on top: a topo-sorted pre-pass over the
parent's leaf tree builds one `_AxisDescriptor` (kind + domain) per
share-equivalence class, every sharer adopts its source's domain, the
matching inner margin shrinks to `layout.inner_gap`, and inner tick
labels redundant with a sharing sibling are dropped (spines and tick
marks remain so each panel still reads as a closed rectangle). Leaves
are body-first: `pt.chart(data_width=..., data_height=...)` declares
the data region exactly, margins are floored at `spec.size.
margin_floor` and grow to fit content (long titles, wide y-tick
labels) via measure-driven margin computation, so the data region
never gets squeezed by overflowing text. To target a specific SVG
canvas size, chain `.fit(canvas_width=…, canvas_height=…)` after
composing — it rescales data regions while keeping fonts, spines,
and margins at their absolute pixel sizes (layout-aware scaling).
Within
a grid, the `hide_*` margin flag propagates column-wise and row-wise
so panels in the same column/row stay x-aligned (a top track sized
by `share_x` lines up with the central chart it sits above), and a
parallel coordination pass aligns body-first cells' measured margins
per column/row so data regions stay aligned across rows and columns.
Step 3 ships the layout-level legend (unified — covers both discrete
swatches and continuous gradients): `pt.legend(*sources, names=,
group_by_chart=)` constructor, `parent.legend(...)` decorator (sugar
over the panel form), grouping by source chart with each chart's
`title` as section header, content-driven width / height, fixed
60-px gradient strips, adaptive tick count, and a `layout.legend_gap`
that sits between a legend and its source separate from the share-pair
joint detection. A "colorbar" is just `pt.legend(hm)` where `hm` has
a continuous color mapping — geometry follows from the source, not
the constructor name.

This doc deliberately separates two things the TODO had bundled:

- **Identity model** — how panels refer to each other for `share_x=`,
  `share_y=`, shared legends, colorbar attachment.
- **Arrangement model** — how panels are placed on the canvas.

The identity model is the load-bearing decision. Arrangement syntax is
secondary and easy to swap (and probably ends up supporting more than
one form).

---

## The five examples this has to express

If a candidate model reads cleanly across all five, it's a real model.
If it only reads well for #3, it's been over-fit to ComplexHeatmap.

1. **Heatmap + colorbar.** Single panel with one attached colorbar.
2. **Heatmap + left dendrogram.** Two panels; tree shares the heatmap's
   y-axis. The tree's leaves must line up with the heatmap's rows.
3. **ComplexHeatmap-style.** Heatmap + top annotation track + left
   dendrogram + shared legend on the right. Three panels share scales
   with the central heatmap; the layout-level legend collects swatches
   from all of them, grouped by source chart.
4. **Two heatmaps sharing one dendrogram.** Tree on the left, two
   heatmaps stacked horizontally, all three share row order. The tree
   is *reused* across heatmaps — not duplicated.
5. **2×2 small-multiples.** Plain grid, no shared scales, no shared
   legend. Sanity check that the model isn't only good for coordinated
   panels.

---

## Settled (not in dispute, regardless of candidate)

These fall out of plotlet's existing architecture and don't need a
candidate to evaluate them:

- **Cross-panel references are object handles**, not string IDs or grid
  positions. plotlet is in-process Python; serialization isn't a
  goal yet, and grid positions are fragile under layout changes. If
  panel B says `share_y=A`, `A` is a Python object.
- **Scale resolution is a pre-pass.** Today's render pipeline already
  computes scales as a discrete phase before any artist draws. Extending
  it: collect all panels, build the dependency DAG from `share_x` /
  `share_y`, topo-sort, build scales in order, then render. Cycles raise.
- **Per-chart legend is unchanged.** Today's `chart.legend()` /
  `legend=True` keeps working as-is — it harvests entries from
  artists that supply `spec.legend_swatch` within that one chart.
- **Layout-level legend is grouped by chart, with the chart's title
  as section header.** A `pt.legend()` panel collects from all charts
  in the layout and renders entries **grouped by source chart**,
  using each chart's existing `title` as the group's section header.
  Example output for charts named A, B, C:

  ```
  A              B              C
   ── high       ── treated      ★ outlier
   ── low        ○ control
  ```

  Overrides via `pt.legend(names={hm: "Treatment", top: None})` —
  string renames the section header, `None` hides it. Opt-out flag
  `group_by_chart=False` collapses everything into one flat list
  (useful when small-multiples genuinely share a series).
  *Implication:* grouping makes dedupe a non-issue — same label in
  different charts sits in different sections naturally.
- **One legend constructor for both discrete and continuous.**
  `pt.legend(hm)` (or `chart.legend()`) renders a gradient strip with
  ticks if `hm`'s color mapping is continuous (e.g. imshow with a
  continuous cmap), a swatch list if discrete (plot/scatter labels,
  categorical imshow), or both stacked if the source mixes them.
  Saying "colorbar" is shorthand for "legend with a continuous source";
  there is no separate `pt.colorbar()` call. To share one gradient
  across heatmaps, pass matching `cmap` / `vmin` / `vmax` to each
  imshow and point the legend at one of them — **no `share_color=`
  mechanism**, color isn't position-critical the way axes are, so
  user-managed kwargs are enough. Per-source overrides via
  `imshow(..., legend={"label": ..., "ticks": ...})`.
- **Dendrograms use the category scale.** A dendrogram on the left of
  a heatmap uses the heatmap's row category scale for leaf positions.
  This is just `share_y=hm` over a categorical scale — no new mechanism.

What's left to decide: how panels are **constructed** (free-standing or
figure-first) and how they're **arranged** (operator algebra or grid
spec). Two candidates below.

---

## Candidate A — free-standing panels + operator algebra

patchwork-flavored. Each panel is a standalone object. The figure
emerges when panels are combined with `|` (hstack) or `/` (vstack).
`pt.grid([[...]])` for irregular layouts.

```python
import plotlet as pt

# Single panel = pt.chart(), the existing recommended surface.
# Composing charts produces a layout (name TBD — see "Open questions").

# ---- 1. Heatmap + colorbar (a continuous-source legend)
hm = pt.chart(); hm.imshow(matrix, cmap="viridis")
out = hm | pt.legend(hm)
out.show()

# ---- 2. Heatmap + left dendrogram (shared y)
hm   = pt.chart();             hm.imshow(matrix)
tree = pt.chart(share_y=hm);   tree.dendrogram(linkage)
out = tree | hm
out.show()

# ---- 3. ComplexHeatmap-style
hm   = pt.chart();             hm.imshow(matrix)
top  = pt.chart(share_x=hm);   top.bar(scores)
tree = pt.chart(share_y=hm);   tree.dendrogram(linkage)
legend = pt.legend()           # auto-collects from siblings — hm's gradient + top's swatches, grouped by title

out = pt.grid([
    [None, top, None  ],
    [tree, hm,  legend],
])
out.show()

# ---- 4. Two heatmaps sharing one dendrogram
hm1  = pt.chart();             hm1.imshow(matrix1)
hm2  = pt.chart(share_y=hm1);  hm2.imshow(matrix2)
tree = pt.chart(share_y=hm1);  tree.dendrogram(linkage)
out = tree | hm1 | hm2
out.show()

# ---- 5. 2x2 small-multiples
a = pt.chart(); a.line(x, y1)
b = pt.chart(); b.line(x, y2)
c = pt.chart(); c.line(x, y3)
d = pt.chart(); d.line(x, y4)
out = (a | b) / (c | d)
out.show()
```

**Operator semantics.** `a | b` returns a horizontal layout node;
`a / b` a vertical one. Layout nodes themselves render and compose, so
`(a | b) / c` works for free. Per-leaf size hints (`pt.chart(data_width=…)`,
the body-first form) drive both natural sizing and the equivalent of
ratios — to make a column 2× wider than another, just set the
data widths. Sum-sizes composition takes it from there.

**Where this shines.** #1, #2, #4, #5. Composition is local; a
function that returns a `chart` (or a layout of charts) drops cleanly
into a bigger composition. Cookbook recipes (`heatmap_with_tree`,
`heatmap_with_top_track`) become functions that *return* a layout
node the caller composes further.

**Where it strains.** #3 — operators with `None` spacers are awkward
(`(None | top | None) / (tree | hm | legend)`). The grid form is the
escape hatch, and #3 reaches for it immediately. So the model has to
ship both forms; the operators don't carry irregular layouts on their
own.

---

## Candidate B — layout-first + grid spec

matplotlib `gridspec`-flavored. Build the layout with explicit
dimensions, address cells by `(row, col)`, fill them in. Cells return
a `chart` already wired into the layout.

```python
import plotlet as pt

# ---- 1. Heatmap + colorbar (a continuous-source legend)
out = pt.layout(rows=1, cols=2, widths=[1, 0.05])
hm = out[0, 0]; hm.imshow(matrix, cmap="viridis")
out.legend(hm, at=(0, 1))
out.show()

# ---- 2. Heatmap + left dendrogram
out = pt.layout(rows=1, cols=2, widths=[0.2, 1])
hm   = out[0, 1]; hm.imshow(matrix)
tree = out[0, 0]; tree.dendrogram(linkage, share_y=hm)
out.show()

# ---- 3. ComplexHeatmap-style
out = pt.layout(rows=2, cols=3,
                widths=[0.2, 1, 0.25],
                heights=[0.2, 1])
hm   = out[1, 1]; hm.imshow(matrix)
top  = out[0, 1]; top.bar(scores, share_x=hm)
tree = out[1, 0]; tree.dendrogram(linkage, share_y=hm)
out.legend(at=(1, 2))                  # auto-collects from siblings
out.show()

# ---- 4. Two heatmaps sharing one dendrogram
out = pt.layout(rows=1, cols=3, widths=[0.2, 1, 1])
hm1  = out[0, 1]; hm1.imshow(matrix1)
hm2  = out[0, 2]; hm2.imshow(matrix2, share_y=hm1)
tree = out[0, 0]; tree.dendrogram(linkage, share_y=hm1)
out.show()

# ---- 5. 2x2 small-multiples
out = pt.layout(rows=2, cols=2)
out[0, 0].line(x, y1)
out[0, 1].line(x, y2)
out[1, 0].line(x, y3)
out[1, 1].line(x, y4)
out.show()
```

**Where this shines.** #3 — the grid shape and sizing are in one
place. Reads top-to-bottom: shape, then content. #5 — clean and
familiar.

**Where it strains.**
- #1 — colorbar width has to be encoded as a manual ratio (`0.05`).
  Colorbars want to auto-size; the up-front grid forces premature
  sizing decisions.
- Cookbook recipes can't return a self-contained layout — they have
  to reach into a parent grid, or receive the layout as a parameter
  and patch into it. The composability of #4 (`tree | hm1 | hm2`)
  becomes harder.
- Adding a panel after the fact means resizing the grid. In A you just
  `|` it on.

---

## Side-by-side verdict

| example | A: operators | B: grid | winner |
|---|---|---|---|
| 1. heatmap + colorbar | `hm \| pt.legend(hm)` | `pt.layout(1,2,widths=[1,0.05])` + index | **A** — legend self-sizes |
| 2. heatmap + left tree | `tree \| hm` | layout + `share_y=hm` | **A** — terser |
| 3. ComplexHeatmap | `pt.grid([[None,top,None],[tree,hm,legend]])` | `pt.layout(2,3,...)` + 4 assignments | **B** slightly — sizes co-located |
| 4. two heatmaps + 1 tree | `tree \| hm1 \| hm2` | `pt.layout(1,3,...)` + indexing | **A** — composable, hands off cleanly |
| 5. 2×2 small-multiples | `(a\|b)/(c\|d)` | `pt.layout(2,2)` + indexing | tie |

A wins or ties on 4/5. B wins clearly on 3 only. That's a strong
argument for **A as the primary surface, with `pt.grid([[...]])` as
the named escape hatch for irregular layouts** — which is exactly how
patchwork itself works (operators primary, `wrap_plots` for irregular).

Recommended:

- **Primary:** A. `pt.chart()` for the leaf, `|` / `/` operators, and
  `pt.grid([[...]])` for irregular grids.
- **One type, leaf or parent.** A bare `chart` calling `.show()` works
  (today's behavior). Combining charts with operators or `pt.grid`
  returns another `Chart` — a "parent chart" — whose `.show()` emits
  the full SVG. Children of a parent can't `.show()` themselves
  (raises); each chart has at most one parent (single-parent
  invariant, enforced at composition time).
- **Sizing.** Body-first per-leaf sizing: `pt.chart(data_width=…,
  data_height=…)` is the only primitive. Sum-sizes composition derives
  the parent's total canvas; ratios are expressed by setting per-leaf
  data widths. Margins grow to fit content (measure-driven), and within
  a grid the per-column/row coordination keeps cells' data regions
  aligned across rows and columns. To target a specific final SVG
  canvas, chain `.fit(canvas_width=…, canvas_height=…)` after composing —
  it rescales data regions layout-aware (fonts, spines, margins, and
  gaps stay at their absolute pixel sizes).

---

## Decisions

1. **What does composition return?** *Resolved: a parent `Chart`, with
   a single-parent invariant.*

   - Composing charts (`a | b`, `a / b`, `pt.grid([[...]])`) returns a
     `Chart` — same type users already know. The result is a "parent
     chart" whose children are the composed leaves.
   - A chart can be in **at most one parent.** Composing with a chart
     that already has a parent raises immediately at composition time,
     not render time. (Catches confused user code; keeps ownership
     unambiguous.)
   - Calling `.show()` / `_repr_html_` on a chart that has a parent
     raises with a message pointing at the parent ("this chart is part
     of `<parent>`; show that instead"). A leaf with no parent shows
     itself — today's behavior, unchanged.
   - Inspection (`repr`, attribute access, `chart._calls`) still works
     on children — only rendering is forbidden. Debugging stays easy.
   - Internally Chart is either one class with a `_parent` / `_children`
     flag, or split into leaf + parent classes behind a single
     user-facing `Chart` name. Implementation detail; doesn't change
     the API.

2. **Where do guides live?** *Resolved: one constructor (`legend`),
   support both panel and decorator forms.*

   Guides are data → glyph mappings. Geometry — gradient strip
   (continuous source) vs. swatch list (discrete source) — is decided
   by the source's color mapping, not by the constructor name. Saying
   "colorbar" is shorthand for "legend with a continuous source"; it
   has no separate API. Placement options:

   - **Per-chart, inside-frame** — `chart.legend()` overlays the data
     area (today's default).
   - **Per-chart, in margin** — `chart.legend(loc="outside right")`
     reserves space in the chart's own margin. Future work; not yet
     built.
   - **Layout-level decorator** — `parent.legend()` / `parent.legend(hm)`
     attaches a legend to a parent chart, auto-sized in reserved
     margin. Use when the guide "comes with" a sub-assembly:

     ```python
     x = (A | B); x.legend()        # legend attached to x (collects from A, B)
     y = (C | D); y.legend(D)       # gradient legend for D, attached to y
     out = x | y                    # each carries its own legend
     ```
   - **Layout-level panel** — `pt.legend()` / `pt.legend(hm)` is a
     chart-shaped object you place explicitly:

     ```python
     out = pt.grid([[None, top, None], [tree, hm, pt.legend()]])
     ```
     Use when you want explicit grid placement and column-width control
     (ComplexHeatmap-style layouts).

   The decorator form is sugar over the panel form internally — same
   renderer, same auto-collection-and-grouping behavior. Two surface
   syntaxes, one mechanism. Pick by intent: decorator for "attached to
   this assembly," panel for "this exact grid cell."

3. **Spacing between panels.** *Resolved: one default + auto-collapse
   for coordinated panels.*
   - Default gap comes from `spec.json` (one number, used for both
     horizontal and vertical directions). No new API surface; users get a
     sane gap without thinking.
   - **Coordinated panels auto-collapse to zero gap.** When
     `b.share_y=a` and `b` is `a`'s horizontal neighbor (or
     `share_x=` + vertical neighbor), the gap between them goes to
     0. matplotlib makes you write `gridspec_kw={'wspace': 0}`
     manually for this; plotlet's `share_y=` already carries the
     intent, so the spacing follows.
   - Same rule for colorbar adjacent to its source chart: `hm |
     pt.colorbar(hm)` collapses the gap between them. Generalized:
     "panel reads its data from immediate neighbor → zero gap."
   - **Override** via a kwarg only when someone hits a wall.
     `pt.grid(..., gap=10)` or `(a | b).gap(0)`. Don't build it until
     a real use case forces it.
   - **No per-edge or per-pair config.** Asymmetric spacing comes from
     nesting: `(tight_pair) | b | (tight_pair)`. Composition expresses
     spacing structure; no second config language.

4. **What does the layout node look like internally?** *Resolved: a
   tree of `Chart`s.*
   Since composition returns a parent `Chart` (decision #1), the
   internal structure is naturally a tree of Charts. A parent Chart
   knows its layout direction (horizontal / vertical / grid) and
   carries its children — themselves Charts, leaf or parent. `to_svg()`
   walks the tree to compute leaf rectangles, then each leaf renders
   into its assigned rect. The existing single-chart render becomes
   the leaf case.

5. **Coordinated artists that span panels** (e.g. a bracket connecting
   two charts). *Resolved: deferred to a future cookbook recipe.* Out
   of scope for the subplots v1.

---

## Suggested implementation order (after this doc lands)

Not a roadmap — just the dependency order:

1. **Parent-Chart layout + rect computation.** ✅ *landed.* Single
   `Chart` class, leaf vs. parent flag. Children list + layout direction
   (h / v / grid). `|` / `/` on `Chart`, plus `pt.grid([[...]])`.
   Single-parent invariant + show-on-child raise. Default gap from
   spec.json (`layout.gap`); auto-zero-gap rule for coordinated
   neighbors (the rect computer reads `share_x` / `share_y` to collapse
   gaps). Two implementation details worth recording:
   - **Operators flatten same-direction LHS in place.** `a | b | c` is
     one parent with three equal children, not a 25/25/50 nested
     `(a|b)|c`. Reusing the LHS variable after composition isn't
     supported — patchwork-style mutating semantics. Cross-direction
     composition (`(a|b)/c`) nests, as expected.
   - **Sub-layout gap is unconditional.** The auto-zero-gap rule
     only fires when *both* sides of a pair are leaves with a
     `share_x=` / `share_y=` link. If either side is itself a parent
     (h / v / grid), the gap is the default. More precise inspection
     ("would the leaf at this edge share with the leaf across the
     boundary?") was not worth the complexity for step 1 — users hit it
     only when nesting layouts and re-asserting sharing across the
     nest boundary, which is rare.
2. **`share_x=` / `share_y=` plumbing on `pt.chart()`** ✅ *landed.*
   Scale-build pre-pass with topo-sort (via `graphlib.TopologicalSorter`)
   across the parent's child tree. `_AxisDescriptor` (kind + domain) is
   computed once per share-equivalence class; each sharer instantiates
   its scale on its own pixel range so panels of different widths still
   line up. Cycles and out-of-tree share targets raise. The four
   nail-down points from earlier discussion all settled:

   - **Inner-axis collapse** uses two flags on `_PanelOpts`:
     `hide_left/right/top/bottom` collapses the matching margin (and
     drops xlabel / ylabel / title there — no room) but keeps spines and
     tick lines intact; `suppress_left_labels` / `suppress_bottom_labels`
     drops tick labels redundant with a sharing sibling. Both apply at
     a joined share-pair joint; only the second is asymmetric (set on the
     panel whose tick-label side faces the joint). The margin flag
     propagates column-wise and row-wise within a grid for alignment;
     the label flag does NOT propagate, so a column-aligned-but-not-
     actually-sharing track keeps its own tick labels.
   - **Inner-margin collapse** uses `layout.inner_gap` (default 12 px
     each side) so joined data areas sit `2 * inner_gap` apart — close
     enough to read as coordinated, with breathing room so corner tick
     labels of independent x/y axes don't kiss across the joint.
   - **Colorbar size hint** falls out of leaf size hints: `pt.chart(
     data_width=80)` for the side-panel slot in `hm | pt.colorbar(hm)`
     works because `_allocate` reads children's natural canvases as
     proportional sizes; sum-sizes composition just adds them up.
   - **Category-y for dendrograms**: `_AxisDescriptor(kind="category")`
     survives sharing, so once a built-in artist exposes categorical y, a
     dendrogram that `share_y=` it gets row-aligned leaf positions
     automatically. y-category scales render r0=0..r1=ih (top-to-bottom)
     to match imshow's row 0 = top convention; y-linear/log stay
     cartesian. Public access: `yscale="category", order=[...]`.

   Two additional tweaks that turned out to matter:

   - **Margin policy.** Leaves are body-first (`data_width=…`,
     `data_height=…`): margins are unscaled (only floored at
     `spec.size.margin_floor`) and grow to fit content via measure-
     driven computation, so the data region is preserved exactly and
     long tick / axis labels never get clipped. Within a grid, cells
     in the same column/row coordinate to share the wider measured
     margin so their data regions stay aligned across rows and columns.
     To target a final SVG canvas size, `.fit(canvas_width=…,
     canvas_height=…)` rescales data regions while keeping fonts /
     spines / margins / gaps at their absolute pixel sizes (layout-aware
     scaling — solves `target = s * data_total + overhead` directly).
   - **Tick density** is `max(2, min(8, iw // 65))` for x and similar for
     y — narrow panels (a tree at 80-px-wide inner) don't get 8 crushed
     labels.

   Grid pair-gaps consider all rows/cols at a boundary (min wins) so
   a joined pair in row 1 still collapses the column gap.
3. **Legend (covers colorbar)** ✅ *landed.* `pt.legend()` panel +
   `parent.legend()` decorator (sugar over panel). One constructor
   handles both discrete swatches (via `spec.legend_swatch`, the same
   hook today's in-frame `chart.legend()` already uses) and continuous
   gradients (new `spec.legend_gradient` hook on `ArtistSpec`,
   implemented for imshow). Geometry chosen per source — gradient strip
   for continuous, swatch list for discrete, both stacked when mixed.
   Layout-level legend groups by source chart, using each chart's
   `title` as section header; `names={chart: "Override"}` replaces
   the header text, `names={chart: None}` hides it, and
   `group_by_chart=False` flattens everything into one unsectioned
   list. Per-imshow override via `imshow(..., legend={"label": ...,
   "ticks": [...]})`.

   Two sizing details that turned out to matter:
   - **Strip height is fixed** (`legend.gradient_height = 60`) per
     continuous entry — independent of source plot height. Pre-render
     pass `_size_legends` overrides each legend leaf's intrinsic
     canvas with its content-driven (width, height) before `_measure`
     runs (unless the user passed explicit `canvas_width=` /
     `canvas_height=` on `pt.legend(...)` — legend leaves have no data
     region, so canvas IS the dimensional primitive there).
   - **Tick count adapts** to strip height (`max(2, min(5, h // 18))`),
     mirroring the axis-tick-density rule in `core._render_inner`,
     so labels don't crowd at small sizes.

   `layout.legend_gap` (6 px) sits between a legend and its source
   neighbor — distinct from the share-pair zero-gap rule, since a
   legend isn't a share joint and shouldn't trigger spine/label
   suppression on either side.
4. **Cookbook recipes:** `heatmap_with_tree`, ComplexHeatmap-style.

Item 4 lands once item 3 is in.
