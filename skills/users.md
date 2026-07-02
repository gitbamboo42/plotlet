# plotlet users guide

For AI assistants generating plotlet code. plotlet is a young,
non-mainstream library — its API is not in your training data. This
guide teaches you WHERE to find the answers.

## Mental model

`import plotlet as pt`. A `pt.chart()` is a **journal**: methods record
into a list; `to_svg()` / `show()` renders. Same journal → byte-identical
SVG.

Chart methods chain. Charts compose with `|` (horizontal), `/`
(vertical), `pt.grid([[...]])`, `.attach_left/right/above/below(...)`,
`.share_x()` / `.share_y()`, `pt.legend()`.

## Where to find examples

**Never assume a signature — read a working example first.**

- `cookbook/*/` — worked multi-file recipes (annotated heatmaps,
  circular / genomic plots, ...).
- `tests/test_*.py` — ~150 small self-contained fixtures named
  `def chart_<what>()` / `def diag_<what>()`. Highly grep-friendly:
  `grep -l "keyword" tests/test_*.py cookbook/*/*.py`.
- `src/plotlet/extensions/*.py` — ~50 domain-specific artists (volcano,
  manhattan, sankey, upset_plot, km_curve, ...). Each file's top
  docstring shows usage. `import plotlet.extensions.<name>` registers it.

Copy the pattern, adapt the data.

## Where to find API details

- `help(c.<method>)` / `c.<method>?` — plotlet forwards artist docstrings
  through the recorder. Always check before first use; signatures are
  not uniform (e.g. some artists take a matrix positionally).
- `src/plotlet/artists/<name>.py` — core artist source.
- `docs/` — deep dives on subplots, coordinates, themes, extending, SVG schema.

## Constraints (won't change)

- No interactivity (hover, zoom, pan, click, animation).
- No twin y-axes. Use `|` or `/` for a second panel.
- No global state. Themes are per-chart: `c.theme("dark")`.
- One coordinate system per panel.
- Not a matplotlib port. No `plt.subplots`, no `ax.set_xlim`, no
  `tight_layout`. Compose with `|` `/` `pt.grid`.

## Deep dives

- Subplots, shared scales, attachments → [docs/SUBPLOTS.md](../docs/SUBPLOTS.md)
- Coordinates → [docs/COORDINATES.md](../docs/COORDINATES.md)
- Themes → [docs/THEMES.md](../docs/THEMES.md)
- Writing new artists → [docs/EXTENDING.md](../docs/EXTENDING.md)
- SVG output schema → [docs/AI_ATTRS.md](../docs/AI_ATTRS.md)
