# Subplots / composition — design pass

Status: **design complete; ready for implementation.** Goal was to
pick a panel-identity and arrangement model so the implementation
pass has a target — see the Decisions section.

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
  positions. plotlet is a small Python library; serialization isn't a
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
- **Colorbar attaches to one chart.** `pt.colorbar(hm)` reads cmap +
  norm from `hm`'s imshow call. To make one colorbar serve multiple
  heatmaps, the user passes matching `cmap` / `vmin` / `vmax` to each
  imshow; the colorbar reads from one of them. **No `share_color=`
  mechanism** — color isn't position-critical the way axes are, so
  user-managed kwargs are enough. If the user gives mismatched
  kwargs and uses one shared colorbar, the bar legitimately
  represents the chart it was given; others look off (user's call).
- **Dendrograms use the band scale.** A dendrogram on the left of a
  heatmap uses the heatmap's row band scale for leaf positions. This
  is just `share_y=hm` over a categorical scale — no new mechanism.

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

# ---- 1. Heatmap + colorbar
hm = pt.chart(); hm.imshow(matrix, cmap="viridis")
out = hm | pt.colorbar(hm)
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
legend = pt.legend()           # auto-collects from siblings, grouped by chart title

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
a = pt.chart(); a.plot(x, y1)
b = pt.chart(); b.plot(x, y2)
c = pt.chart(); c.plot(x, y3)
d = pt.chart(); d.plot(x, y4)
out = (a | b) / (c | d)
out.show()
```

**Operator semantics.** `a | b` returns a horizontal layout node;
`a / b` a vertical one. Layout nodes themselves render and compose, so
`(a | b) / c` works for free. Width/height ratios via a `widths=`
kwarg on `pt.grid` (or a future per-chart size hint); the operator
form defaults to equal sizing.

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

# ---- 1. Heatmap + colorbar
out = pt.layout(rows=1, cols=2, widths=[1, 0.05])
hm = out[0, 0]; hm.imshow(matrix, cmap="viridis")
out.colorbar(hm, at=(0, 1))
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
out[0, 0].plot(x, y1)
out[0, 1].plot(x, y2)
out[1, 0].plot(x, y3)
out[1, 1].plot(x, y4)
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
| 1. heatmap + colorbar | `hm \| pt.colorbar(hm)` | `pt.layout(1,2,widths=[1,0.05])` + index | **A** — colorbar self-sizes |
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
- **Sizing.** Default equal sizing. `pt.grid(..., widths=[...],
  heights=[...])` for explicit ratios. A future per-chart size hint
  (`pt.chart(width=0.2)`) covers the colorbar-width case without
  forcing every layout to declare ratios up front.

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

2. **Where do guides (legend, colorbar) live?** *Resolved: support both
   panel and decorator forms; treat legend and colorbar uniformly.*

   Guides are data → glyph mappings (legend: discrete; colorbar:
   continuous). They get the same placement options:

   - **Per-chart, inside-frame** — `chart.legend()` overlays the data
     area (today's default). `chart.colorbar(loc="inside")` allowed
     too if someone really wants it; not a special-cased forbid.
   - **Per-chart, in margin** — `chart.legend(loc="outside right")` /
     `chart.colorbar(loc="right")` reserves space in the chart's own
     margin. Same `loc=` machinery for both. Future work; not yet
     built for either.
   - **Layout-level decorator** — `parent.legend()` / `parent.colorbar(hm)`
     attaches a guide to a parent chart, auto-sized in reserved
     margin. Use when the guide "comes with" a sub-assembly:

     ```python
     x = (A | B); x.legend()        # legend attached to x
     y = (C | D); y.colorbar(D)     # colorbar attached to y
     out = x | y                    # each carries its own guide
     ```
   - **Layout-level panel** — `pt.legend()` / `pt.colorbar(hm)` is a
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
   - Default gutter comes from `spec.json` (one number, used for both
     horizontal and vertical gaps). No new API surface; users get a
     sane gutter without thinking.
   - **Coordinated panels auto-collapse to zero gutter.** When
     `b.share_y=a` and `b` is `a`'s horizontal neighbor (or
     `share_x=` + vertical neighbor), the gutter between them goes to
     0. matplotlib makes you write `gridspec_kw={'wspace': 0}`
     manually for this; plotlet's `share_y=` already carries the
     intent, so the spacing follows.
   - Same rule for colorbar adjacent to its source chart: `hm |
     pt.colorbar(hm)` collapses the gutter between them. Generalized:
     "panel reads its data from immediate neighbor → zero gutter."
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

1. **Parent-Chart layout + rect computation.** Single `Chart` class,
   leaf vs. parent flag (or two classes behind one name). Children
   list + layout direction (h / v / grid). `|` / `/` on `Chart`, plus
   `pt.grid([[...]])`. Single-parent invariant + show-on-child raise.
   Default gutter from spec.json; auto-zero-gutter rule for
   coordinated neighbors goes in here too (the rect computer reads
   `share_x` / `share_y` to collapse gutters).
2. **`share_x=` / `share_y=` plumbing on `pt.chart()`** — scale-build
   pre-pass with topo-sort across the parent's child tree.
3. **Legend** — `pt.legend()` panel + `parent.legend()` decorator (sugar
   over panel). Layout-level legend groups by source chart, using
   each chart's `title` as section header; `names=` overrides; opt-out
   via `group_by_chart=False`.
4. **Colorbar** — `pt.colorbar(chart)` panel + `parent.colorbar(chart)`
   decorator. Reads cmap+norm from the referenced chart's imshow.
5. **Cookbook recipes:** `heatmap_with_tree`, ComplexHeatmap-style.

Items 3–5 are independently mergeable once 1–2 are in. The legacy
`pt.figure()` / `pt.Figure` chained API stays as-is — `Chart` is the
surface that gets the subplots treatment; `Figure` remains the
internal plumbing it already is.
