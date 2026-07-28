# plotlet

plotlet is a Python library for reproducible, multi-panel scientific figures, built for AI authorship: figures are written, inspected, and verified as data, not pixels. Byte-identical output across machines, a standard plotting vocabulary, built-in Cartesian and circular coordinate systems, and an easy way to add your own plot types.

## Documentation

Online documentation is available at [gitbamboo42.github.io/plotlet](https://gitbamboo42.github.io/plotlet/).

The docs include a [tutorial](https://gitbamboo42.github.io/plotlet/tutorial.html), a [plot-type reference](https://gitbamboo42.github.io/plotlet/reference.html), a [cookbook](https://gitbamboo42.github.io/plotlet/cookbook.html), an [extensions gallery](https://gitbamboo42.github.io/plotlet/extensions.html), [deep-dive guides](https://gitbamboo42.github.io/plotlet/docs-api.html), and a [page for AI agents](https://gitbamboo42.github.io/plotlet/agents.html).

## Dependencies

plotlet supports Python 3.10+.

Required: `fonttools`, `scipy`, `resvg_py`. numpy / pandas / polars inputs work transparently.

Optional: `cairosvg` for PDF export (`pip install plotlet[pdf]`).

## Installation

```bash
pip install plotlet
```

## For AI assistants

Tell your assistant to run plotlet's `skill()` and follow it. The guides, docs, and worked examples ship inside the installed package; the [page for AI agents](https://gitbamboo42.github.io/plotlet/agents.html) shows the full workflow.

## Development

Development takes place on GitHub. Please submit bugs to the issue tracker with a reproducible example.

## License

MIT
