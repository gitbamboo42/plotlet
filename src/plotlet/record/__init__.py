"""plotlet's recording half — user calls in, `FigureIR` out.

`Chart` / `Layout` / `FacetGrid` methods (`chart.py`, `facet.py`,
`legend.py`) append to the journal (`journal.py`), never execute;
`figure_ir.py` compiles the journal to the `FigureIR` — the one
contract with the render half (`docs/ARCHITECTURE.md`). Nothing here
imports `plotlet.render` at module level (rendering loads lazily on
first render), and the render half never imports this package at all;
`tests/test_import_boundary.py` enforces both directions. Everything
both halves share is neutral vocabulary at the package root
(`registry`, `draw`, `_spec`, `scales`, ...).
"""
