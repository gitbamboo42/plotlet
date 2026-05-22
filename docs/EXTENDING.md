# Extending plotlet

Adding a custom plot type is a 3-step recipe: write three small functions,
bundle them into an `ArtistSpec`, hand it to `add_artist(...)`. After that,
`c.<your_name>(...)` Just Works on any `Chart` — autoscaling, gridlines,
color cycling, and the legend integrate for free. No edits to `core.py`,
no monkey-patching. Custom artists live in your project, or in
[`src/plotlet/extensions/`](../src/plotlet/extensions/) as reference.

---

## The three steps

```python
import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import segment, circle


# 1. record(args, kwargs) -> dict
#    Turn c.<name>(...) args into the artist dict stored in Chart._calls.
#    Pure data — no scales yet.
def my_record(args, kw):
    return {"type": "lollipop",
            "xs": to_list(args[0]),
            "ys": to_list(args[1]),
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
c.lollipop([1, 2, 3, 4, 5], [3, 7, 2, 9, 4], label="A")
c.title("Lollipop chart").grid(True).legend(True).save_svg("out.svg")
```

Worked example: [`src/plotlet/extensions/lollipop.py`](../src/plotlet/extensions/lollipop.py) — basic
artist plus an optional `legend_entries` so the legend entry looks like a
tiny lollipop. Every extension under [`src/plotlet/extensions/`](../src/plotlet/extensions/)
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
| `text_path(s, x, y, size, anchor, color)` | Text as glyph paths (font-independent across machines). |

`dash=` accepts matplotlib codes (`"--"`, `":"`, `"-."`) or a raw SVG
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
    layer: "background" | "data" | "foreground" = "data",
    uses_color_cycle: bool = True,
    default_color: str | None = None,
    legend_entries: (a) -> list[dict] | None = None,
    legend_gradient: (a) -> dict | None = None,
    data_attrs: (a) -> dict | None = None,
    axis_order: (a) -> dict | None = None,
    frame_defaults: (args, kwargs) -> list[tuple] | None = None,
)
```

| Field | When you need it |
|---|---|
| `xdomain` / `ydomain` | Your artist's data should drive axis limits. Return `None` for decorative artists (axhline, axvline). |
| `layer` | `"background"` for fills (drawn first), `"foreground"` for reference lines (drawn last). Default `"data"`. |
| `uses_color_cycle` | Set `False` for artists that pick their own color (reflines, image artists). Set `default_color` for the fallback. |
| `legend_entries` | Return the legend entries this artist contributes (zero or more). Each entry is a `{"label": str, "color": str, "paint": callable}` dict where `paint(a, ctx, x0, y_mid) -> svg_fragment` draws the swatch. Most one-series-per-call artists return zero or one entry depending on whether `label=` was set. |
| `legend_gradient` | For artists with a continuous color mapping. Returns `{"kind": "continuous", "cmap": ..., "vmin": ..., "vmax": ...}`. |
| `data_attrs` | AI-readable type-specific attrs. Keys land on the artist's `<g>` as `data-plotlet-<key>`. Common attrs (type, index, label, color) are automatic — see [`AI_ATTRS.md`](AI_ATTRS.md). |
| `axis_order` | Contribute a canonical order for a categorical axis. Returns `{"x": [...]}` / `{"y": [...]}`. Use when ordering is load-bearing (dendrogram leaves). User's explicit `xscale("category", order=...)` still wins. |
| `frame_defaults` | Return a list of `(call_name, args, kwargs)` recorded *before* your artist. Use for strong defaults (e.g. dendrogram hides all spines). User calls *after* `c.<your_artist>()` still win. |

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
stash pre-processed data in [`builtin_artists.py`](../src/plotlet/builtin_artists.py).

Respect deferred rendering: `record` runs early, `draw` runs at `to_svg()`
time. Don't compute scales or colors in `record` — they don't exist yet.
