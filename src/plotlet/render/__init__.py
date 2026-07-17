"""plotlet's render half — `FigureIR` in, SVG out.

Everything under this package is the rendering side of the
recording/rendering split: replay, layout, chrome, legend harvest, and
SVG emission, operating on the private node tree hydrated from a
`FigureIR` (`_nodes.py`). Nothing here imports the recording half
(the `record/` package) — the IR is the only input, and the
shared vocabulary (`registry`, `draw`, `_spec`, `sectors`, `utils`,
`_tree`, `_json_layer`, `scales`, `_regions`) is the only other
dependency. The contract lives in `docs/ARCHITECTURE.md`; `validate` enforces it
at every entry (`hydrate` runs it first).

The front half calls in through this seam — every function takes a
`FigureIR`:

    render_svg(ir, clean=..., outer=...)  render to the SVG string
    regions(ir, outer=...)                chrome regions from a render
    natural_size(ir)                      figure (W, H) after measurement
    data_total_size(ir)                   summed data-area (w, h)
    resolve(ir)                           the resolved IR — the render
                                          path's own middle stage
                                          (resolved_ir.py)
    validate(ir)                          contract check, ValueError on
                                          violation
    hydrate(ir) / materialize(tree)       the render tree, for tools
                                          that walk or measure it
"""
from ._nodes import (  # noqa: F401
    RenderNode, RenderLayout, hydrate, materialize,
)
from ._validate import validate  # noqa: F401
from .resolved_ir import resolve  # noqa: F401


def render_svg(ir, *, clean: bool = False, outer: bool = True) -> str:
    """Render a `FigureIR` to the standalone SVG string. Why every
    render passes through the resolved stage is `resolved_ir.py`'s
    docstring. `outer=False` drops the figure-level breathing-room
    margin — the inner render tools embed (`layout_diagram`) or
    measure against."""
    return resolve(ir).to_svg(clean=clean, outer=outer)


def regions(ir, *, outer: bool = True) -> list[dict]:
    """Render `ir` under a region-collecting sink and return the chrome
    regions — title, axis labels, ticks, spines, panel, legend
    sub-elements — as `{"kind", "bbox", "name", "meta"}` dicts. The SVG
    is discarded; this runs the same pipeline as `render_svg`, so the
    regions describe exactly that render. `outer` matches
    `render_svg`'s."""
    from .. import _regions

    with _regions.collecting() as sink:
        resolve(ir).to_svg(outer=outer)
    return [{"kind": r.kind, "bbox": r.bbox, "name": r.name, "meta": r.meta}
            for r in sink.regions]


def natural_size(ir) -> tuple[int, int]:
    """The figure's natural (W, H) in pixels — after the measurement
    pre-pass, so measure-driven margin growth and share-scaling
    coordination are included."""
    from ._layout_engine import _natural_size

    root = hydrate(ir)
    materialize(root)
    return _natural_size(root)


def data_total_size(ir) -> tuple[float, float]:
    """Summed data-area (w, h) across the figure's data leaves —
    combined like the layout combines canvases (sum along the layout
    direction, max orthogonally). Runs the same measurement pre-pass as
    `natural_size` first, so share-scaled leaves contribute their
    coordinated dims and the two functions describe one consistent
    figure. `Chart.fit()` solves `target = s * data_total + overhead`
    from the pair."""
    from ._layout_engine import _data_total_size, _natural_size

    root = hydrate(ir)
    materialize(root)
    _natural_size(root)
    return _data_total_size(root)
