"""Layout-level legend — the `pt.legend(...)` factory.

A legend is a leaf-flavored `Chart`. The layout treats it as a regular
leaf with intrinsic size, but it renders through the legend renderer
(`render/_legend.py`) instead of the standard frame+artists pipeline.
Geometry (gradient strip vs. swatch list) is decided at render time
from the source's color mapping, not by the constructor name. See
`docs/SUBPLOTS.md`.
"""
from __future__ import annotations

from .chart import Chart


def legend(*sources: Chart, names: dict | None = None,
           group_by_chart: bool = True,
           valign: str = "middle",
           ncols: int = 1,
           reverse: bool = False,
           entries: list | None = None,
           canvas_width: int | float | str | None = None,
           canvas_height: int | float | str | None = None,
           legend_gap: int | float | None = None,
           **kwargs) -> Chart:
    """Create a layout-level legend.

    With no `sources`, the legend harvests entries from every leaf in
    its parent layout. With sources, it harvests only from those.

    Multiple sources are grouped by source chart, with each chart's
    `title` rendered as a section header. `names={chart: "Override"}`
    replaces a header text; `names={chart: None}` hides the header
    while keeping the entries. `group_by_chart=False` flattens all
    entries into a single unsectioned list (useful when small-multiples
    genuinely share a series).

    `valign=` controls where the content sits vertically when the
    legend leaf gets more space than its content needs (siblings taller,
    or explicit `canvas_height=`). `"middle"` (default) centers it;
    `"top"` pins it to the top edge.

    `ncols=N` wraps each discrete entry list into N columns, filled
    down-then-across (matplotlib's `ncols`, ggplot2's `guide_legend(
    ncol=)`) — the fix for a long categorical legend outgrowing its
    siblings. Headers and gradient strips span the full width; each
    grouped guide block wraps independently.

    `reverse=True` flips the discrete entry order within each section
    (matplotlib's `reverse`) — the fix when stacked marks read bottom-up
    but the legend reads top-down.

    `entries=[{"label": ..., "color": ...}, ...]` appends free-form
    manual rows not harvested from any artist (an annotation color, an
    external reference). Each dict needs `label` and `color`; optional
    `alpha`. Manual rows render as standard rect swatches after the
    harvested sections.

    Legend leaves have no data axes, so the dimensional surface is
    canvas-only: pass `canvas_width=` / `canvas_height=` to override the
    content-driven auto-size. `legend_gap=N` overrides the default 6 px
    separation between this legend and its source neighbor (falls back
    to `spec.json:layout.legend_gap` when unset).
    """
    if kwargs:
        raise TypeError(f"pt.legend() got unexpected keyword arguments: {list(kwargs)!r}")
    _validate_manual_entries(entries, "pt.legend")
    if valign not in ("top", "middle"):
        raise ValueError(
            f"pt.legend(valign={valign!r}) — must be 'top' or 'middle'."
        )
    if not isinstance(ncols, int) or isinstance(ncols, bool) or ncols < 1:
        raise ValueError(
            f"pt.legend(ncols={ncols!r}) — must be an int >= 1."
        )
    for src in sources:
        if not isinstance(src, Chart):
            raise TypeError(
                f"pt.legend() sources must be Chart objects; got {type(src).__name__}."
            )
        if src._is_parent:
            raise ValueError(
                "pt.legend() sources must be leaf charts, not composed parents."
            )
    # Canvas size starts as a 1×1 placeholder; `_size_legends` overrides
    # it from harvested content at render time, unless the user passed
    # an explicit canvas_*. Legend leaves have no data region — the
    # canvas IS the dimensional primitive (see `Chart._new_sized_leaf`).
    from .utils import _to_px
    cw = _to_px(canvas_width) if canvas_width is not None else 1
    ch = _to_px(canvas_height) if canvas_height is not None else 1
    leaf = Chart._new_sized_leaf(canvas_width=cw, canvas_height=ch,
                                 leaf_kind="legend")
    leaf._legend_sources = list(sources)
    leaf._legend_names = dict(names) if names else {}
    leaf._legend_group_by_chart = group_by_chart
    leaf._legend_valign = valign
    leaf._legend_ncols = ncols
    leaf._legend_reverse = bool(reverse)
    leaf._legend_manual = [dict(e) for e in entries] if entries else []
    leaf._legend_user_width = canvas_width
    leaf._legend_user_height = canvas_height
    leaf._legend_gap = float(legend_gap) if legend_gap is not None else None
    return leaf


def _validate_manual_entries(entries, where: str) -> None:
    """Shared `entries=` validation for `pt.legend` and `Chart.legend`."""
    if entries is None:
        return
    if not isinstance(entries, (list, tuple)):
        raise TypeError(
            f"{where}(entries=...) — pass a list of "
            f'{{"label": ..., "color": ...}} dicts.'
        )
    for e in entries:
        if not isinstance(e, dict) or "label" not in e or "color" not in e:
            raise ValueError(
                f"{where}(entries=...) — each entry needs at least "
                f'"label" and "color"; got {e!r}.'
            )
