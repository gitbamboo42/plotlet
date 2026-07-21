"""Faceting — small-multiples by one or two categorical columns.

`pt.facet(data, by="col")` returns a recorder with the same mark / frame
methods as `Chart`. Each call is stored; on render the recorder splits
`data` by unique values of `by`, builds one `Chart` per subset, replays
the recorded calls against it, and lays the panels out in a `pt.grid`
with `share_x` / `share_y` on by default — adjacent panels read as one
continuous coordinate system.

    g = pt.facet(df, by="species", col_wrap=3)
    g.add_scatter(aes(x="bill_length", y="bill_depth"))
    g.show()

Two-factor form — `row=` / `col=` (the seaborn names; ggplot's
`facet_grid(rows ~ cols)`): one grid row per level of `row`, one grid
column per level of `col`, both in first-seen order. Combinations with
no data become blank cells. Panel titles default to `"{row} | {col}"`
(the lone level when only one factor is given).

    g = pt.facet(df, row="sex", col="species")
    g.add_scatter(aes(x="bill_length", y="bill_depth"))

Why a recorder (not "build one Chart per group inline"): the user's
column mappings (`aes(x="bill_length")`) need to be re-resolved against each
subset, and the panel title defaults to the group label. Deferring is the
simplest way to keep that bookkeeping out of user code.
"""
from __future__ import annotations

import math

from .chart import Chart, chart, grid, _REPR_SCALE
from ..utils import _normalize_data


def facet(data, *, by=None, row=None, col=None, col_wrap=None,
          share_x=True, share_y=True, **chart_opts) -> "FacetGrid":
    """Build a FacetGrid bound to `data`. `by=` wraps one variable's
    panels into a near-square grid (`col_wrap=` fixes the column count);
    `row=` / `col=` lay a two-factor grid, one factor per grid axis.
    Forwarded `chart_opts` (e.g. `data_width`, `xlabel`, `theme`) apply
    to every panel; the per-panel title defaults to the group label."""
    if data is None:
        raise ValueError("pt.facet requires a data argument.")
    # Same recorder-boundary normalization as `pt.chart(data)` — the
    # journal (and JSON layer) never hold a library-specific object.
    data = _normalize_data(data)
    if by is not None and (row is not None or col is not None):
        raise TypeError(
            "pt.facet: pass either by= (wrapped panels) or row=/col= "
            "(two-factor grid), not both."
        )
    if by is None and row is None and col is None:
        raise TypeError(
            "pt.facet requires by= (wrapped panels) or row=/col= "
            "(two-factor grid)."
        )
    if col_wrap is not None and by is None:
        raise TypeError(
            "pt.facet: col_wrap= applies to by= wrapping; a row=/col= "
            "grid is shaped by its factor levels."
        )
    return FacetGrid(data, by=by, row=row, col=col, col_wrap=col_wrap,
                     share_x=share_x, share_y=share_y,
                     chart_opts=chart_opts)


def _data_columns(data):
    if hasattr(data, "columns"):
        return list(data.columns)
    if hasattr(data, "keys"):
        return list(data.keys())
    raise TypeError(
        "pt.facet: data must support column access — pandas / polars "
        "DataFrame or dict-like with .keys()."
    )


def _to_list_column(values):
    if hasattr(values, "tolist"):
        return values.tolist()
    return list(values)


def _split_by(data, by):
    """Return [(label, subset_as_dict_of_lists), ...] in first-seen order.

    `data` is always normalized (`DataFrameLite` / dict of lists) by the
    time this runs — `facet()` normalizes on entry."""
    cols = {col: _to_list_column(data[col]) for col in _data_columns(data)}
    if by not in cols:
        raise KeyError(f"pt.facet: column {by!r} not found in data")
    keys = cols[by]
    order = []
    for k in keys:
        if k not in order:
            order.append(k)
    out = []
    for label in order:
        idxs = [i for i, k in enumerate(keys) if k == label]
        sub = {col: [vals[i] for i in idxs] for col, vals in cols.items()}
        out.append((label, sub))
    return out


def _split_by_2(data, row_by, col_by):
    """Return (row_levels, col_levels, {(row, col): subset}); each level
    list is in first-seen order over the rows of `data`. Combinations
    that never occur are simply absent from the dict."""
    cols = {c: _to_list_column(data[c]) for c in _data_columns(data)}
    for name in (row_by, col_by):
        if name not in cols:
            raise KeyError(f"pt.facet: column {name!r} not found in data")
    row_keys, col_keys = cols[row_by], cols[col_by]
    row_levels, col_levels, idxs = [], [], {}
    for i, (rv, cv) in enumerate(zip(row_keys, col_keys)):
        if rv not in row_levels:
            row_levels.append(rv)
        if cv not in col_levels:
            col_levels.append(cv)
        idxs.setdefault((rv, cv), []).append(i)
    cells = {
        key: {col: [vals[i] for i in ii] for col, vals in cols.items()}
        for key, ii in idxs.items()
    }
    return row_levels, col_levels, cells


class FacetGrid:
    """Records method calls; produces one Chart per group on render.

    Mark methods (`line`, `scatter`, `bar`, …) and frame methods
    (`title`, `xlabel`, `xticks`, …) all work — anything you can call on
    a `Chart` you can call here, and it replays against every panel.
    Title defaults to the group label; calling `.title(...)` overrides
    that (the recorded call wins on replay).
    """

    def __init__(self, data, *, by, row, col, col_wrap,
                 share_x, share_y, chart_opts):
        self._data = data
        self._by = by
        self._row = row
        self._col = col
        self._col_wrap = col_wrap
        self._share_x = share_x
        self._share_y = share_y
        self._chart_opts = dict(chart_opts)
        self._calls: list[tuple[str, list, dict]] = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def recorder(*args, **kwargs):
            self._calls.append((name, list(args), dict(kwargs)))
            return self
        return recorder

    def _panel(self, subset, default_title: str) -> Chart:
        opts = dict(self._chart_opts)
        opts.setdefault("title", default_title)
        c = chart(subset, **opts)
        for name, args, kwargs in self._calls:
            getattr(c, name)(*args, **kwargs)
        return c

    def _wrap_cells(self) -> list:
        groups = _split_by(self._data, self._by)
        if not groups:
            raise ValueError(
                f"pt.facet: column {self._by!r} has no values; nothing to facet on."
            )
        panels = [self._panel(subset, str(label)) for label, subset in groups]
        cols = self._col_wrap if self._col_wrap else max(1, math.ceil(math.sqrt(len(panels))))
        rows = math.ceil(len(panels) / cols)
        cells = []
        for r in range(rows):
            row = []
            for cidx in range(cols):
                i = r * cols + cidx
                row.append(panels[i] if i < len(panels) else None)
            cells.append(row)
        return cells

    def _grid_cells(self) -> list:
        row_by, col_by = self._row, self._col
        if row_by is not None and col_by is not None:
            row_levels, col_levels, subsets = _split_by_2(
                self._data, row_by, col_by)
            if not subsets:
                raise ValueError(
                    f"pt.facet: columns {row_by!r} / {col_by!r} have no "
                    f"values; nothing to facet on."
                )
            return [[(self._panel(subsets[(rv, cv)], f"{rv} | {cv}")
                      if (rv, cv) in subsets else None)
                     for cv in col_levels]
                    for rv in row_levels]
        lone = row_by if row_by is not None else col_by
        groups = _split_by(self._data, lone)
        if not groups:
            raise ValueError(
                f"pt.facet: column {lone!r} has no values; nothing to facet on."
            )
        panels = [self._panel(subset, str(label)) for label, subset in groups]
        # row= stacks levels vertically; col= lays them out in one row.
        return [[p] for p in panels] if row_by is not None else [panels]

    def _materialize(self) -> Chart:
        cells = self._wrap_cells() if self._by is not None else self._grid_cells()
        layout = grid(cells)
        if self._share_x:
            layout.share_x(self._share_x)
        if self._share_y:
            layout.share_y(self._share_y)
        return layout

    def to_svg(self, *, clean: bool = False) -> str:
        return self._materialize().to_svg(clean=clean)

    def to_html(self, full_page: bool = False) -> str:
        return self._materialize().to_html(full_page=full_page)

    def _repr_mimebundle_(self, include=None, exclude=None):
        return self._materialize()._repr_mimebundle_(include, exclude)

    def show(self, *, format: str = "png", scale: float = _REPR_SCALE):
        return self._materialize().show(format=format, scale=scale)

    def save_svg(self, path, *, clean: bool = False):
        self._materialize().save_svg(path, clean=clean)
        return self

    def save_png(self, path, *, scale: float = 1.0):
        self._materialize().save_png(path, scale=scale)
        return self

    def save_pdf(self, path):
        self._materialize().save_pdf(path)
        return self

    def save_html(self, path):
        self._materialize().save_html(path)
        return self
