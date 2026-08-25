# Themes

Two functions style a chart, one mechanism underneath — a deep-merge
over [`spec.json`](../spec.json), the locked default look:

```python
c.spec(font=dict(title_size=15))   # set individual spec values
c.theme("dark")                    # apply a named preset
```

They compose in either order: `spec` values always apply on top of the
preset. `spec` calls accumulate — repeated calls deep-merge, later
wins per key — while `theme` is last-call-wins.

Each `spec` kwarg is a spec section (`figure`, `font`, `frame`,
`grid`, `legend`, …) holding a partial dict of that section's keys —
the same shape as a theme JSON. Unknown sections or keys raise at
record time with a did-you-mean hint. The overrides are recorded on
the chart, so a saved journal stays self-contained — nothing to
re-register before replay.

## What you can set

Any `spec.json` key is overridable — the sections you'll typically
touch:

```jsonc
{
  "figure":   { "background": "..." },
  "font":     { "family": "...", "color": "...",
                "tick_size": ..., "label_size": ..., "title_size": ... },
  "frame":    { "color": "...", "width": ..., "tick_length": ...,
                "tick_direction": "...", "tick_marks": true, "x_side": "...",
                "spine_top": true, /* …one flag per side */ },
  "grid":     { "color": "...", "width": ..., "dasharray": "2,3",
                "default_on": false },
  "defaults": { "linewidth": ..., "markersize": ..., "fill_alpha": ...,
                "refline_color": "...", /* …per-artist visual defaults */ },
  "legend":   { "background": "...", "swatch_width": ..., /* … */ },
  "linestyles": { "--": "6,3", /* …dash specs */ }
}
```

The remaining sections (`size`, `pad`, `sectors`, `layout`) merge the
same way — see the `size.data_width` warning below before touching
geometry. `"dasharray": null` drops the dash (solid gridlines — how
`minimal` gets its look). Unspecified keys fall through to `classic` —
which is just `spec.json` with no overrides. The authoritative key set
and the default values live in
[`src/plotlet/spec.json`](../spec.json).

`font.family` doubles as the face selector: its first comma-separated
segment takes a bundled name or a `.ttf`/`.otf` path (see
[API.md → Fonts](API.md#fonts)) —
`c.spec(font=dict(family="Arimo"))` picks the face, under any preset.

Convention: **the data palette stays orthogonal to theme.** TAB10 and
the named-color shortcuts live in [`src/plotlet/draw/colors.py`](../draw/colors.py)
as plain constants — not in `spec.json`, not theme-overridable. Themes
change frame chrome; the data palette is for users to override at the
chart / call level. Frame-chrome and data-color knobs stay separate so
swapping a theme never changes the data colors.

## Built-in presets

A preset is a named bundle of the same overrides. plotlet ships four:

| theme     | look                                                                |
|-----------|---------------------------------------------------------------------|
| `classic` | white background, black spines on all four sides, no grid (default) |
| `minimal` | white background, no spines, light solid gridlines on by default    |
| `dark`    | dark gray background, light spines, soft grid on by default         |
| `void`    | white background, no spines, no tick marks (tick labels remain — pass `c.xticks([])` / `yticks([])` to drop those too) — for sparklines/insets |

```python
import plotlet as pt
from plotlet import aes

c = pt.chart(df, aes(x="t"), title="hits per minute",
             xlabel="t", ylabel="hits")
c.theme("dark")
c.add_line(aes(y="A"), label="A")
c.add_line(aes(y="B"), label="B")
```

Chaining also works — `theme` and `spec` are frame methods like
`title` / `xlabel`:

```python
c = pt.chart().theme("minimal").title("residuals").add_line(df, aes(x="x", y="resid"))
```

## Whole-figure themes

A theme only affects the chart it's set on; multi-panel layouts may
mix themes per leaf:

```python
a = pt.chart(df, aes(x="t", y="raw"), title="raw")
a.theme("minimal")
a.add_line()
b = pt.chart(df, aes(x="t", y="fit"), title="model")
b.theme("dark")
b.add_line()
fig = a | b
```

To theme a whole figure in one call, set it on the layout:

```python
fig = pt.grid([[a, b], [c, d]])
fig.theme("dark")
```

The layout theme is the *default* for every leaf under it — a leaf's
own `c.theme(...)` wins — and it styles the outer canvas: figure
background, figure title, the space between panels. Nested layouts
cascade the same way (nearest themed ancestor provides a leaf's
default). `layout.spec(...)` sets figure-wide spec values the same
way: every leaf inherits them, and a leaf's own `c.spec(...)`
deep-merges on top (leaf wins per key). The two channels cascade
independently, so a leaf that only tweaks spec values still inherits
the layout's preset.

Without a layout theme, the outer canvas comes from whatever theme is
active at the root render: a root that funnels to a single themed
chart takes that chart's theme; a multi-leaf parent like `a | b`
stays `classic`. The background is painted as a real first-child
`<rect>` (not CSS on the root element), so PNG/PDF exports and
non-browser SVG consumers carry it too.

## Naming your own theme

When the same overrides recur across charts, register them under a
name. As a dict at runtime:

```python
import plotlet as pt
pt.register_theme("paper", dict(
    figure=dict(background="#fafafa"),
    frame=dict(color="#222222", spine_top=False, spine_right=False),
    grid=dict(color="#dddddd", default_on=True),
    font=dict(color="#222222"),
))
c = pt.chart(df, aes(x="x", y="y"))
c.theme("paper")
c.add_line()
```

Or as a JSON file you ship in your project:

```python
pt.register_theme("paper", "themes/paper.json")
```

`pt.list_themes()` lists everything registered, including the
built-ins. One caveat versus inline overrides: a journal that names a
registered theme needs that registration re-run before replay.

> ⚠️ A theme that overrides `size.data_width` / `size.data_height`
> changes the geometry of every chart that doesn't set its own — most
> baselines assume the classic dimensions, so use sparingly.

## How theme application works

`c.theme(...)` and `c.spec(...)` record onto the chart's call list. At
render time, the accumulated spec overrides are deep-merged over the
preset, and the spec dicts (`_FRAME`, `_D`, …) are mutated in place
with the result for the duration of one render, then restored. In
layout rendering each leaf's style is applied independently — themes
don't leak between panels.
