"""Tidy-table-friendly facade over Figure, plus subplot composition.

A `Chart` is one of two things:

  * **Leaf** — wraps a `Figure` and records artist calls into it. This is the
    surface returned by `pt.chart(...)`. `_layout_kind is None`.

  * **Parent** — composed from other Charts. Holds a list of children and a
    layout direction ("h" | "v" | "grid"). Has no `_fig` of its own; rendering
    walks the tree (see `layout.py`).

Composition operators:

  * `a | b` → horizontal parent. Flattens when LHS is already a same-direction
    parent with no own parent (so `a | b | c` is a single 3-cell row, not
    nested). Mutates the LHS parent in place; LHS should not be reused after.

  * `a / b` → vertical parent. Same flattening rule.

  * `pt.grid([[a, b], [c, d]])` → grid parent. Lives in `layout.py`.

Invariants:

  * Single parent — composing a chart that already has a `_parent` raises.
  * Show-on-child raises — calling `.show()` / `.to_svg()` / `_repr_html_`
    on a parented chart raises with a pointer to the parent.
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
                 legend: bool | None = None, grid: bool | None = None,
                 share_x: "Chart | None" = None, share_y: "Chart | None" = None):
        self._fig = Figure(width=width, height=height, margin=margin)
        self._data = data
        # Composition state. Leaves: _layout_kind is None, _children is empty.
        self._parent: Chart | None = None
        self._layout_kind: str | None = None
        self._children: list[Chart] = []
        # Layout hints — used in step 1 only for auto-zero-gutter.
        # Step 2 will plumb these through to scale-build.
        self._share_x: Chart | None = share_x
        self._share_y: Chart | None = share_y
        if title  is not None: self._fig.title(title)
        if xlabel is not None: self._fig.xlabel(xlabel)
        if ylabel is not None: self._fig.ylabel(ylabel)
        if xlim   is not None: self._fig.xlim(*xlim)
        if ylim   is not None: self._fig.ylim(*ylim)
        if xscale is not None: self._fig.xscale(xscale)
        if yscale is not None: self._fig.yscale(yscale)
        if legend is not None: self._fig.legend(legend)
        if grid   is not None: self._fig.grid(grid)

    # ---------- composition ----------

    @classmethod
    def _new_parent(cls, kind: str, children: list["Chart"]) -> "Chart":
        """Construct a parent Chart with no Figure of its own."""
        p = cls.__new__(cls)
        p._fig = None
        p._data = None
        p._parent = None
        p._layout_kind = kind
        p._children = list(children)
        p._share_x = None
        p._share_y = None
        return p

    @property
    def _is_parent(self) -> bool:
        return self._layout_kind is not None

    def __or__(self, other: "Chart") -> "Chart":
        return _compose(self, other, "h")

    def __truediv__(self, other: "Chart") -> "Chart":
        return _compose(self, other, "v")

    # ---------- recording (leaf only) ----------

    def __getattr__(self, name):
        # __getattr__ is only called when normal lookup fails, so this won't
        # interfere with _fig / _layout_kind / _children etc.
        if name.startswith("_"):
            raise AttributeError(name)
        if self._layout_kind is not None:
            raise AttributeError(
                f"{name!r} is not available on a parent Chart "
                f"(layout={self._layout_kind!r}). Call it on a leaf chart instead."
            )
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
        self._require_leaf("line")
        if x is not None or y is not None:
            self._tabular("line", "plot", data, x, y, hue, opts)
        else:
            self._fig.plot(*args, **opts)
        return self

    def scatter(self, *args, x=None, y=None, hue=None, data=None, **opts):
        self._require_leaf("scatter")
        if x is not None or y is not None:
            self._tabular("scatter", "scatter", data, x, y, hue, opts)
        else:
            self._fig.scatter(*args, **opts)
        return self

    def bar(self, *args, x=None, y=None, data=None, **opts):
        self._require_leaf("bar")
        if x is not None or y is not None:
            df = self._resolve_data(data, "bar")
            self._fig.bar(_to_pylist(df[x]), _to_pylist(df[y]), **opts)
        else:
            self._fig.bar(*args, **opts)
        return self

    def hist(self, *args, x=None, data=None, **opts):
        self._require_leaf("hist")
        if x is not None:
            df = self._resolve_data(data, "hist")
            self._fig.hist(_to_pylist(df[x]), **opts)
        else:
            self._fig.hist(*args, **opts)
        return self

    def fill_between(self, *args, x=None, y1=None, y2=None, data=None, **opts):
        self._require_leaf("fill_between")
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

    def _require_leaf(self, public_name):
        if self._layout_kind is not None:
            raise TypeError(
                f"Chart.{public_name}() is only valid on a leaf chart, not a parent "
                f"(layout={self._layout_kind!r})."
            )

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
        self._require_render_root()
        if self._is_parent:
            from .layout import _render_layout
            return _render_layout(self)
        return self._fig.to_svg()

    def to_html(self, full_page: bool = False) -> str:
        svg = self.to_svg()
        if full_page:
            return ('<!doctype html><html><head><meta charset="utf-8">'
                    '<title>plotlet</title></head>'
                    f'<body style="margin:24px">{svg}</body></html>')
        return svg

    def _repr_html_(self) -> str:
        return self.to_svg()

    def show(self):
        self._require_render_root()
        if self._is_parent:
            svg = self.to_svg()
            try:
                from IPython.display import HTML, display
            except ImportError:
                print(self.to_html(full_page=True))
                return
            display(HTML(svg))
            return
        self._fig.show()

    def save_svg(self, path):
        from pathlib import Path
        Path(path).write_text(self.to_svg())
        return self

    def write_html(self, path):
        from pathlib import Path
        Path(path).write_text(self.to_html(full_page=True))
        return self

    def _require_render_root(self):
        if self._parent is not None:
            raise RuntimeError(
                "this chart is part of a composed parent; render the parent instead."
            )


def chart(data=None, **opts) -> Chart:
    """Construct a table-bound Chart. See `Chart` for keyword arguments."""
    return Chart(data, **opts)


def _compose(left: Chart, right: Chart, kind: str) -> Chart:
    """Implement `|` / `/`. Flattens same-direction parents in place on LHS."""
    if not isinstance(right, Chart):
        return NotImplemented
    if left._parent is not None or right._parent is not None:
        raise ValueError(
            "Each chart can be in at most one parent. "
            "Compose fresh charts, or copy your sub-assembly."
        )
    # Flatten LHS if it's a same-direction parent (so `a | b | c` is one row of 3).
    if left._is_parent and left._layout_kind == kind:
        if right._is_parent and right._layout_kind == kind:
            for child in right._children:
                child._parent = left
            left._children.extend(right._children)
        else:
            left._children.append(right)
            right._parent = left
        return left
    parent = Chart._new_parent(kind, [left, right])
    left._parent = parent
    right._parent = parent
    return parent
