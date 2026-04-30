# CLAUDE.md

Project memory for **plotlet** — a small, hackable Python library that emits matplotlib-style SVG.

This file gives Claude (or any collaborator) the context needed to be useful from the first message of a new session. Read it before suggesting changes.

---

## What this project is

plotlet is a ~700-line Python library that produces matplotlib-flavored SVG plots. The architecture is a deferred-rendering pipeline: artist methods record into a list, then `show()` walks the list and emits one self-contained SVG string. Output is rendered by the consumer's browser/viewer; plotlet has no rendering engine of its own.

Product positioning — "scaffold, not catalog", why-not-matplotlib, custom plots in user projects — lives in [README.md](README.md) and [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md). This file focuses on *how plotlet is built and changed*.

---

## Core design principles

1. **Few lines, full plot.** A typical plot is ~5 lines: figure, plot call, labels, legend. If something common takes more, the API is wrong.
2. **Deferred rendering.** `plot()`, `xlabel()`, `legend()` only *record* what to draw. `show()` does the actual rendering. This lets the framework compute correct axis limits, lay out legends, and compose new plot types with everything else for free.
3. **matplotlib parity — API and visuals.** Method names, `"C0"`–`"C9"` color shortcuts, `"--"` `":"` linestyle codes, `"o"` `"s"` `"^"` markers all mirror pyplot. Black 0.8 px spines, inward 3.5 px ticks, tab10 cycle, DejaVu Sans, optional dashed grid all mirror matplotlib's default look. If a user knows pyplot, they should be able to guess the call and recognize the output.
4. **Static and reproducible.** No interactivity, no animation, no zoom. Same script → byte-identical SVG → visually identical rendering on every machine. This is what unlocks publication-quality output and baseline-image testing.
5. **Custom plot types are first-class — but they live in user projects.** Adding a new artist is ~50–100 lines following the documented recipe. The core stays small specifically to make this easy. Reference implementations go in [`cookbook/`](cookbook/), not the core.

---

## Architecture

### File layout

```
plotlet/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── src/
│   └── plotlet/
│       ├── __init__.py          # public API
│       ├── _spec.py             # loads spec.json
│       ├── colors.py
│       ├── scales.py            # _LinearScale, _LogScale, _BandScale, nice ticks
│       ├── font.py              # _measure_text, _text_path (DejaVu Sans)
│       ├── artists.py           # plot/scatter/bar/hist/fill_between/imshow + reflines
│       ├── core.py              # Figure class + _render orchestrator
│       ├── chart.py             # Chart facade for tabular data
│       ├── colormaps.py         # 180 vendored matplotlib colormaps (continuous, value→RGB)
│       ├── _cm_data.py          # generated LUT data — do not edit by hand
│       ├── _png.py              # tiny stdlib-only PNG encoder for imshow's large-image path
│       ├── spec.json            # locked visual constants — package data
│       └── fonts/DejaVuSans.ttf # bundled font (~700 KB)
├── cookbook/                    # reference implementations of custom plot types
├── notebooks/
├── tests/
│   ├── baseline_images/         # committed SVG baselines
│   ├── _runner.py               # shared CLI: --update, --gallery, default = check
│   └── test_chart.py            # plot defs for the pt.chart() API
└── docs/
    ├── PHILOSOPHY.md
    └── EXTENDING.md
```

### Running tests / notebooks

Install editable into a Python 3.10+ environment, then run the test scripts:
```bash
pip install -e .
python tests/test_chart.py            # check vs. committed baselines (default)
python tests/test_chart.py --update   # regenerate after intentional visual changes
python tests/test_chart.py --gallery  # build tests/baseline_images/chart/index.html
jupyter nbconvert --to notebook --execute notebooks/01_basics.ipynb --output /tmp/out.ipynb
```

The test runner plumbing lives in `tests/_runner.py`. Machine-specific interpreter paths and env quirks live in `CLAUDE.local.md` (gitignored).

### The deferred-rendering pattern (the heart of the library)

Every artist method records a tuple `(name, args, kwargs)` into `Figure._calls`:

```python
def __getattr__(self, name):
    if name in _RECORDABLE:
        def recorder(*args, **kwargs):
            self._calls.append((name, list(args), dict(kwargs)))
            return self
        return recorder
```

Then `to_svg()` does five phases:

1. **Replay** — walks `_calls` to build a state dict (`artists`, `title`, `xlim`, …).
2. **Domain compute** — for each numeric artist, expand `x_min/x_max/y_min/y_max`. Histograms pre-bin here.
3. **Scale build** — `_LinearScale`, `_LogScale`, `_BandScale` (bar charts). Ticks are computed via the standard 1/2/5 × 10ⁿ "nice numbers" algorithm.
4. **Render artists** — each artist type has a `_artist_<type>(a, x_scale, y_scale, color)` helper in `artists.py` that emits SVG strings.
5. **Frame, ticks, labels, legend** — spines, tick lines, text-as-paths labels, then the legend box.

### Adding a new plot type

The three-step recipe (add to `_RECORDABLE`, extend domain logic in `_render()`, add a draw branch + `_artist_<type>` helper) is plotlet's central hackability claim. **For most custom plots, the right home is your own project (or [`cookbook/`](cookbook/)) — not the core.** Full guide: [docs/EXTENDING.md](docs/EXTENDING.md).

### Text rendering — text-as-paths via fontTools

Instead of emitting `<text>` elements that depend on the consumer's installed fonts, plotlet extracts glyph outlines from the bundled DejaVu Sans (`fonts/DejaVuSans.ttf`) and emits `<path d="…">` elements. This unlocks:

- **Cross-machine reproducibility.** Same SVG renders identically on Linux, macOS, Windows, headless CI.
- **Exact text measurement.** `_measure_text(s, size)` returns the precise pixel width by summing glyph advances. The legend box auto-sizes to fit; no `len(text) * 6.2` magic numbers.
- **Self-contained output.** SVG files don't need fonts on the recipient's machine.

Tradeoff: text in the output isn't selectable / searchable. matplotlib makes the same trade for the same reason.

### Visual spec (`spec.json`)

All visual constants — colors, font sizes, spine widths, default alphas, legend dimensions — live in `src/plotlet/spec.json`. The package reads it at import via `_spec.py`. Changing a value in `spec.json` is the *only* way to alter the locked visual style. Don't reintroduce hard-coded literals in render code.

### State on a Figure

Each `Figure` instance accumulates:

- `_calls` — list of recorded artist + styling calls
- `_width`, `_height`, `_margin` — figure dimensions

The replay function reconstructs `title`, `xlabel`, `ylabel`, `xlim`, `ylim`, `xscale`, `yscale`, `grid`, `legend`, `artists` from `_calls` each render. Stateless rendering = same output every time.

---

## Conventions for collaboration

**Dependencies.** plotlet depends on Python 3.10+ and `fonttools` (parses the bundled DejaVu Sans). numpy / pandas / polars inputs are accepted because `_to_pylist` calls `.tolist()` defensively, but the implementation doesn't currently need them. Add deps when they earn their keep — don't avoid them on principle.

When suggesting changes or adding features:

- **Decide core vs cookbook first.** Cookbook is the default for new plot types; core is only for shared infrastructure (this is how `imshow` got in — it carries the colormap registry and the PNG encoder, both reusable) or genuine essentials.
- **Refuse new core plot types by default.** "Let's add a Sankey to the core" is almost always wrong; the right answer is `cookbook/<name>.py` or the user's own project.
- **Match existing code style.** Plain Python, top-to-bottom readable, no clever metaclasses or classes-everywhere.
- **Preserve matplotlib API parity** for standard plots. If matplotlib calls it `axhline`, don't call it `horizontalLine`.
- **No premature abstraction.** Three is the threshold — leave duplicated code alone until there's a third use site.
- **Visual constants live in `spec.json`.** If you find yourself typing a number into render code, ask whether it should be there instead.
- **Test with baselines.** Core changes get added to `tests/test_chart.py` with a committed SVG; cookbook examples are reference, not regression-tested.
- **Mention matplotlib quirks that aren't replicated** and why, when relevant.

The actual mechanics of adding an artist (`_RECORDABLE`, replay, domain, draw + `_artist_<type>`) are in [docs/EXTENDING.md](docs/EXTENDING.md).

---

## Non-goals

User-facing non-goals (no interactivity, no 3D, no production dashboard, not a matplotlib competitor for standard plots) are listed in [README.md](README.md). Contributor-only reminders:

- **Interactivity is out forever, not deferred.** Hover, zoom, pan, click, animation are *not* "maybe later" — they kill the byte-identical reproducibility that makes baseline-image testing possible. Don't soften this in code review.
- **Not aiming for 100% matplotlib coverage.** Just the parts the author actually uses, plus whatever shared infrastructure is forced by core artists. Reject "we should add this for parity" arguments.
