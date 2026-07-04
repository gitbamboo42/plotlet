"""The recording/rendering split, enforced as tests.

The contract (plan of record: `docs/IR.md`): the recording half
(`chart`, `facet`, `legend`, `_journal`, `_ir`, ...) never imports the
render half at module level — `plotlet.render` loads lazily on first
render — and the render half never imports the recording half at all;
its only input is the `FigureIR`. Everything both halves share is
neutral vocabulary (`registry`, `draw`, `_spec`, `scales`, `sectors`,
`_regions`, `_tree`, `utils`, `_json_layer`, `_coord_registry`,
`formatters`, `themes`).

Two directions, two tests: a subprocess proves importing the recording
half loads no render module; a static import scan proves no render
module names a front-half module. A regression in either direction is
an architecture bug, not a style nit — fix the import, don't widen the
lists here.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

# Front-half modules the render half must never import: the recorder
# types, their factories and sugar, the journal, and the IR compiler.
# (`FigureIR` instances cross the seam duck-typed — the render half
# needs no import to consume one.) Everything else under plotlet/ is
# shared vocabulary (or render-internal).
FRONT_HALF = {
    "chart", "facet", "legend", "lint", "layout_diagram",
    "_journal", "_ir",
}


def test_importing_the_recording_half_never_loads_render():
    """`import plotlet` (and the journaling / IR modules explicitly) must
    not pull in the render half — it loads lazily on first render."""
    code = (
        "import sys\n"
        "import plotlet\n"
        "import plotlet._journal\n"
        "import plotlet._ir\n"
        "import plotlet.chart\n"
        "loaded = sorted(m for m in sys.modules"
        " if m.startswith('plotlet.render'))\n"
        "assert not loaded, f'render half loaded at import time: {loaded}'\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_rendering_loads_the_render_half_lazily():
    """Sanity for the test above: the lazy seam actually fires — a render
    in a fresh process does load `plotlet.render`."""
    code = (
        "import sys\n"
        "import plotlet as pt\n"
        "c = pt.chart({'x': [1, 2], 'y': [3, 4]})\n"
        "c.scatter(x='x', y='y')\n"
        "c.to_svg()\n"
        "assert 'plotlet.render' in sys.modules\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def _imported_plotlet_modules(path: Path):
    """Yield (lineno, top-level plotlet submodule name) for every import
    statement in a render/ source file. Relative imports resolve against
    the file's package (`plotlet.render`)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "plotlet" and len(parts) > 1:
                    yield node.lineno, parts[1]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                parts = (node.module or "").split(".")
                if parts[0] == "plotlet" and len(parts) > 1:
                    yield node.lineno, parts[1]
            elif node.level == 1:
                # `from . import x` / `from .x import y` — inside
                # plotlet.render, always render-internal.
                continue
            else:
                # level >= 2 resolves to plotlet.<module> (render/ is one
                # package deep). `from .. import x` puts the module in
                # the names; `from ..x import y` puts it in node.module.
                if node.module:
                    yield node.lineno, node.module.split(".")[0]
                else:
                    for alias in node.names:
                        yield node.lineno, alias.name.split(".")[0]


def test_render_half_imports_no_front_half_module():
    import plotlet.render
    render_dir = Path(plotlet.render.__path__[0])
    files = sorted(render_dir.glob("*.py"))
    assert files, f"no sources found under {render_dir}"
    offenders = [
        f"{path.name}:{lineno} imports plotlet.{mod}"
        for path in files
        for lineno, mod in _imported_plotlet_modules(path)
        if mod in FRONT_HALF
    ]
    assert not offenders, (
        "render/ must not import the recording half — its input is the "
        "FigureIR:\n  " + "\n  ".join(offenders)
    )
