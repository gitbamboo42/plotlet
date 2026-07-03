"""Faceting — small-multiples by a categorical column.

`pt.facet(data, by="col")` returns a recorder with the same mark / frame
methods as `Chart`. Each call is stored; on render the recorder splits
`data` by unique values of `by`, builds one `Chart` per subset, replays
the recorded calls against it, and lays the panels out in a `pt.grid`
with `share_x` / `share_y` on by default — adjacent panels read as one
continuous coordinate system.

    g = pt.facet(df, by="species", col_wrap=3)
    g.scatter(x="bill_length", y="bill_depth")
    g.show()

Why a recorder (not "build one Chart per group inline"): the user's
column-name args (`x="bill_length"`) need to be re-resolved against each
subset, and the panel title defaults to the group label. Deferring is the
simplest way to keep that bookkeeping out of user code.
"""
from __future__ import annotations

import math

from .chart import Chart, chart, grid


def facet(data, *, by, col_wrap=None, share_x=True, share_y=True,
          **chart_opts) -> "FacetGrid":
    """Build a FacetGrid bound to `data`, splitting by `by`. Forwarded
    `chart_opts` (e.g. `data_width`, `xlabel`, `theme`) apply to every
    panel; the per-panel title defaults to the group label."""
    if data is None:
        raise ValueError("pt.facet requires a data argument.")
    return FacetGrid(data, by, col_wrap=col_wrap,
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
    """Return [(label, subset_in_same_shape_as_data), ...] in first-seen order.

    pandas-style `.groupby` is preferred when available so the subsets keep
    their original type; otherwise the data is materialized as a dict of
    lists and sliced by index."""
    if hasattr(data, "groupby"):
        return [(k, sub) for k, sub in data.groupby(by, sort=False)]
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


class FacetGrid:
    """Records method calls; produces one Chart per group on render.

    Mark methods (`line`, `scatter`, `bar`, …) and frame methods
    (`title`, `xlabel`, `xticks`, …) all work — anything you can call on
    a `Chart` you can call here, and it replays against every panel.
    Title defaults to the group label; calling `.title(...)` overrides
    that (the recorded call wins on replay).
    """

    def __init__(self, data, by, *, col_wrap, share_x, share_y, chart_opts):
        self._data = data
        self._by = by
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

    def _materialize(self) -> Chart:
        groups = _split_by(self._data, self._by)
        if not groups:
            raise ValueError(
                f"pt.facet: column {self._by!r} has no values; nothing to facet on."
            )
        panels: list[Chart] = []
        for label, subset in groups:
            opts = dict(self._chart_opts)
            opts.setdefault("title", str(label))
            c = chart(subset, **opts)
            for name, args, kwargs in self._calls:
                getattr(c, name)(*args, **kwargs)
            panels.append(c)
        cols = self._col_wrap if self._col_wrap else max(1, math.ceil(math.sqrt(len(panels))))
        rows = math.ceil(len(panels) / cols)
        cells = []
        for r in range(rows):
            row = []
            for cidx in range(cols):
                i = r * cols + cidx
                row.append(panels[i] if i < len(panels) else None)
            cells.append(row)
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

    def _repr_html_(self) -> str:
        return self._materialize()._repr_html_()

    def show(self):
        return self._materialize().show()

    def save_svg(self, path):
        self._materialize().save_svg(path)
        return self

    def save_png(self, path, *, scale: float = 1.0, dpi: int | None = None):
        self._materialize().save_png(path, scale=scale, dpi=dpi)
        return self

    def save_pdf(self, path):
        self._materialize().save_pdf(path)
        return self

    def write_html(self, path):
        self._materialize().write_html(path)
        return self
