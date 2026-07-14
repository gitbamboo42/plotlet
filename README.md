# plotlet

plotlet is a Python library for reproducible, multi-panel scientific figures. Byte-identical output across machines, a standard plotting vocabulary, built-in Cartesian and circular coordinate systems, and an easy way to add your own plot types.

## Documentation

Hands-on tour with executable examples:

- [notebooks/00_introduction.ipynb](notebooks/00_introduction.ipynb) — long-form data, aesthetic inheritance, layering, composition (more topic notebooks in [`notebooks/`](notebooks/))

Reference docs in [`docs/`](docs/):

- [API reference](docs/API.md) — mark methods, frame options, scales, tick overrides
- [Philosophy](docs/PHILOSOPHY.md) — what's in core, what's not, and why
- [Subplots](docs/SUBPLOTS.md) — multi-panel composition, shared scales
- [Coordinates](docs/COORDINATES.md) — Circular, custom non-Cartesian projections
- [Extending](docs/EXTENDING.md) — write your own plot type
- [Themes](docs/THEMES.md) — visual presets
- [AI attributes](docs/AI_ATTRS.md) — `data-plotlet-*` schema for automation

Reference plot types beyond the standard vocabulary ship in the separate [`plotlet-extensions`](https://github.com/gitbamboo42/plotlet-extensions) package (single-file artists — sankey, alluvial, raincloud, upset_plot, …; `pip install plotlet-extensions`, then `import plotlet.extensions.<name>`) and in the [`plotlet-cookbook`](https://github.com/gitbamboo42/plotlet-cookbook) repo (multi-file, domain-specific projects). A few extensions the core tests depend on still ship in core under [`src/plotlet/extensions/`](src/plotlet/extensions/).

## For AI assistants

Compact, vendor-neutral onboarding docs live in [`skills/`](skills/):

- [`skills/users.md`](skills/users.md) — for AI tools generating plotlet code on a user's behalf.
- [`skills/developers.md`](skills/developers.md) — for AI (or human) contributors working on plotlet itself. Symlink as `CLAUDE.md` / `.cursorrules` / `AGENTS.md` as your tool expects.

## Dependencies

plotlet supports Python 3.10+.

Required: `fonttools`, `scipy` (regression, qq, CI error bands, clustering/dendrogram), `resvg_py` (PNG rendering — prebuilt wheels, no system libraries). numpy / pandas / polars inputs work transparently.

Optional: `cairosvg` for PDF export (`pip install plotlet[pdf]`).

## Installation

```bash
pip install plotlet
```

## Testing

```bash
pip install -e ".[test]"
pytest tests/                  # check vs. committed baselines
pytest tests/ --update         # regenerate (review the diff!)
```

## Development

Development takes place on GitHub. Please submit bugs to the issue tracker with a reproducible example.

## License

MIT
