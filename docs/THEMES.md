# Themes

A theme is a per-chart visual preset — background, spines, ticks, grid,
font color. Conceptually the same idea as ggplot2's `theme_classic` /
`theme_minimal` / `theme_dark`. plotlet ships four:

| theme     | look                                                           |
|-----------|----------------------------------------------------------------|
| `classic` | white background, black spines on all four sides, no grid (default) |
| `minimal` | white background, no spines, light dashed gridlines on by default   |
| `dark`    | dark gray background, light spines, soft grid on by default         |
| `void`    | white background, no spines, no ticks — for sparklines/insets       |

## Using a theme

```python
import plotlet as pt

c = pt.chart(theme="dark", title="hits per minute",
             xlabel="t", ylabel="hits", legend=True)
c.line(xs, ys, label="A")
c.line(xs, ys2, label="B")
```

Or chained — `theme` is just a frame method like `title` / `xlabel`:

```python
c = pt.chart().theme("minimal").title("residuals").line(xs, resid)
```

The theme only affects the chart it's set on. Multi-panel layouts may
mix themes per leaf:

```python
a = pt.chart(theme="minimal", title="raw").line(xs, ys)
b = pt.chart(theme="dark",    title="model").line(xs, fits)
fig = a | b
```

The outer SVG background comes from `figure.background` of whatever
theme is active at the root render. For `a | b` (an unthemed parent),
that's `classic` — set a theme on a wrapping chart if you want a
non-default outer canvas.

## What a theme controls

The full set of keys a theme can override:

```jsonc
{
  "figure":   { "background": "#ffffff" },
  "font":     { "family": "...", "color": "#000000",
                "tick_size": 11, "label_size": 12, "title_size": 13 },
  "frame":    { "color": "#000000", "width": 0.8,
                "tick_length": 3.5, "tick_pad": 4,
                "tick_direction": "out",
                "tick_top": false, "tick_right": false,
                "spine_top": true, "spine_right": true,
                "spine_bottom": true, "spine_left": true },
  "grid":     { "color": "#b0b0b0", "width": 0.5,
                "dasharray": "2,3",
                "default_on": false },
  "defaults": { "linewidth": 1.5, "markersize": 4, "scatter_alpha": 0.85,
                "fill_alpha": 0.3, "bar_alpha": 1, "hist_alpha": 1,
                "refline_color": "#000000", "refspan_alpha": 0.2,
                "dendrogram_color": "#1a1a1a", "text_color": "#222222",
                "errorbar_capsize": 4 /* … see src/plotlet/spec.json */ },
  "legend":   { "background": "#ffffff", "opacity": 0.92,
                "swatch_width": 22, "row_height": 16 /* … */ },
  "linestyles": { "-": null, "--": "6,3", ":": "1,3", "-.": "6,3,1,3" },
  "colors":   { "tab10": [ "#1f77b4", "..." ],
                "named": { "blue": "#1f77b4", "k": "#000000", "..." } }
}
```

Any of these can be overridden by a theme. Unspecified keys fall through
to `classic` — which is just `spec.json` with no overrides. The full
default spec lives in [`src/plotlet/spec.json`](../src/plotlet/spec.json).

## Writing your own theme

Two ways. As a dict at runtime:

```python
import plotlet as pt
pt.register_theme("paper", {
    "figure": {"background": "#fafafa"},
    "frame": {"color": "#222222", "spine_top": False, "spine_right": False},
    "grid": {"color": "#dddddd", "default_on": True},
    "font": {"color": "#222222"},
})
c = pt.chart(theme="paper").line(xs, ys)
```

Or as a JSON file you ship in your project:

```python
pt.register_theme("paper", "themes/paper.json")
```

`pt.available_themes()` lists everything registered, including the
built-ins.

## How theme application works

Themes are applied via [`active_theme(name)`](../src/plotlet/_spec.py) —
a context manager that *mutates the inner contents* of the live spec
dicts (`_D`, `_FRAME`, …) for the duration of one render. Every
existing module that imported `_D` / `_FRAME` at startup keeps using
those references; they see the override transparently because we change
contents, not identities.

`Chart.to_svg()` scans `_calls` for the last `theme(...)` and wraps
both replay (so `_replay`'s spine-visibility / tick-direction defaults
pick up the theme) and render under `active_theme`. In layout
rendering, each leaf's theme is applied independently — the swap is
restored before the next leaf renders, so themes don't leak between
panels.

## Limitations

- The outer-SVG background uses whatever theme is active at the root.
  A parent layout (`a | b`) doesn't currently accept a theme; if you
  want a dark figure background outside the panel rectangles, set the
  same theme on every leaf and on the root chart.
- Themes can't currently change `colors.tab10` and `colors.named` (the
  data palette). They affect frame chrome only. Treat palette as
  orthogonal to theme — same way ggplot2 separates `theme_*` from
  `scale_color_*`.
- A theme that resizes via `size.data_width` / `size.data_height` will
  change the geometry of every chart that doesn't pass its own
  `data_width=` / `data_height=`. Be careful — most baselines assume
  the classic dimensions.
