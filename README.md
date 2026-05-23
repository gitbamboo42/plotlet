# plotlet

plotlet is a Python library for SVG plots. It provides reproducible, byte-identical multi-panel scientific figures with a standard plotting vocabulary and a first-class extension story for custom plot types.

## Documentation

Hands-on tour with executable examples:

- [notebooks/01_basics.ipynb](notebooks/01_basics.ipynb) — line, scatter, bar, hist, fill_between, reference lines, heatmap
- [notebooks/02_subplots.ipynb](notebooks/02_subplots.ipynb) — multi-panel composition and shared scales

Reference docs in [`docs/`](docs/):

- [API reference](docs/API.md) — mark methods, frame options, scales, tick overrides
- [Philosophy](docs/PHILOSOPHY.md) — what's in core, what's not, and why
- [Subplots](docs/SUBPLOTS.md) — multi-panel composition, shared scales
- [Extending](docs/EXTENDING.md) — write your own plot type
- [Themes](docs/THEMES.md) — visual presets
- [AI attributes](docs/AI_ATTRS.md) — `data-plotlet-*` schema for automation

Reference plot types beyond the standard vocabulary live in [`src/plotlet/extensions/`](src/plotlet/extensions/) (single-file) and [`cookbook/`](cookbook/) (multi-file projects).

## Dependencies

plotlet supports Python 3.10+.

Required: `fonttools`. numpy / pandas / polars inputs work transparently.

Optional: `cairosvg` for PNG / PDF export; `scipy` for a few statistical artists (regression, qq, pointplot).

## Installation

```bash
pip install plotlet
```

## Testing

```bash
python tests/test_chart.py            # check vs. committed baselines
python tests/test_chart.py --update   # regenerate (review the diff!)
python tests/test_subplots.py
python tests/test_themes.py
```

## Development

Development takes place on GitHub. Please submit bugs to the issue tracker with a reproducible example.

## License

MIT
