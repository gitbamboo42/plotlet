# Architecture — the render pipeline

plotlet works like a small compiler: what you type is *recorded*, then
progressively *lowered* into the final image. Every figure renders
through the same four representations (the middle two are IRs —
"intermediate representations", the compiler term), ordered by
distance from the user:

    journal     "what the user did"    record/journal.py
    FigureIR    "what the figure is"   record/figure_ir.py
    ResolvedIR  "what was decided"     render/resolved_ir.py
    SVG         the rendered plot      render/emit.py

`Chart.to_svg()` itself goes journal → IR → resolved IR → SVG; there
is no other render path, so each stage provably carries everything the
next one consumes.

- **journal** — the recorder's event log; `Chart` methods append, never
  execute. Owned by the recording half (`record/journal.py`,
  `record/chart.py`);
  the replay model is described in
  [PHILOSOPHY.md](PHILOSOPHY.md#the-replay-model).
- **FigureIR** — the journal compiled to a per-node table, loss-free
  and round-trippable, still in user terms (ops, data columns, palette
  names). **The one contract between the two halves — the rest of this
  file specifies it.**
- **ResolvedIR** — the render plan after resolution: replayed states,
  trained scales, measured margins, baked colors. One-way, unversioned,
  in-process by design; it lives entirely inside the render half and is
  documented where it's defined (`render/resolved_ir.py`).
- **SVG** — written by the emit pass, which only transcribes decisions
  already in the ResolvedIR (pinned: emit never re-resolves).

## The FigureIR contract

The specified boundary between plotlet's two halves. The **recording
half** (the `record/` package: `chart.py`, `facet.py`, `legend.py`,
`journal.py`, `figure_ir.py`)
turns user actions into a `FigureIR`; the **render half** (the
`render/` package) turns a `FigureIR` into an SVG and never imports the
recording half. Everything below is contract: the render half may
assume it, and anything producing IRs — the recorder, a JSON loader, a
programmatic transform — must guarantee it. `render.validate` enforces
it at every render entry; `tests/test_import_boundary.py` enforces the
import boundary itself. Lowering is loss-free both ways (`ir_to_journal ∘
journal_to_ir` replays to a byte-identical SVG). A `FacetGrid` is
recording-side sugar: it journals as one `new_facet_grid` event for
provenance, and `journal_to_ir` expands it to the grid of charts it
denotes — the IR and everything downstream see only the four node
kinds below.

### Shape

```python
FigureIR(nodes=[IRNode, ...], root_nid=<int>)
IRNode(nid, kind, init, ops, insets)
```

- `nid` — opaque int, unique within the table; the journal's node id.
- `kind` — `"chart" | "legend" | "diagram" | "layout"`.
- `init` — construction kwargs (below).
- `ops` — `[{"op": <name>, "args": [...], "kwargs": {...}}, ...]` in
  original per-node order.
- `insets` — `[{"rect": [x, y, w, h], "chart_nid": <nid>}, ...]`
  (fractional rect in the host's data area). Insets live on leaf
  nodes — never on a layout — and `chart_nid` must name a chart node.

**Dependency order.** `nodes` is ordered so that every nid a node
references — layout children, legend sources, inset charts, `$node`
envelopes anywhere in init/op values — appears **earlier** in the list.
Hydration is a single forward pass. The order is the depth-first walk
from the root, so two IRs of the same figure list nodes identically.

### Node kinds and init keys

**`chart`** — data leaf. All keys optional; missing keys take spec
defaults. `data_width`, `data_height` (px or unit strings; unread under
a container coord, which sizes from its own geometry — e.g.
`CircularCoordinate.data_diameter`), `margin` (dict with
`left/right/top/bottom`), plus recorder-only state the render half
ignores: `data` and chart-level aes (`x`, `y`, `color`, `palette`, ...)
— those are already baked into the ops at record time.

**`legend`** — standalone legend leaf. Required: `canvas_width`,
`canvas_height` (the canvas is the dimensional primitive; data dims are
zero). Optional: `margin`, `legend_sources` (list of nids — positional
reference form; each must name a leaf node, not a layout),
`legend_names_pairs` (pairs, not a dict — keys may be `$node`
envelopes), `legend_group_by_chart`, `legend_valign`, `legend_ncols`,
`legend_user_width`, `legend_user_height`, `legend_gap`.

**`diagram`** — pre-rendered SVG leaf. Required: `canvas_width`,
`canvas_height`. Optional: `margin`, `diagram_inner` (the SVG body).

**`layout`** — composition node. Required: `layout_kind`
(`"h" | "v" | "grid"`) and `children` (non-empty list of nids, `None`
for grid holes). Grids additionally require integer `grid_rows` /
`grid_cols` with `rows * cols == len(children)`.

### Ops are normalized calls

An op is one recorded method call, **post**-normalization: chart-level
aes and data injection already applied, `data=` normalized to the
canonical table form — and **pre**-`spec.record`: the artist's `record()`
runs at replay, not before. Artist `frame_defaults` are never present;
they regenerate inside `_replay` on every render.

Op names are interpreted per kind:

- chart-family nodes (`chart`, `legend`, `diagram`): a registered
  artist, a frame method (`title`, `xlim`, `xscale`, `xticks`,
  `spines`, `grid`, `legend`, `clip`, `facecolor`, `coordinate`,
  `sectors`, `theme`, ... — `_FRAME_OPS` in `render/_resolution.py` is the
  authoritative set), or `attach_left/right/above/below`.
- `layout` nodes: `share_x`, `share_y`, `align_x`, `align_y`, `gap`,
  `coordinate`, `sectors`, `title`, `heights` (`_LAYOUT_MATERIALIZED` ∪
  `_LAYOUT_PASSTHROUGH` in `render/_nodes.py`).

**Interpretation is registry-relative.** The IR stores names, not
implementations: an IR referencing an extension artist or a custom
coord is valid only in a process that has imported the module
registering it. That's the same rule as rendering — determinism is
"same input **and same registry** → same SVG".

**The root is always a layout.** `journal_to_ir` wraps a lone leaf
(chart / legend / diagram) in a 1×1 `"h"` layout, so every IR presents
one root shape and `validate` rejects hand-built IRs with a leaf root.
A chart root's composition-level ops hoist onto the wrapper: `sectors`
always; a container-strategy `coordinate` (one whose coord class
implements `render_layout`) additionally hoists `coordinate` and
`title`, since the overlay path draws no leaf chrome. Composition-level
state therefore never sits on a chart at the root position. Only the
root wraps: charts inside layouts already have a layout home for
composition state, and grid cells are charts by API contract. The hoist
decision reads the `container` flag on the `$coord` envelope (stamped by
`to_journal` from the live class), so op placement is a function of the
blob alone — `validate` cross-checks the flag against the registered
class and rejects a mismatch.

### Value envelopes

Three envelopes, shared verbatim with the journal, may appear anywhere
in init or op values; `_decode` (`_json_layer.py`) resolves them at
hydration:

    {"$node": <nid>}                     cross-node reference (attachments,
                                         coord inners, legend name keys)
    {"$coord": <class name>,             coord instance, via the coord
     "container": <bool>, "kwargs"}     registry (`register_coord_codec`);
                                         `container` = class defines
                                         `render_layout`, required
    {"$sectors": {...}}                  Sectors value

A dict containing the key `$node` must be exactly that single-key form.
In the JSON form (`to_dict` / `from_dict`), non-JSON-native values
(tuples, sets, dates/datetimes, DataFrames, non-string-keyed dicts)
are additionally wrapped by `_json_layer` envelopes (`$tuple`, `$set`,
`$date`, `$datetime`, `$dataframe`, `$dict_pairs`); those decode at
`from_dict` time, before the IR contract applies.

### Version discipline

The in-memory `FigureIR` carries no version; the JSON form does
(`"version": 1`), checked in `FigureIR.from_dict`. Pre-release the
version stays `1` and there is no migration story — a breaking IR
change bumps the number and old blobs fail loudly.

## Working with IRs

```python
ir = pt.to_ir(fig)          # Chart / Layout / FacetGrid / journal → IR
ir.validate()               # contract check without rendering
ir.to_svg()                 # render (validates implicitly)
ir.resolve()                # resolved IR — the render path's middle
                            # stage; .root inspects, .to_svg() emits
blob = ir.to_dict()         # JSON-safe; pt.from_ir(blob) inverts
```

The render half's full seam (`render/__init__.py`): `render_svg`,
`regions`, `natural_size`, `data_total_size`, `resolve`, `validate`,
plus `hydrate(ir)` / `materialize(tree)` for tools that walk or measure
the render tree — every function takes a `FigureIR` (`materialize` the
tree `hydrate` returns). Violations raise
`ValueError("invalid FigureIR: ...")` naming the offending node and
rule.
