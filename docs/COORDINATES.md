# Coordinate systems

How plotlet maps data coordinates to pixel coordinates, and how to plug a
new mapping in. By default a chart is Cartesian: `(x, y)` in data space
maps linearly to a pixel in the data rectangle. Switching that mapping —
to a ring, a polar disc, a future spiral — is the job of a **coordinate
class**.

```python
c.coordinate(pt.CircularCoordinate(r_inner=0.3))
```

One call swaps the panel's projection. Every artist on that panel then
renders through the new coord.

## The model

- **One coord per panel.** Mixing two spatial mappings in one frame is
  worse than `twinx` — the reader can't parse either axis. For two
  coords, use two panels composed with `pt.grid` / `|` / `/`. Enforced
  at record time.
- **Coords own the chrome.** Cartesian frame chrome (spines, ticks, tick
  labels) doesn't generally make sense under a non-Cartesian map. A
  coord can replace any subset of chrome via optional hooks
  (`draw_frame`, `draw_x_frame`, `draw_x_sector_chrome`, `clip_path_d`);
  the renderer falls back to Cartesian rendering for any hook the coord
  doesn't implement.
- **Artists opt in per coord.** Not every artist renders correctly under
  every coord — e.g. `imshow` (Cartesian-pixel raster) doesn't belong on
  a ring. Each coord lists its supported artists via
  `declare_coord_support`; the renderer raises if you mix a coord with
  an artist not in that list.
- **Both hosting forms are one form.** `c.coordinate(...)` on a bare
  chart and `pt.grid([[c]]).coordinate(...)` produce the same figure:
  lowering wraps a single-chart root in a 1×1 layout and hoists
  `coordinate` / `sectors` (and the title, for container coords like
  `CircularCoordinate`) onto it, so both routes render through the
  coord's layout strategy. A ring's title draws as the layout title
  band above the ring.

## Built-in: `CircularCoordinate`

The only coord shipped in core. Maps `(t, r) → (px, py)` on an annulus:
`t ∈ [0, 1]` runs clockwise from 12 o'clock; `r ∈ [0, 1]` is radial
depth (0 = inner edge, 1 = outer edge). Set `r_inner=0` for a full
polar disc.

```python
c.coordinate(pt.CircularCoordinate(
    data_diameter=None, # outer diameter of the data annulus, px (spec default)
    r_inner=0.3,        # where r=0 lands (fraction of the data radius)
    r_outer=1.0,        # where r=1 lands (use < 1 for nested rings)
    wrap_gap_deg=None,  # angular gap at 12 o'clock; auto-derives
    inner=None,         # optional inner-disc Chart (chord artists)
    start_deg=0,        # t=0 angle (clockwise from 12 o'clock)
    end_deg=360,        # t=1 angle; pair with start_deg for a partial arc
))
```

**Sizing.** `data_diameter` is the circular counterpart of a Cartesian
chart's `data_width`/`data_height`: it sizes the data region itself, and
chrome (tick labels, sector labels, the title band) grows the canvas
outward around it — the set diameter is exactly what renders. Chart-level
`data_width`/`data_height` play no role under this coord. In a multi-ring
pile (`(a / b).coordinate(...)`) the annulus splits into one concentric
band per chart — equal thickness by default, weighted with
`.heights([...])` on the stack (outermost first, dimensionless ratios).

**Partial arc.** `start_deg` and `end_deg` carve out a sub-arc instead of
a closed ring — `start_deg=90, end_deg=360` sweeps 270° from 3 o'clock
clockwise around to 12 o'clock. The open ends get radial cap spines so
the arc reads as a bounded annular sector. Y-tick labels move to the
`t=0` open edge by default (`start_rad`); use `c.yticks(side="right")`
to put them on the `t=1` edge instead — same `side=` kwarg you'd use in
linear, just remapped to the partial arc's geometry. For an arc that
crosses 12 o'clock, use `start_deg=270, end_deg=450`. `wrap_gap_deg`
is ignored when the arc is partial.

**Sectors.** `c.sectors({"A": [...], "B": [...]}, axis="x")` partitions
the ring into Circos-style wedges with radial dividers and tangential
labels. Under a partial arc, sector walls are acyclic — no wrap walls
at the arc's open ends (the cap spines handle the boundary). `axis="y"`
(concentric bands) is not yet supported.

**Inner sub-coord.** Pass `inner=pt.chart(...)` to render a separate
chart into the central disc (`r ∈ [0, r_inner]`). Used to host chord /
link artists that share the t-axis with the rings but live in the
inner disc. Sectors propagate from the layout to the inner chart by
default.

**Chord artists.** Three extension artists are designed for the inner
disc: `chord_links` (pairwise Bezier arcs), `chord_ribbon` (oriented
ribbons), and the `annotation_strip` track for sector labels. They
self-register via `declare_coord_support("Circular", [...])` from their
own modules — `import plotlet.extensions.chord_links` activates the
artist.

**Supported artists.** The authoritative list is the
`declare_coord_support("Circular", [...])` block at the bottom of
[`render/coordinates.py`](../src/plotlet/render/coordinates.py) — most
of the standard vocabulary, including the reference and shape primitives
and `text` / `annotate`. Everything warps through the standard `draw.*`
subdivision: segments become arcs, rects become annular sectors (a bar →
a wedge, a box → an annular box), polygons curve along the ring; point
marks re-anchor but keep their glyph shape. Not supported: 2-D field
marks (`imshow`, `hexbin`, `kde_2d`, `contour`) and the stacked-baseline
`ridge` don't map to a 1-D-over-angle canvas; `dendrogram` awaits its
own radial-tree treatment. Extensions: `numeric_bar`, `chord_links`,
`chord_ribbon`, `annotation_strip` (each activates on import).

**Per-artist coord knobs.** A few artists expose a kwarg that only
matters under a non-Cartesian coord:

| Kwarg | Artist | Effect |
|---|---|---|
| `arc=False` | `c.line(...)` | Connect points with literal Cartesian chords instead of subdividing each edge along the arc. Endpoints still project to their correct angle/ring. No-op under Cartesian. |

The kwarg falls through `**kwargs` into the artist's opts — Cartesian
users never see it.

## The protocol

The required surface is one callable:

```python
class MyCoordinate:
    def __call__(self, artist_dict, iw, ih):
        def project(t, r):       # (t, r) in [0, 1] → pixel (px, py)
            ...
            return px, py
        return project
```

No base class to inherit, just match the protocol. Optional hooks unlock
deeper integration:

| Hook | When it kicks in |
|---|---|
| `svg_transform(project, iw, ih) -> "matrix(...)"` | **Affine** coords only. The core wraps every artist's output in `<g transform="matrix(...)">`, so existing artists draw in Cartesian and the SVG matrix maps the output — zero per-artist changes. No coord in core ships this today. |
| `draw_frame(project, iw, ih, y_ticks_r, y_labels, frame_opts) -> str` | Replaces the Cartesian y-axis rendering (left spine, y ticks, y labels). |
| `draw_x_frame(project, iw, ih, x_ticks_t, x_labels, frame_opts) -> str` | Replaces the Cartesian x-axis rendering. When present, the standard bottom-spine + x-tick block is skipped. |
| `draw_x_sector_chrome(...)` | Replaces the Cartesian x-axis sector chrome (dividers + labels) when `c.sectors(axis="x")` is set. Required if `draw_x_frame` is implemented and sectors are used. |
| `clip_path_d(iw, ih) -> str` | SVG path-data string for the data-area clip region. Defaults to the four-corner polygon (correct for affine coords); `CircularCoordinate` returns an annulus. |
| `render_layout(root) -> (W, H, body)` | Makes the coord a **container coord**: it takes over layout rendering for the whole (sub)tree — `CircularCoordinate` overlays every leaf onto one canvas as concentric r-bands. Its presence drives the IR container flag and the title hoist (see [IR.md](IR.md)); coords without it render each panel in its own layout cell. |

For **non-affine** coords (no `svg_transform`), supporting artists draw
through `ctx.warp` — a Cartesian-pixel → coord-pixel closure passed to
`draw.*` helpers via `project=` — so edges subdivide and primitives
project at draw time. When `svg_transform` is present, `ctx.warp` is
not set and artists draw in Cartesian as usual.

## Opting artists in

Each coord lists the artists that render correctly under it via one
`declare_coord_support` call — typically next to the coord's class
definition.

```python
pt.declare_coord_support("Circular", [
    "scatter", "line",                  # core
    "numeric_bar",                      # extension (activates when imported)
])
```

- The short name is the class name minus the `Coordinate` suffix
  (`"Circular"` for `CircularCoordinate`).
- Declarations are additive — multiple `declare_coord_support` calls
  for the same coord union their artist lists. Extension artists
  self-register from their own modules so the user only pays for what
  they import.
- No name validation at declaration time. Typos and missing artists
  surface at render time via the coord gate error message.

## Adding a new coord

The bare minimum: a class with `__call__`, a `declare_coord_support`
listing supporters, and (if you want users to attach it via
`c.coordinate(...)`) nothing else — `c.coordinate` accepts any object
matching the protocol.

```python
import plotlet as pt

class FlippedCoordinate:
    """Mirror the data area horizontally."""
    def __call__(self, artist, iw, ih):
        def project(t, r):
            return (1 - t) * iw, (1 - r) * ih
        return project

pt.declare_coord_support("Flipped", ["scatter", "line", "bar"])
```

For JSON round-trip, add `_to_dict` / `_from_dict` and register a codec
via `pt.register_coord_codec(...)`.

For the full worked example — frame chrome, sector chrome, clip path,
inner sub-coord, serialization — read
[`render/coordinates.py`](../src/plotlet/render/coordinates.py).
That file is the authoritative reference for the protocol contract; the
table above is a navigation aid.

## See also

- [`plotlet-cookbook/circle/`](https://github.com/gitbamboo42/plotlet-cookbook/tree/main/circle) — circular ring diagram using `CircularCoordinate` + sectors + chord artists.
- [`docs/EXTENDING.md`](EXTENDING.md) — adding custom artists (the other half of the extension story).
- [`docs/SUBPLOTS.md`](SUBPLOTS.md) — composing multi-panel layouts for the "two coords side by side" pattern.
