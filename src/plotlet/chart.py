"""Tidy-table-friendly facade over Figure.

    c = chart(df, title="...", xlabel="...", legend=True, grid=True)
    c.line(x="time", y="value", hue="series")
    c                         # auto-renders in Jupyter

Each mark method (`line`, `scatter`, `bar`, `hist`, `fill_between`) accepts
either column-name kwargs against the bound table, or the existing array form
as positional args. `hue=<col>` splits into one call per unique value with
auto-labels and tab10 colors.

The bound table can be anything that supports `df[col_name]` returning an
iterable: pandas / polars DataFrames, dict-of-lists, dict-of-arrays. No
pandas dependency.
"""
from __future__ import annotations

from .core import Figure, _FRAME_METHODS
from .artists import _to_pylist
from .registry import get_artist, all_artist_names


class Chart:
    def __init__(self, data=None, *, width: int | None = None, height: int | None = None,
                 margin: dict | None = None,
                 title: str | None = None,
                 xlabel: str | None = None, ylabel: str | None = None,
                 xlim: tuple | None = None, ylim: tuple | None = None,
                 xscale: str | None = None, yscale: str | None = None,
                 legend: bool | None = None, grid: bool | None = None):
        self._fig = Figure(width=width, height=height, margin=margin)
        self._data = data
        if title  is not None: self._fig.title(title)
        if xlabel is not None: self._fig.xlabel(xlabel)
        if ylabel is not None: self._fig.ylabel(ylabel)
        if xlim   is not None: self._fig.xlim(*xlim)
        if ylim   is not None: self._fig.ylim(*ylim)
        if xscale is not None: self._fig.xscale(xscale)
        if yscale is not None: self._fig.yscale(yscale)
        if legend is not None: self._fig.legend(legend)
        if grid   is not None: self._fig.grid(grid)

    def __getattr__(self, name):
        # Mirrors Figure.__getattr__: any frame method or registered artist
        # forwards to self._fig and returns self for chaining. So custom
        # artists registered via add_artist() Just Work on Chart too.
        if name in _FRAME_METHODS or get_artist(name) is not None:
            def call(*args, **kwargs):
                getattr(self._fig, name)(*args, **kwargs)
                return self
            return call
        raise AttributeError(f"Chart has no method {name!r}")

    def __dir__(self):
        return sorted(set(super().__dir__()) | _FRAME_METHODS | set(all_artist_names()))

    # ---------- tabular mark methods ----------

    def line(self, *args, x=None, y=None, hue=None, data=None, **opts):
        if x is not None or y is not None:
            self._tabular("line", "plot", data, x, y, hue, opts)
        else:
            self._fig.plot(*args, **opts)
        return self

    def scatter(self, *args, x=None, y=None, hue=None, data=None, **opts):
        if x is not None or y is not None:
            self._tabular("scatter", "scatter", data, x, y, hue, opts)
        else:
            self._fig.scatter(*args, **opts)
        return self

    def bar(self, *args, x=None, y=None, data=None, **opts):
        if x is not None or y is not None:
            df = self._resolve_data(data, "bar")
            self._fig.bar(_to_pylist(df[x]), _to_pylist(df[y]), **opts)
        else:
            self._fig.bar(*args, **opts)
        return self

    def hist(self, *args, x=None, data=None, **opts):
        if x is not None:
            df = self._resolve_data(data, "hist")
            self._fig.hist(_to_pylist(df[x]), **opts)
        else:
            self._fig.hist(*args, **opts)
        return self

    def fill_between(self, *args, x=None, y1=None, y2=None, data=None, **opts):
        if x is not None or y1 is not None or y2 is not None:
            df = self._resolve_data(data, "fill_between")
            self._fig.fill_between(
                _to_pylist(df[x]), _to_pylist(df[y1]), _to_pylist(df[y2]), **opts)
        else:
            self._fig.fill_between(*args, **opts)
        return self

    # Reflines, imshow, and any user-registered artist forward through
    # __getattr__ above. They take raw lists/values, not column names.

    # ---------- helpers ----------

    def _resolve_data(self, data, public_name):
        df = data if data is not None else self._data
        if df is None:
            raise ValueError(
                f"Chart.{public_name}() with column-name kwargs requires a bound table; "
                f"pass data=<table> or use chart(<table>)."
            )
        return df

    def _tabular(self, public_name, kind, data, x_col, y_col, hue, opts):
        df = self._resolve_data(data, public_name)
        method = getattr(self._fig, kind)
        if hue is None:
            method(_to_pylist(df[x_col]), _to_pylist(df[y_col]), **opts)
            return
        hue_vals = _to_pylist(df[hue])
        xs_all = _to_pylist(df[x_col])
        ys_all = _to_pylist(df[y_col])
        seen: list = []
        for v in hue_vals:
            if v not in seen:
                seen.append(v)
        opts.pop("label", None)  # hue overrides any user-provided label
        for v in seen:
            xs_g = [xs_all[i] for i, h in enumerate(hue_vals) if h == v]
            ys_g = [ys_all[i] for i, h in enumerate(hue_vals) if h == v]
            method(xs_g, ys_g, label=str(v), **opts)

    # Frame-state methods (title/xlabel/ylabel/xlim/ylim/xscale/yscale/
    # grid/legend) forward through __getattr__ above.

    # ---------- render ----------

    def to_svg(self) -> str:
        return self._fig.to_svg()

    def to_html(self, full_page: bool = False) -> str:
        return self._fig.to_html(full_page=full_page)

    def _repr_html_(self) -> str:
        return self._fig.to_svg()

    def show(self):
        self._fig.show()

    def save_svg(self, path):
        self._fig.save_svg(path)
        return self

    def write_html(self, path):
        self._fig.write_html(path)
        return self


def chart(data=None, **opts) -> Chart:
    """Construct a table-bound Chart. See `Chart` for keyword arguments."""
    return Chart(data, **opts)
