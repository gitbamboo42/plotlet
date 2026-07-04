"""plotlet's render half — `FigureIR` in, SVG out.

Everything under this package is the rendering side of the
recording/rendering split: replay, layout, chrome, legend harvest, and
SVG emission, operating on the private node tree hydrated from a
`FigureIR` (`_nodes.py`). Nothing here imports the recording half
(`chart`, `facet`, `_journal`) — the IR is the only input, and the
shared vocabulary (`registry`, `draw`, `_spec`, `sectors`, `utils`,
`_tree`, `_json_layer`) is the only other dependency.

The front half calls in through this seam:

    render_svg(ir, clean=...)   render a FigureIR to the SVG string
    hydrate(ir)                 build the render tree (for tools that
                                walk or measure it)
    materialize(tree)           derive wired field state on a tree
    resolve(ir)                 pre-layout render plan (resolved IR)
"""
from ._nodes import (  # noqa: F401
    RenderNode, RenderLayout, hydrate, materialize, render_svg,
)
from .resolved import resolve_ir as resolve  # noqa: F401
