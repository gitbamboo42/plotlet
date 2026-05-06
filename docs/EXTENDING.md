# Extending plotlet

Adding a custom plot type is a 3-step recipe. You write three small functions,
bundle them into an `ArtistSpec`, and hand it to `add_artist(...)`. After
that, `fig.<your_name>(...)` Just Works — autoscaling, gridlines, color
cycling, and the legend integrate for free.

No edits to `core.py`. No monkey-patching `Figure`. Custom artists live in
your project (or in [`cookbook/`](../cookbook/) as reference), not upstream.

> If your custom plot is generally useful, **publish it from your own project**;
> see [`PHILOSOPHY.md`](PHILOSOPHY.md) for why we don't accept new plot types
> into the core.

---

## The three steps

```python
import plotlet as pt
from plotlet.artists import _to_pylist


# 1. record(args, kwargs) -> dict
#    Turn the positional/keyword args from fig.<name>(...) into the artist
#    dict that gets stored in Figure._calls. Pure data — no scales yet.
def my_record(args, kw):
    return {"type": "lollipop",
            "xs": _to_pylist(args[0]),
            "ys": _to_pylist(args[1]),
            "opts": kw}


# 2. xdomain(a) / ydomain(a) -> Iterable[float] | None
#    Yield every value that should participate in axis autoscaling. Return
#    None if your artist doesn't constrain that axis (e.g. axhline ignores x).
def my_xdomain(a): return a["xs"]
def my_ydomain(a): return list(a["ys"]) + [0]   # always include 0 for stems


# 3. draw(a, ctx) -> str
#    Emit the SVG fragment for this artist. ctx carries everything you need:
#      ctx.x_scale, ctx.y_scale     callables: data value -> pixel
#      ctx.iw, ctx.ih               inner figure width / height (px)
#      ctx.color                    the assigned color (None for non-cycling)
#      ctx.defaults                 the spec.json defaults dict
#      ctx.dash                     linestyle -> SVG dasharray map
def my_draw(a, ctx):
    out = []
    y0 = ctx.y_scale(0)
    for x, y in zip(a["xs"], a["ys"]):
        px, py = ctx.x_scale(x), ctx.y_scale(y)
        out.append(
            f'<line x1="{px:.2f}" x2="{px:.2f}" y1="{y0:.2f}" y2="{py:.2f}" '
            f'stroke="{ctx.color}" stroke-width="1.5"/>'
            f'<circle cx="{px:.2f}" cy="{py:.2f}" r="5" fill="{ctx.color}"/>'
        )
    return "".join(out)


# Register it. After this line, every Figure has a .lollipop() method.
pt.add_artist(pt.ArtistSpec(
    name="lollipop",
    record=my_record,
    xdomain=my_xdomain,
    ydomain=my_ydomain,
    draw=my_draw,
))


# Use it.
fig = pt.figure()
fig.lollipop([1, 2, 3, 4, 5], [3, 7, 2, 9, 4], label="A")
fig.title("Lollipop chart").grid(True).legend(True)
fig.save_svg("out.svg")
```

Worked example: [`cookbook/lollipop/lollipop.py`](../cookbook/lollipop/lollipop.py) — basic
artist plus an optional `legend_swatch` so the legend entry actually
looks like a tiny lollipop.

---

## ArtistSpec fields

```python
ArtistSpec(
    name: str,
    record: (args, kwargs) -> dict,           # required
    draw: (artist_dict, ctx) -> str,          # required, returns SVG fragment
    xdomain: (artist_dict) -> Iterable | None  = lambda a: None,
    ydomain: (artist_dict) -> Iterable | None  = lambda a: None,
    layer: "background" | "data" | "foreground" = "data",
    uses_color_cycle: bool = True,
    default_color: str | None = None,         # used when uses_color_cycle=False
    legend_swatch: (a, ctx, x0, y_mid) -> str | None = None,
    legend_gradient: (a) -> dict | None = None,
    data_attrs: (a) -> dict | None = None,
)
```

| Field | Default | When you need it |
|---|---|---|
| `xdomain` / `ydomain` | `None` | Set when your artist's data should drive axis limits. Return `None` for decorative artists that just sit on the frame (axhline, axvline). |
| `layer` | `"data"` | `"background"` for fills and shaded spans (drawn first), `"foreground"` for reference lines (drawn last, on top). Same artist within a layer keeps insertion order. |
| `uses_color_cycle` | `True` | Set `False` for artists that shouldn't consume a tab10 slot — reflines, image-based artists, anything that picks its own color. Set `default_color` to give it a fallback. |
| `legend_swatch` | `None` | Provide to draw your own legend entry. Without it, the legend falls back to a colored line in the artist's color. Signature: `(a, ctx, x0, y_mid) -> svg_fragment`. |
| `legend_gradient` | `None` | Provide for artists with a continuous color mapping (heatmap-style). Returns `{"kind": "continuous", "cmap": ..., "vmin": ..., "vmax": ...}` so the layout-level legend can render a colorbar. |
| `data_attrs` | `None` | AI-readable structural attrs. Returned dict keys land on the artist's `<g>` as `data-plotlet-<key>`. Common attrs (type, index, label, color) are added automatically without this field — declare it if you want type-specific attrs (`n`, ranges, marker, …). See [`AI_ATTRS.md`](AI_ATTRS.md). |

---

## RenderContext reference

`RenderContext` is the second argument to `draw` and to `legend_swatch`. It
bundles every piece of render state an artist might need so the call sites
stay short:

| Field | Type | Notes |
|---|---|---|
| `x_scale`, `y_scale` | callable | `scale(value) -> pixel`. On a categorical axis (bar, or `xscale="category"`/`yscale="category"`) the scale is a `_CategoryScale` returning the band *center*, with `.bandwidth` available — bars subtract `bandwidth/2` for the rect's left edge. |
| `iw`, `ih` | float | Inner figure width and height in pixels (after margins). |
| `color` | `str \| None` | The resolved color for this artist. `None` if `uses_color_cycle=False` *and* no `default_color` was set (e.g. `imshow`, which uses a colormap). |
| `defaults` | dict | The `spec.json` defaults — `linewidth`, `markersize`, `scatter_s`, `refspan_alpha`, etc. Use these instead of hardcoded numbers. |
| `dash` | dict | Linestyle codes (`"--"`, `":"`, `"-."`) → SVG `stroke-dasharray` strings. |

---

## What goes in the artist dict

Whatever you return from `record(args, kwargs)` ends up in `Figure._calls`
and is passed to `xdomain`, `ydomain`, and `draw` as `a`. Two conventions:

- **Always set `"type"` to your artist name.** The render layer uses it for
  the registry lookup and a couple of small special-cases (`force_zero`
  for bar/hist y-axes, histogram pre-binning).
- **Always set `"opts"` to the kwargs dict.** Color resolution, label
  collection (for the legend), `linestyle`, `linewidth`, `alpha`, `marker`,
  and the rest of plotlet's matplotlib-flavored kwargs all live there.

Keys starting with `_` (e.g. `_bins`, `_data`, `_color`) are conventionally
"computed during render, used during draw" — see how `imshow` and `hist`
stash pre-processed data in [`builtin_artists.py`](../src/plotlet/builtin_artists.py).

---

## Things to keep in mind

- **Reuse the visual spec.** Don't hardcode colors, font sizes, alphas.
  Pull from `ctx.defaults` (or import `_D` from `plotlet._spec`) so your
  artist matches the locked plotlet look.
- **Respect deferred rendering.** `record` runs early; `draw` runs at
  `to_svg()` time. Don't compute scales or colors in `record` — they don't
  exist yet.
- **No interactivity.** No event handlers, no `<script>`, no animation.
  Static SVG is what makes plotlet's baseline-image testing possible — see
  the non-goals section in [`PHILOSOPHY.md`](PHILOSOPHY.md).
- **Custom plot types don't get added to `core.py`.** Live in your project,
  or send a recipe to [`cookbook/`](../cookbook/) as a reference for others.
