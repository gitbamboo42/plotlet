"""Chart — the user-facing object. Leaf for one panel, parent when composed.

A `Chart` is one of two things:

  * **Leaf** — records artist calls into `_calls` and carries the dimensions
    + margin needed to render one panel. This is the surface returned by
    `pt.chart(...)`. `_layout_kind is None`.

  * **Parent** — composed from other Charts. Holds a list of children and a
    layout direction ("h" | "v" | "grid"). Carries no per-leaf render state;
    rendering walks the tree (see `layout.py`).

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

from pathlib import Path

from ._spec import _SIZESPEC, active_theme
from .core import (
    _FRAME_METHODS, _replay, _effective_margin, _render,
    _to_px,
)
from .utils import to_list, to_list_2d
from .registry import get_artist, all_artist_names


def _extract_theme(calls) -> str | None:
    """Last-call-wins scan for the active theme. Returns `None` when the
    chart never set a theme — `active_theme(None)` is a passthrough that
    leaves the spec dicts on their current values."""
    name = None
    for call_name, args, _ in calls:
        if call_name == "theme":
            name = args[0] if args else None
    return name


def _normalize_inner_gap(value) -> tuple[float, float]:
    """Normalize an `inner_gap` value to an internal `(vertical, horizontal)`
    tuple. Scalars are duplicated to both directions; a 2-tuple/list is
    coerced element-wise. Negative values reject."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        if v < 0:
            raise ValueError(f"inner_gap must be non-negative; got {value!r}")
        return (v, v)
    if isinstance(value, (tuple, list)) and len(value) == 2:
        try:
            v, h = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            raise TypeError(
                "inner_gap tuple must contain two numbers; "
                f"got {value!r}"
            ) from None
        if v < 0 or h < 0:
            raise ValueError(f"inner_gap values must be non-negative; got {value!r}")
        return (v, h)
    raise TypeError(
        "inner_gap must be a number or a 2-tuple (vertical, horizontal); "
        f"got {type(value).__name__}: {value!r}"
    )


class Chart:
    def __init__(self, data=None, *,
                 data_width: int | float | str | None = None,
                 data_height: int | float | str | None = None,
                 margin: dict | None = None,
                 title: str | None = None,
                 xlabel: str | None = None, ylabel: str | None = None,
                 xlim: tuple | None = None, ylim: tuple | None = None,
                 xscale: str | None = None, yscale: str | None = None,
                 x_expand: float | tuple | None = None,
                 y_expand: float | tuple | None = None,
                 legend: bool | None = None, grid: bool | None = None,
                 theme: str | None = None,
                 **kwargs):
        # Migration errors — surface the rename loudly rather than silently
        # accepting and producing a different-sized figure.
        if "width" in kwargs or "height" in kwargs:
            raise TypeError(
                "pt.chart() no longer accepts `width=` / `height=` (changed in 0.2.0). "
                "Pass `data_width=` / `data_height=` for the data region."
            )
        if "canvas_width" in kwargs or "canvas_height" in kwargs:
            raise TypeError(
                "pt.chart() no longer accepts `canvas_width=` / `canvas_height=` "
                "(removed in 0.4.0). Use `data_width=` / `data_height=` to size the "
                "data region; if you need the rendered SVG to fit a specific canvas, "
                "chain `.fit(canvas_width=…, canvas_height=…)` after composition."
            )
        if "share_x" in kwargs or "share_y" in kwargs:
            raise TypeError(
                "pt.chart() no longer accepts `share_x=` / `share_y=` "
                "(moved to compose-time). Use `pt.grid([[...]], share_x=True)` "
                "or `(a | b).share_x()` instead."
            )
        if kwargs:
            raise TypeError(f"Chart() got unexpected keyword arguments: {list(kwargs)!r}")

        # ---- Render-state init (leaf-only fields used by core._render) ----
        # Resolve unit-suffixed strings (`"4in"`, `"10cm"`, …) once at the
        # boundary so internal math stays in pixels.
        data_width  = _to_px(data_width)
        data_height = _to_px(data_height)

        self._calls: list[tuple[str, list, dict]] = []
        self._margin = dict(margin) if margin is not None else dict(_SIZESPEC["margin"])

        # User picks the data region exactly. Margin is used unscaled (only
        # floored). Canvas falls out as data + margin; render-time pre-pass
        # may grow the margin further to fit long tick/axis labels.
        self._data_width  = data_width  if data_width  is not None else _SIZESPEC["data_width"]
        self._data_height = data_height if data_height is not None else _SIZESPEC["data_height"]
        self._canvas_width  = self._data_width  + self._margin["left"] + self._margin["right"]
        self._canvas_height = self._data_height + self._margin["top"]  + self._margin["bottom"]
        # Snapshot the user's originally-requested data dims. The render-time
        # share-scaling pre-pass mutates `_data_width` / `_data_height` to
        # coordinate sibling sizes; restoring from these on re-render keeps
        # the operation idempotent across multiple `to_svg()` calls.
        self._orig_data_width  = self._data_width
        self._orig_data_height = self._data_height

        # ---- Composition state ---------------------------------------------
        self._data = data
        # Leaves: _layout_kind is None, _children is empty.
        self._parent: Chart | None = None
        self._layout_kind: str | None = None
        self._children: list[Chart] = []
        # Share-class membership. Set by parent-level .share_x() / .share_y()
        # (or pt.grid(share_x=...)); not user-settable on the leaf directly.
        self._share_x: Chart | None = None
        self._share_y: Chart | None = None
        # Per-parent gap overrides. None = use spec.json default. Only read
        # off parents (read sites are layout.py's gap-resolution helpers);
        # leaving them on leaves too keeps `_new_parent` and `__init__`
        # symmetric without a separate slot type.
        self._gap: float | None = None
        self._inner_gap: tuple[float, float] | None = None
        # Leaf discriminator. Values: "data" (default — normal chart leaf
        # with axes and artists), "legend" (set by pt.legend(...), bypasses
        # the frame+artists render path; see legend.py), "diagram" (set by
        # pt.layout_diagram(...) from layout_diagram.py — embeds a
        # pre-rendered SVG with no panel decorations). Parents leave this
        # at "data"; for them `_layout_kind` is the discriminator.
        self._leaf_kind: str = "data"
        self._legend_sources: list[Chart] = []
        self._legend_names: dict = {}
        self._legend_group_by_chart: bool = True

        # Apply convenience constructor kwargs by recording. `self.title(...)`
        # etc. fall through __getattr__ → recorder; `self.legend(...)` hits
        # the special method below (which dispatches leaf vs parent).
        if title  is not None: self.title(title)
        if xlabel is not None: self.xlabel(xlabel)
        if ylabel is not None: self.ylabel(ylabel)
        if xlim   is not None: self.xlim(*xlim)
        if ylim   is not None: self.ylim(*ylim)
        if xscale is not None: self.xscale(xscale)
        if yscale is not None: self.yscale(yscale)
        if x_expand is not None:
            self.x_expand(*(x_expand if isinstance(x_expand, (tuple, list)) else (x_expand,)))
        if y_expand is not None:
            self.y_expand(*(y_expand if isinstance(y_expand, (tuple, list)) else (y_expand,)))
        if legend is not None: self.legend(legend)
        if grid   is not None: self.grid(grid)
        if theme  is not None: self.theme(theme)

    # ---------- composition ----------

    @classmethod
    def _new_parent(cls, kind: str, children: list["Chart"]) -> "Chart":
        """Construct a parent Chart. Parents carry no render-state of their
        own — `_calls`, `_data_width`, `_margin`, etc. are leaf-only. The
        parent's total size is derived from its children at render time
        (sum-sizes; see `docs/SUBPLOTS.md`)."""
        p = cls.__new__(cls)
        p._data = None
        p._parent = None
        p._layout_kind = kind
        p._children = list(children)
        p._share_x = None
        p._share_y = None
        p._gap = None
        p._inner_gap = None
        p._leaf_kind = "data"
        p._legend_sources = []
        p._legend_names = {}
        p._legend_group_by_chart = True
        return p

    @classmethod
    def _new_sized_leaf(cls, *,
                        canvas_width: int, canvas_height: int,
                        leaf_kind: str,
                        margin: dict | None = None) -> "Chart":
        """Construct a non-data leaf with an explicitly-sized canvas.
        Used internally by `pt.legend()` and `pt.layout_diagram()` —
        legends and diagrams have no axes so sizing isn't expressed as
        a data region; the canvas IS the primitive. Bypasses the
        body-first margin path in `__init__`."""
        leaf = cls.__new__(cls)
        leaf._calls = []
        leaf._margin = dict(margin) if margin is not None else dict(_SIZESPEC["margin"])
        leaf._canvas_width  = int(canvas_width)
        leaf._canvas_height = int(canvas_height)
        # Non-data leaves carry no real data region; keep zeros so any
        # accidental read produces a zero contribution.
        leaf._data_width = 0
        leaf._data_height = 0
        leaf._orig_data_width = 0
        leaf._orig_data_height = 0
        leaf._data = None
        leaf._parent = None
        leaf._layout_kind = None
        leaf._children = []
        leaf._share_x = None
        leaf._share_y = None
        leaf._gap = None
        leaf._inner_gap = None
        leaf._leaf_kind = leaf_kind
        leaf._legend_sources = []
        leaf._legend_names = {}
        leaf._legend_group_by_chart = True
        return leaf

    @property
    def _is_parent(self) -> bool:
        return self._layout_kind is not None

    def __or__(self, other: "Chart") -> "Chart":
        return _compose(self, other, "h")

    def __truediv__(self, other: "Chart") -> "Chart":
        return _compose(self, other, "v")

    def share_x(self, mode: bool | str = "all") -> "Chart":
        """Wire up x-axis sharing across this parent's leaves. Mutates the
        leaves' private share state so layout's pre-pass coordinates them.
        Returns self for chaining."""
        self._apply_share("x", mode)
        return self

    def share_y(self, mode: bool | str = "all") -> "Chart":
        """Wire up y-axis sharing across this parent's leaves. See `share_x`."""
        self._apply_share("y", mode)
        return self

    def gap(self, value: int | float) -> "Chart":
        """Override the inter-panel gap for this parent's children. Falls
        back to `spec.json:layout.gap` (default 20) when unset. Coordinated
        share-pair joints still collapse to 0 regardless."""
        if not self._is_parent:
            raise TypeError(
                "Chart.gap() requires a parent Chart, not a leaf. "
                "Compose first (e.g. (a | b).gap(0)) then call."
            )
        self._gap = float(value)
        return self

    def inner_gap(self, value) -> "Chart":
        """Override the inner-margin collapse value for share-pair joints
        among this parent's body-first leaves. Accepts a scalar (applies to
        both directions) or a 2-tuple `(vertical, horizontal)` to set
        per-direction values — `vertical` controls joints in a vertical
        stack (share_x), `horizontal` controls joints in a horizontal row
        (share_y). Falls back to `spec.json:layout.inner_gap` when unset."""
        if not self._is_parent:
            raise TypeError(
                "Chart.inner_gap() requires a parent Chart, not a leaf. "
                "Compose first (e.g. (a | b).share_x().inner_gap(4)) then call."
            )
        self._inner_gap = _normalize_inner_gap(value)
        return self

    def _apply_share(self, axis: str, mode) -> None:
        norm = _normalize_share_mode(axis, mode)
        if norm == "none":
            return
        if not self._is_parent:
            raise TypeError(
                f"share_{axis}() requires a parent Chart, not a leaf. "
                f"Compose first (e.g. (a | b).share_{axis}()) then call."
            )
        if norm in ("col", "row") and self._layout_kind != "grid":
            raise ValueError(
                f"share_{axis}={norm!r} requires a pt.grid parent; got "
                f"{self._layout_kind!r} layout. Use share_{axis}=True for "
                f"all-leaves sharing on h/v compositions."
            )
        classes = self._compute_share_classes(norm)
        attr = "_share_x" if axis == "x" else "_share_y"
        for cls in classes:
            if len(cls) < 2:
                continue
            anchor = cls[0]
            for leaf in cls[1:]:
                setattr(leaf, attr, anchor)

    def _compute_share_classes(self, mode: str) -> list[list["Chart"]]:
        from .layout import _iter_leaves

        def cell_leaves(cell):
            if cell is None:
                return []
            if cell._is_parent:
                return [l for l in _iter_leaves(cell) if l._leaf_kind == "data"]
            return [cell] if cell._leaf_kind == "data" else []

        if mode == "all":
            return [[l for l in _iter_leaves(self) if l._leaf_kind == "data"]]
        rows, cols = self._grid_rows, self._grid_cols
        children = self._children
        if mode == "col":
            return [
                [l for r in range(rows) for l in cell_leaves(children[r * cols + c])]
                for c in range(cols)
            ]
        # mode == "row"
        return [
            [l for c in range(cols) for l in cell_leaves(children[r * cols + c])]
            for r in range(rows)
        ]

    def legend(self, *args, names: dict | None = None,
               group_by_chart: bool | None = None,
               canvas_width: int | float | str | None = None,
               canvas_height: int | float | str | None = None,
               legend_gap: int | float | None = None,
               **kwargs) -> "Chart":
        """Toggle the in-frame overlay (leaf) or attach a layout-level legend (parent).

        On a leaf, this is the existing `chart.legend([bool])` toggle for
        the in-frame overlay — args must be a single optional bool.

        On a parent, this is sugar for the panel form: `parent.legend(*sources)`
        is equivalent to `parent | pt.legend(*sources)` (or `parent / ...` for
        a vertical parent), with `names=` / `group_by_chart=` / `canvas_width=` /
        `canvas_height=` / `legend_gap=` forwarded to the constructor. Grids
        raise — place `pt.legend(...)` in an explicit cell instead. Returns
        `self` for chaining; remember that further composition (`|` / `/`)
        appends children *after* the legend, so decorate last."""
        if "width" in kwargs or "height" in kwargs:
            raise TypeError(
                "Chart.legend() no longer accepts `width=` / `height=` "
                "(changed in 0.2.0). Use `canvas_width=` / `canvas_height=` "
                "instead — legend leaves have no data axes, so the canvas "
                "is the only meaningful dimension."
            )
        if kwargs:
            raise TypeError(
                f"Chart.legend() got unexpected keyword arguments: {list(kwargs)!r}"
            )
        if self._is_parent:
            if self._layout_kind == "grid":
                raise ValueError(
                    "parent.legend() doesn't apply to grid layouts; "
                    "place pt.legend() in a grid cell explicitly."
                )
            from .legend import legend as _make_legend
            gbc = True if group_by_chart is None else group_by_chart
            leg = _make_legend(*args, names=names, group_by_chart=gbc,
                               canvas_width=canvas_width, canvas_height=canvas_height,
                               legend_gap=legend_gap)
            self._children.append(leg)
            leg._parent = self
            return self
        # Leaf: today's in-frame overlay toggle. Reject parent-only kwargs.
        if (names is not None or group_by_chart is not None
                or canvas_width is not None or canvas_height is not None
                or legend_gap is not None):
            raise TypeError(
                "names=, group_by_chart=, canvas_width=, canvas_height=, "
                "legend_gap= are layout-level options for parent.legend(); "
                "on a leaf, chart.legend() takes an optional bool. To attach "
                "a layout-level legend to a single chart, compose first: "
                "(chart | pt.legend()).show()."
            )
        if args and not isinstance(args[0], bool):
            raise TypeError(
                f"chart.legend() (leaf in-frame overlay) takes an optional bool; "
                f"got {type(args[0]).__name__}."
            )
        # Record directly — `legend` is in _FRAME_METHODS but our specialized
        # method above shadows __getattr__, so we use `_record` explicitly.
        return self._record("legend", *args)

    # ---------- recording (leaf only) ----------

    def __getattr__(self, name):
        # __getattr__ is only called when normal lookup fails, so this won't
        # interfere with _layout_kind / _children / _calls etc.
        if name.startswith("_"):
            raise AttributeError(name)
        if self._layout_kind is not None:
            raise AttributeError(
                f"{name!r} is not available on a parent Chart "
                f"(layout={self._layout_kind!r}). Call it on a leaf chart instead."
            )
        spec = get_artist(name)
        if name in _FRAME_METHODS or spec is not None:
            def recorder(*args, **kwargs):
                if spec is not None and spec.frame_defaults is not None:
                    for call in spec.frame_defaults(list(args), dict(kwargs)) or ():
                        self._calls.append(call)
                self._calls.append((name, list(args), dict(kwargs)))
                return self
            return recorder
        raise AttributeError(
            f"Chart has no method {name!r}. "
            f"Registered artists: {all_artist_names()}"
        )

    def __dir__(self):
        return sorted(set(super().__dir__()) | _FRAME_METHODS | set(all_artist_names()))

    # ---------- tabular mark methods ----------

    def _record(self, name, *args, **kwargs):
        """Append one (name, args, kwargs) tuple to the recording. Used by
        the tabular methods below and by `legend()`'s leaf branch — both
        cases shadow `__getattr__`'s recorder closure with a real method,
        so they need to record explicitly."""
        self._calls.append((name, list(args), dict(kwargs)))
        return self

    def line(self, *args, x=None, y=None, hue=None, data=None, **opts):
        self._require_leaf("line")
        if x is not None or y is not None:
            self._tabular("line", "line", data, x, y, hue, opts)
        else:
            self._record("line", *args, **opts)
        return self

    def step(self, *args, x=None, y=None, hue=None, where="post", data=None, **opts):
        """Step plot — sugar over `line(curve=...)`. `where="pre"`,
        `"post"` (default), or `"mid"` map to plotlet's curve names
        (`step-before`, `step-after`, `step-mid`). matplotlib convention."""
        self._require_leaf("step")
        curve = {"pre": "step-before", "post": "step-after", "mid": "step-mid"}.get(where)
        if curve is None:
            raise ValueError(
                f"step() where= expects 'pre', 'post', or 'mid'; got {where!r}"
            )
        opts = dict(opts)
        opts["curve"] = curve
        return self.line(*args, x=x, y=y, hue=hue, data=data, **opts)

    def scatter(self, *args, x=None, y=None, hue=None, size=None, style=None,
                sizes=(20, 200), data=None, **opts):
        """Plot points. `size=<col>` maps a numeric column to per-point area
        in pixels², linearly rescaled into `sizes=(min, max)`. `style=<col>`
        cycles markers (`o`, `s`, `^`, `v`, `x`, `+`) per unique value.
        Both compose with `hue=<col>`."""
        self._require_leaf("scatter")
        if x is not None or y is not None:
            if size is not None or style is not None:
                self._scatter_with_aesthetics(data, x, y, hue, size, style, sizes, opts)
            else:
                self._tabular("scatter", "scatter", data, x, y, hue, opts)
        else:
            self._record("scatter", *args, **opts)
        return self

    def _scatter_with_aesthetics(self, data, x_col, y_col, hue, size, style, sizes, opts):
        """Compute per-point `s` and `marker` arrays from data columns, then
        emit one scatter call per hue group (or one total when no hue).
        Centralized so the hue/size/style combinatorics stay in one place."""
        df = self._resolve_data(data, "scatter")
        xs_all = to_list(df[x_col])
        ys_all = to_list(df[y_col])
        n = len(xs_all)
        s_arr   = self._compute_size_array(df[size], sizes) if size is not None else None
        mk_arr  = self._compute_style_array(df[style])      if style is not None else None

        def slice_for(idx_list):
            sub_opts = dict(opts)
            if s_arr is not None:
                sub_opts["s"] = [s_arr[i] for i in idx_list]
            if mk_arr is not None:
                sub_opts["marker"] = [mk_arr[i] for i in idx_list]
            return sub_opts

        if hue is None:
            self._record("scatter", xs_all, ys_all, **slice_for(range(n)))
            return

        hue_vals = to_list(df[hue])
        seen = []
        for v in hue_vals:
            if v not in seen:
                seen.append(v)
        opts.pop("label", None)
        for v in seen:
            idxs = [i for i, h in enumerate(hue_vals) if h == v]
            xs_g = [xs_all[i] for i in idxs]
            ys_g = [ys_all[i] for i in idxs]
            sub_opts = slice_for(idxs)
            sub_opts.pop("label", None)
            self._record("scatter", xs_g, ys_g, label=str(v), **sub_opts)

    @staticmethod
    def _compute_size_array(values, sizes):
        vals = to_list(values)
        nums = [v for v in vals if isinstance(v, (int, float)) and v == v]
        if not nums:
            return [sizes[0]] * len(vals)
        lo, hi = min(nums), max(nums)
        span = hi - lo
        s_lo, s_hi = float(sizes[0]), float(sizes[1])
        if span == 0:
            mid = (s_lo + s_hi) / 2
            return [mid if isinstance(v, (int, float)) and v == v else s_lo for v in vals]
        return [s_lo + (v - lo) / span * (s_hi - s_lo)
                if isinstance(v, (int, float)) and v == v else s_lo for v in vals]

    @staticmethod
    def _compute_style_array(values):
        cycle = ("o", "s", "^", "v", "x", "+")
        vals = to_list(values)
        seen = []
        for v in vals:
            if v not in seen:
                seen.append(v)
        mapping = {v: cycle[i % len(cycle)] for i, v in enumerate(seen)}
        return [mapping[v] for v in vals]

    def bar(self, *args, x=None, y=None, data=None, **opts):
        self._require_leaf("bar")
        if x is not None or y is not None:
            df = self._resolve_data(data, "bar")
            self._record("bar", to_list(df[x]), to_list(df[y]), **opts)
        else:
            self._record("bar", *args, **opts)
        return self

    def hist(self, *args, x=None, data=None, **opts):
        self._require_leaf("hist")
        if x is not None:
            df = self._resolve_data(data, "hist")
            self._record("hist", to_list(df[x]), **opts)
        else:
            self._record("hist", *args, **opts)
        return self

    def fill_between(self, *args, x=None, y1=None, y2=None, data=None, **opts):
        self._require_leaf("fill_between")
        if x is not None or y1 is not None or y2 is not None:
            df = self._resolve_data(data, "fill_between")
            self._record("fill_between",
                          to_list(df[x]), to_list(df[y1]), to_list(df[y2]),
                          **opts)
        else:
            self._record("fill_between", *args, **opts)
        return self

    def heatmap(self, df, *, cmap=None, vmin=None, vmax=None, norm="linear",
                center=None, xticklabels=None, yticklabels=None, legend=None):
        # DataFrame-aware companion to imshow: index/columns become tick
        # labels, row 0 sits at the top (origin="upper"), and cell centers
        # land at integer + 0.5 so a future top/left dendrogram pairs cleanly
        # via share_x / share_y. Pure pre-processing — no separate artist;
        # the rendering goes through imshow.
        self._require_leaf("heatmap")
        if hasattr(df, "values") and hasattr(df, "columns") and hasattr(df, "index"):
            cols = list(df.columns) if xticklabels is None else list(xticklabels)
            rows = list(df.index)   if yticklabels is None else list(yticklabels)
            matrix = df.values
        else:
            d = to_list_2d(df)
            n_rows = len(d); n_cols = len(d[0]) if d else 0
            cols = list(xticklabels) if xticklabels is not None else list(range(n_cols))
            rows = list(yticklabels) if yticklabels is not None else list(range(n_rows))
            matrix = d
        cols = [str(x) for x in cols]
        rows = [str(x) for x in rows]
        n_cols = len(cols); n_rows = len(rows)

        self._record("xticks", [i + 0.5 for i in range(n_cols)], cols, marks=False)
        self._record("yticks", [i + 0.5 for i in range(n_rows)], rows, marks=False)

        opts = {"origin": "upper"}
        if cmap is not None:    opts["cmap"]   = cmap
        if vmin is not None:    opts["vmin"]   = vmin
        if vmax is not None:    opts["vmax"]   = vmax
        if norm != "linear":    opts["norm"]   = norm
        if center is not None:  opts["center"] = center
        if legend is not None:  opts["legend"] = legend
        self._record("imshow", matrix, **opts)
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
        if hue is None:
            self._record(kind, to_list(df[x_col]), to_list(df[y_col]), **opts)
            return
        hue_vals = to_list(df[hue])
        xs_all = to_list(df[x_col])
        ys_all = to_list(df[y_col])
        seen: list = []
        for v in hue_vals:
            if v not in seen:
                seen.append(v)
        opts.pop("label", None)  # hue overrides any user-provided label
        for v in seen:
            xs_g = [xs_all[i] for i, h in enumerate(hue_vals) if h == v]
            ys_g = [ys_all[i] for i, h in enumerate(hue_vals) if h == v]
            self._record(kind, xs_g, ys_g, label=str(v), **opts)

    # Frame-state methods (title/xlabel/ylabel/xlim/ylim/xscale/yscale/
    # grid/legend) forward through __getattr__ above.

    # ---------- render ----------

    def to_svg(self) -> str:
        self._require_render_root()
        if self._is_parent:
            from .layout import _render_layout
            return _render_layout(self)
        if self._leaf_kind == "legend":
            from .legend import _render_standalone_legend
            return _render_standalone_legend(self)
        if self._leaf_kind == "diagram":
            from .layout_diagram import _render_standalone_diagram
            return _render_standalone_diagram(self)
        # Data leaf. Canvas grows to fit the (possibly measure-driven-
        # expanded) margin — data region stays at the user-requested size.
        # Theme is applied around the whole replay+render pipeline so
        # `_replay` picks up the right defaults (spine visibility, tick
        # direction) and every module reading from the spec dicts sees
        # the override transparently.
        with active_theme(_extract_theme(self._calls)):
            st = _replay(self._calls)
            M_eff = _effective_margin(self, st)
            W = self._data_width  + M_eff["left"] + M_eff["right"]
            H = self._data_height + M_eff["top"]  + M_eff["bottom"]
            return _render(st, W, H, M_eff)

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
        svg = self.to_svg()
        try:
            from IPython.display import HTML, display
        except ImportError:
            print(self.to_html(full_page=True))
            return
        display(HTML(svg))

    def save_svg(self, path):
        Path(path).write_text(self.to_svg())
        return self

    def save_png(self, path, *, scale: float = 1.0, dpi: int | None = None):
        """Rasterize the chart to PNG. Requires `cairosvg` (`pip install
        cairosvg`). `scale` multiplies the canvas pixel dimensions
        uniformly (e.g. `scale=2` for retina); `dpi` overrides the
        default 96 dpi rendering — both are passed straight through."""
        _rasterize(self.to_svg(), path, "png", scale=scale, dpi=dpi)
        return self

    def save_pdf(self, path):
        """Rasterize the chart to PDF. Requires `cairosvg`."""
        _rasterize(self.to_svg(), path, "pdf")
        return self

    def write_html(self, path):
        Path(path).write_text(self.to_html(full_page=True))
        return self

    def fit(self, canvas_width=None, canvas_height=None) -> "Chart":
        """Return a copy of this chart with data dimensions scaled so the
        rendered SVG fits within `canvas_width × canvas_height` pixels.

        Layout-aware: only data regions scale. Tick labels, titles, axis
        labels, spine widths, font sizes, and panel gaps stay at their
        absolute pixel sizes — the result keeps the publication look at
        every size, just with a smaller or larger data area.

        Aspect ratio is preserved (the binding constraint wins). Pass
        one dimension to scale uniformly to that axis; pass both to
        fit-within W × H. Accepts pixels (``400``) or unit-suffixed
        strings (``"4in"``, ``"10cm"``, ``"72pt"``).

        Returns a fresh Chart; the original is unchanged."""
        from copy import deepcopy
        from .layout import _natural_size, _data_total_size
        W = _to_px(canvas_width)
        H = _to_px(canvas_height)
        if W is None and H is None:
            raise ValueError(
                "Chart.fit() requires at least one of canvas_width=, canvas_height=."
            )
        if (W is not None and W <= 0) or (H is not None and H <= 0):
            raise ValueError("Chart.fit() canvas dimensions must be positive.")
        chart = deepcopy(self)
        chart._parent = None  # copy may inherit a stale parent ref
        # Direct solve. Natural figure = data_total + overhead (margins,
        # gaps, non-data leaves). Solving target = s * data_total +
        # overhead for s gives the exact factor in one pass — unless the
        # overhead changes with scale (it can, via measure-driven tick
        # label growth). Iterating absorbs that residual; in practice
        # 2–3 passes converge to within a pixel.
        for _ in range(6):
            W_nat, H_nat = _natural_size(chart)
            D_w, D_h = _data_total_size(chart)
            ratios = []
            if W is not None and D_w > 0:
                overhead_w = W_nat - D_w
                ratios.append(max(1e-3, (W - overhead_w) / D_w))
            if H is not None and D_h > 0:
                overhead_h = H_nat - D_h
                ratios.append(max(1e-3, (H - overhead_h) / D_h))
            if not ratios:
                # Nothing to scale (e.g. a sole legend leaf).
                break
            s = min(ratios)
            if abs(s - 1.0) < 5e-4:
                break
            _scale_data_dims(chart, s)
        return chart

    def _require_render_root(self):
        if self._parent is not None:
            raise RuntimeError(
                "this chart is part of a composed parent; render the parent instead."
            )


def chart(data=None, **opts) -> Chart:
    """Construct a table-bound Chart. See `Chart` for keyword arguments."""
    return Chart(data, **opts)


def _scale_data_dims(node: Chart, s: float) -> None:
    """Multiply every data leaf's `_data_width` / `_data_height` by `s`,
    rederiving `_canvas_*`. Non-data leaves (legend, diagram) keep their
    explicitly-sized canvases — their dimensional primitive isn't the
    data region. Used by `Chart.fit()` after measuring natural size."""
    if not node._is_parent:
        if node._leaf_kind == "data":
            new_w = max(1, int(round(node._data_width * s)))
            new_h = max(1, int(round(node._data_height * s)))
            node._data_width = new_w
            node._data_height = new_h
            node._orig_data_width = new_w
            node._orig_data_height = new_h
            node._canvas_width  = new_w + node._margin["left"] + node._margin["right"]
            node._canvas_height = new_h + node._margin["top"]  + node._margin["bottom"]
        return
    for child in node._children:
        if child is not None:
            _scale_data_dims(child, s)


def _rasterize(svg: str, path, fmt: str, *, scale: float = 1.0, dpi: int | None = None):
    """SVG → PNG/PDF via cairosvg. Imported lazily so users who only use
    `save_svg` / `write_html` don't pay for a heavy dependency."""
    try:
        import cairosvg
    except ImportError as e:
        raise ImportError(
            f"save_{fmt}() needs cairosvg. Install with: pip install cairosvg"
        ) from e
    fn = {"png": cairosvg.svg2png, "pdf": cairosvg.svg2pdf}[fmt]
    kw = {"bytestring": svg.encode("utf-8"), "write_to": str(path)}
    if fmt == "png":
        kw["scale"] = float(scale)
        if dpi is not None:
            kw["dpi"] = int(dpi)
    fn(**kw)


def _normalize_share_mode(axis: str, mode) -> str:
    """Map share_x / share_y param to one of "all" / "col" / "row" / "none".
    Accepts True ("all"), False / None ("none"), or the four literal strings.
    Mirrors matplotlib's `sharex` semantics."""
    if mode is True:
        return "all"
    if mode is False or mode is None:
        return "none"
    if isinstance(mode, str) and mode in ("all", "col", "row", "none"):
        return mode
    raise ValueError(
        f"share_{axis}=: expected True, False, or one of "
        f"'all', 'col', 'row', 'none'; got {mode!r}"
    )


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
