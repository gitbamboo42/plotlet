# plotlet

plotlet is a Python library for reproducible, multi-panel scientific figures. Byte-identical output across machines, a standard plotting vocabulary, and a first-class extension story for custom plot types.

## Documentation

Hands-on tour with executable examples:

- [notebooks/00_introduction.ipynb](notebooks/00_introduction.ipynb) — long-form data, aesthetic inheritance, layering, composition

Reference docs in [`docs/`](docs/):

- [API reference](docs/API.md) — mark methods, frame options, scales, tick overrides
- [Philosophy](docs/PHILOSOPHY.md) — what's in core, what's not, and why
- [Subplots](docs/SUBPLOTS.md) — multi-panel composition, shared scales
- [Extending](docs/EXTENDING.md) — write your own plot type
- [Themes](docs/THEMES.md) — visual presets
- [AI attributes](docs/AI_ATTRS.md) — `data-plotlet-*` schema for automation

Reference plot types beyond the standard vocabulary live in [`src/plotlet/extensions/`](src/plotlet/extensions/) (single-file) and [`cookbook/`](cookbook/) (multi-file projects).

## Dependencies

plotlet supports Python 3.8+ (CI tests 3.9+).

Required: `fonttools`, `scipy` (used by regression, qq, pointplot, dendrogram). numpy / pandas / polars inputs work transparently.

Optional: `cairosvg` for PNG / PDF export.

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
