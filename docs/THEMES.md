# Themes

A theme is a per-chart visual preset — background, spines, ticks, grid,
font color. plotlet ships four:

| theme     | look                                                                |
|-----------|---------------------------------------------------------------------|
| `classic` | white background, black spines on all four sides, no grid (default) |
| `minimal` | white background, no spines, light dashed gridlines on by default   |
| `dark`    | dark gray background, light spines, soft grid on by default         |
| `void`    | white background, no spines, no ticks — for sparklines/insets       |

## Using a theme

```python
import plotlet as pt

c = pt.chart(theme="dark", title="hits per minute",
             xlabel="t", ylabel="hits", legend=True)
c.line(data=df, x="t", y="A", label="A")
c.line(data=df, x="t", y="B", label="B")
```

Or chained — `theme` is just a frame method like `title` / `xlabel`:

```python
c = pt.chart().theme("minimal").title("residuals").line(data=df, x="x", y="resid")
```

The theme only affects the chart it's set on. Multi-panel layouts may
mix themes per leaf:

```python
a = pt.chart(theme="minimal", title="raw").line(xs, ys)
b = pt.chart(theme="dark",    title="model").line(xs, fits)
fig = a | b
```

The outer SVG background comes from whatever theme is active at the
root render. For an unthemed parent like `a | b`, that's `classic` — set
a theme on a wrapping chart if you want a non-default outer canvas. The
background is painted as a real first-child `<rect>` (not CSS on the
root element), so PNG/PDF exports and non-browser SVG consumers carry
it too.

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
                "x_side": "bottom", "y_side": "left",
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
  "linestyles": { "-": null, "--": "6,3", ":": "1,3", "-.": "6,3,1,3" }
}
```

Any of these can be overridden by a theme. Unspecified keys fall through
to `classic` — which is just `spec.json` with no overrides. The full
default spec lives in [`src/plotlet/spec.json`](../src/plotlet/spec.json).

Convention: **the data palette stays orthogonal to theme.** TAB10 and
the named-color shortcuts live in [`src/plotlet/draw/colors.py`](../src/plotlet/draw/colors.py)
as plain constants — not in `spec.json`, not theme-overridable. Themes
change frame chrome; the data palette is for users to override at the
chart / call level. Frame-chrome and data-color knobs stay separate so
swapping a theme never changes the data colors.

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

> ⚠️ A theme that overrides `size.data_width` / `size.data_height`
> changes the geometry of every chart that doesn't set its own — most
> baselines assume the classic dimensions, so use sparingly.

## How theme application works

`c.theme(name)` records the theme onto the chart's call list. At render
time, the spec dicts (`_FRAME`, `_D`, …) are mutated in place with the
theme's overrides for the duration of one render, then restored. In
layout rendering each leaf's theme is applied independently — themes
don't leak between panels.
