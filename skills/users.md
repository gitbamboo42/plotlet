# plotlet users guide

For AI assistants generating plotlet code. plotlet is a young,
non-mainstream library — its API is not in your training data. This
guide teaches you WHERE to find the answers.

## Mental model

`import plotlet as pt`. A `pt.chart(df, aes(x=..., y=...))` is a
**journal**: artist calls record into a list; `to_svg()` / `show()`
renders. Same journal → byte-identical SVG.

Two rules that won't come from your training data:
- **Artists are called as `add_<name>`** — `c.add_scatter(...)`,
  `c.add_line(...)`, not `c.scatter(...)`. Frame methods (`title`,
  `xlim`, `theme`, …) stay bare.
- **Column mapping goes through `aes(...)`** — `aes(x="col", color="grp")`
  reads from the data; a bare string is always a literal (`color="purple"`
  is the color, not a column). Set `aes` on the chart or per artist.

Chart methods chain. Charts compose with `|` (horizontal), `/`
(vertical), `pt.grid([[...]])`, `.attach_left/right/above/below(...)`,
`.share_x()` / `.share_y()`, `pt.legend()`.

## Where to find examples

**Never assume a signature — read a working example first.**

- [`plotlet-cookbook`](https://github.com/gitbamboo42/plotlet-cookbook) repo —
  worked multi-file recipes (annotated heatmaps, circular / ring plots, ...).
- `tests/test_*.py` — ~150 small self-contained fixtures named
  `def chart_<what>()` / `def diag_<what>()`. Highly grep-friendly:
  `grep -l "keyword" tests/test_*.py`.
- `plotlet-extensions` package — ~45 domain-specific artists (sankey,
  alluvial, raincloud, mosaic, upset_plot, ...) in a separate install
  (`pip install plotlet-extensions`). Each file's top docstring shows
  usage and `import plotlet.extensions.<name>` registers it. (`numeric_bar`,
  `annotation_strip`, `chord_links`, `chord_ribbon` are now core built-ins —
  no import needed.)

Copy the pattern, adapt the data.

## Where to find API details

- `help(c.add_<name>)` / `c.add_<name>?` — plotlet forwards artist docstrings
  through the recorder. Always check before first use; signatures are
  not uniform (e.g. some artists take a matrix positionally).
- `src/plotlet/artists/<name>.py` — core artist source.
- `docs/` — deep dives on subplots, coordinates, themes, extending, SVG schema.

## Debugging: read the figure back, don't re-render and eyeball

plotlet is built so every stage of a figure is machine-readable. When a
plot comes out wrong, **do not fall back to render-a-PNG-and-guess or
matplotlib-style print debugging** — that is slow and blind here. Each
stage below returns structured data in one call; pick the row that
matches the symptom and read the answer directly.

| Symptom | One call | What it answers |
|---|---|---|
| A series is missing / wrong color / `aes` looks ignored | `pt.to_journal(c).to_dict()["entries"]` | What was actually recorded — did the data / mapping land on that artist call? |
| Autoscale clips the data, limits look wrong, `log`/`symlog` did nothing | `pt.to_ir(c).resolve().to_dict()` | What the renderer *decided*: trained scales, baked palette, effective limits and margins |
| "Does the finished plot actually say what I meant?" | parse `data-plotlet-*` out of `c.to_svg()` (snippet below) | Plot type, axis labels, x/y scale, resolved `xlim`/`ylim`, and per-series label, color, range, point count |
| Title / label / legend overlaps or is cut off | `from plotlet.lint import lint` then `lint(c)` | Automated edge-clip + overlap warnings, each naming the region pair; `str(w)` prints it |
| Need the exact box of a chrome element (title, ticks, legend, panel) | `c.regions()` | `{"kind","bbox","name","meta"}` per element, outer-SVG coords; filter by `r["name"]` |
| Panels misaligned, wrong grid, composition off | `pt.layout_diagram(c).show()` | A schematic render of the panel boxes and their nesting |

`lint` is imported from `plotlet.lint` — it is **not** `pt.lint`. The
others (`to_journal`, `to_ir`, `regions`, `layout_diagram`) are on `pt`
or the chart.

Read the SVG's semantic layer back — the "did I plot what I meant?" check:

```python
import re
svg = c.to_svg()
for line in svg.splitlines():
    hits = re.findall(r'data-plotlet-[a-z-]+="[^"]*"', line)
    if hits:
        print(" ".join(hits))
# -> PANEL xlabel=... xlim=... ; ARTIST 0 line label=a color=#1f77b4 n=... x-min=... ...
```

Full attribute schema: [docs/AI_ATTRS.md](../docs/AI_ATTRS.md).

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
