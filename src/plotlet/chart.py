"""Public API surface: the `Chart` and `Layout` types plus their constructors.

This module owns plotlet's user-facing classes:

  * **`Chart`** — single panel, leaf in any composition tree. Records artist
    calls into `_calls` and carries the data dimensions + margin needed to
    render one panel. Returned by `pt.chart(...)`.

  * **`Layout`** — a composition of `Chart`s (and other `Layout`s). Holds a
    list of children and a layout direction ("h" | "v" | "grid"). Carries no
    per-leaf render state; rendering walks the tree.

  * **`chart(...)`** / **`grid([[...]])`** — public factory functions.

`Chart` and `Layout` share a private `_Renderable` base that owns the
composition operators (`|`, `/`), output methods (`to_svg`, `show`,
`save_*`), and `fit()`. Subclasses just implement `_to_svg_unchecked`.

Composition operators:

  * `a | b` → horizontal `Layout`. Flattens when LHS is already a
    same-direction `Layout` (so `a | b | c` is a single 3-cell row, not
    nested). Mutates LHS in place; LHS should not be reused after.

  * `a / b` → vertical `Layout`. Same flattening rule.

The render pipeline (margin coordination, share-pre-pass, allocation,
SVG emission) lives in the private `_layout_engine.py`. Chart and Layout
both lazy-import from there in their render methods.

Invariants:

  * Single parent — composing a node that already has a `_parent` raises.
  * Show-on-child raises — calling `.show()` / `.to_svg()` / `_repr_html_`
    on a node with a non-None `_parent` raises with a pointer up.
"""
from __future__ import annotations

from pathlib import Path

from ._spec import _SIZESPEC, _MARGIN_FLOOR, active_theme
from .core import (
    _FRAME_METHODS, _replay, _render,
    _to_px,
)
from .draw.colors import TAB10
from .utils import to_list, to_list_2d, palette_color, resolve_aes
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


class _Renderable:
    """Private base for `Chart` and `Layout` — owns the shared rendering
    glue (composition operators, output methods, `fit()`,
    `_require_render_root`). The one variant piece is
    `_to_svg_unchecked`, which each subclass implements.

    Lives behind an underscore on purpose: users only ever see `Chart`
    and `Layout`. The base is here to remove copy-paste, not to grow a
    public hierarchy.
    """

    # Default for leaves. `Layout` overrides to True. Lets tree-walking
    # code in the layout engine distinguish parents from leaves without
    # `isinstance` checks at every site.
    _is_parent: bool = False

    # ---------- composition ----------

    def __or__(self, other) -> "Layout":
        return _compose(self, other, "h")

    def __truediv__(self, other) -> "Layout":
        return _compose(self, other, "v")

    # ---------- render ----------

    def to_svg(self) -> str:
        self._require_render_root()
        return self._to_svg_unchecked()

    def _to_svg_unchecked(self) -> str:
        raise NotImplementedError

    def to_html(self, full_page: bool = False) -> str:
        svg = self.to_svg()
        if full_page:
            return ('<!doctype html><html><head><meta charset="utf-8">'
                    '<title>plotlet</title></head>'
                    f'<body style="margin:24px">{svg}</body></html>')
        return svg

    def _repr_html_(self) -> str:
        # Overlay responsive CSS for notebook display only — `to_svg()` stays
        # byte-identical for file output. `max-width:100%` lets the figure
        # shrink with a narrow cell; the existing `width` attribute caps it
        # at natural size; `height:auto` preserves aspect via the viewBox.
        # Merged into the existing `style="background:..."` to avoid a
        # duplicate attribute (browsers would drop one).
        return self.to_svg().replace(
            'style="background:',
            'style="max-width:100%;height:auto;background:',
            1,
        )

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
        """Rasterize to PNG. Requires `cairosvg` (`pip install cairosvg`).
        `scale` multiplies the canvas pixel dimensions uniformly (e.g.
        `scale=2` for retina); `dpi` overrides the default 96 dpi
        rendering — both are passed straight through."""
        _rasterize(self.to_svg(), path, "png", scale=scale, dpi=dpi)
        return self

    def save_pdf(self, path):
        """Rasterize to PDF. Requires `cairosvg`."""
        _rasterize(self.to_svg(), path, "pdf")
        return self

    def write_html(self, path):
        Path(path).write_text(self.to_html(full_page=True))
        return self

    def fit(self, canvas_width=None, canvas_height=None):
        """Return a copy of this node with every data leaf's data region
        scaled so the rendered SVG fits within `canvas_width ×
        canvas_height` pixels.

        Layout-aware: only data regions scale. Tick labels, titles, axis
        labels, spine widths, font sizes, and panel gaps stay at their
        absolute pixel sizes — the result keeps the publication look at
        every size, just with a smaller or larger data area.

        Aspect ratio is preserved (the binding constraint wins). Pass
        one dimension to scale uniformly to that axis; pass both to
        fit-within W × H. Accepts pixels (``400``) or unit-suffixed
        strings (``"4in"``, ``"10cm"``, ``"72pt"``).

        Returns a fresh copy; the original is unchanged."""
        from copy import deepcopy
        from ._layout_engine import _natural_size, _data_total_size
        cls_name = type(self).__name__
        W = _to_px(canvas_width)
        H = _to_px(canvas_height)
        if W is None and H is None:
            raise ValueError(
                f"{cls_name}.fit() requires at least one of canvas_width=, canvas_height=."
            )
        if (W is not None and W <= 0) or (H is not None and H <= 0):
            raise ValueError(f"{cls_name}.fit() canvas dimensions must be positive.")
        node = deepcopy(self)
        node._parent = None  # copy may inherit a stale parent ref
        # Direct solve. Natural figure = data_total + overhead (margins,
        # gaps, non-data leaves). Solving target = s * data_total +
        # overhead for s gives the exact factor in one pass — unless the
        # overhead changes with scale (it can, via measure-driven tick
        # label growth). Iterating absorbs that residual; in practice
        # 2–3 passes converge to within a pixel.
        for _ in range(6):
            W_nat, H_nat = _natural_size(node)
            D_w, D_h = _data_total_size(node)
            ratios = []
            if W is not None and D_w > 0:
                overhead_w = W_nat - D_w
                ratios.append(max(1e-3, (W - overhead_w) / D_w))
            if H is not None and D_h > 0:
                overhead_h = H_nat - D_h
                ratios.append(max(1e-3, (H - overhead_h) / D_h))
            if not ratios:
                break
            s = min(ratios)
            if abs(s - 1.0) < 5e-4:
                break
            _scale_data_dims(node, s)
        return node

    def _require_render_root(self):
        if self._parent is not None:
            kind = "layout" if self._is_parent else "chart"
            raise RuntimeError(
                f"this {kind} is part of a composed parent; render the parent instead."
            )


class Chart(_Renderable):
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
                 clip: bool | None = None,
                 facecolor: str | None = None,
                 theme: str | None = None,
                 x: str | None = None, y: str | None = None,
                 fill: str | None = None,
                 color: str | None = None,
                 group: str | None = None,
                 linetype: str | None = None,
                 palette=None,
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
                "(moved to compose-time). Chain `.share_x()` on the parent "
                "layout: `pt.grid([[a, b]]).share_x()` or `(a | b).share_x()`."
            )
        if kwargs:
            raise TypeError(f"Chart() got unexpected keyword arguments: {list(kwargs)!r}")

        # ---- Render-state init (leaf-only fields used by core._render) ----
        # Resolve unit-suffixed strings (`"4in"`, `"10cm"`, …) once at the
        # boundary so internal math stays in pixels.
        data_width  = _to_px(data_width)
        data_height = _to_px(data_height)

        self._calls: list[tuple[str, list, dict]] = []
        # Default to the spec floor — render-time pre-pass grows this as
        # `_required_margin` reports what title / tick / label content
        # actually needs, so a content-light leaf (e.g. `xticks([])` cells
        # in a pair plot) doesn't reserve breathing room it won't use.
        # Explicit `margin=` raises the lower bound for users who want
        # pre-reserved space.
        self._margin = dict(margin) if margin is not None else dict(_MARGIN_FLOOR)

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
        # Chart-level aesthetic defaults (ggplot-style inheritance). Artist
        # calls with matching kwargs override; missing kwargs fall back here.
        self._aes = {"x": x, "y": y,
                     "fill": fill, "color": color, "group": group,
                     "linetype": linetype,
                     "palette": palette}
        self._parent: "Layout | None" = None
        # Share-class membership. Set by parent-level .share_x() / .share_y();
        # not user-settable on the leaf directly.
        self._share_x: "Chart | None" = None
        self._share_y: "Chart | None" = None
        # Whether this leaf opts in to joined-pair label hiding on its
        # shared axis. Default True (matches matplotlib's `sharex=True`).
        # `share_x(..., hide_labels=False)` flips this to False so the
        # share-equivalence still applies (xlim sync) but adjacent cells
        # keep their xlabel/xtick labels visible.
        self._share_hide_labels_x: bool = True
        self._share_hide_labels_y: bool = True
        # Leaf discriminator. Values: "data" (default — normal chart leaf
        # with axes and artists), "legend" (set by pt.legend(...), bypasses
        # the frame+artists render path; see legend.py), "diagram" (set by
        # pt.layout_diagram(...) — embeds a pre-rendered SVG with no panel
        # decorations).
        self._leaf_kind: str = "data"
        self._legend_sources: list[Chart] = []
        self._legend_names: dict = {}
        self._legend_group_by_chart: bool = True

        # Inset axes — small charts embedded inside this leaf's data area
        # at axes-fraction coordinates. Each entry is (rect, inset_chart).
        self._insets: list[tuple[tuple[float, float, float, float], "Chart"]] = []
        # Set on a Chart that has been registered as an inset of another.
        # Suppresses standalone `.show()` / `.to_svg()` calls.
        self._inset_owner: "Chart" | None = None
        # Cache of the effective margin from the most recent render — read
        # by an embedding parent (inset loop) to align this chart's data
        # region, not its canvas.
        self._last_M_eff: dict | None = None

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
        if clip   is not None: self.clip(clip)
        if facecolor is not None: self.facecolor(facecolor)
        if theme  is not None: self.theme(theme)

    # ---------- composition ----------

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
        leaf._margin = dict(margin) if margin is not None else dict(_MARGIN_FLOOR)
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
        leaf._share_x = None
        leaf._share_y = None
        leaf._leaf_kind = leaf_kind
        leaf._legend_sources = []
        leaf._legend_names = {}
        leaf._legend_group_by_chart = True
        leaf._insets = []
        leaf._inset_owner = None
        leaf._last_M_eff = None
        return leaf

    def legend(self, *args, position: str | None = None, **kwargs) -> "Chart":
        """Toggle the in-frame overlay legend.

        `chart.legend()` or `chart.legend(True)` turns it on; `False` off.
        `position=` places the block: `"inside"` (default) paints it
        inside the data area at top-right; `"right"`, `"left"`, `"top"`,
        `"bottom"` paint it outside the data region in reserved margin
        space.

        For a separate, layout-level legend leaf (the kind that lives in
        its own panel and harvests entries from sibling charts), use
        `pt.legend(...)` or `parent.legend(...)` on a `Layout`."""
        if "width" in kwargs or "height" in kwargs:
            raise TypeError(
                "Chart.legend() no longer accepts `width=` / `height=` "
                "(changed in 0.2.0). Use `canvas_width=` / `canvas_height=` "
                "on `pt.legend(...)` instead — those are layout-legend "
                "options, not in-frame ones."
            )
        if kwargs:
            raise TypeError(
                f"Chart.legend() got unexpected keyword arguments: {list(kwargs)!r}"
            )
        if args and not isinstance(args[0], bool):
            raise TypeError(
                f"chart.legend() (leaf in-frame overlay) takes an optional bool; "
                f"got {type(args[0]).__name__}."
            )
        if position is not None and position not in (
                "inside", "right", "left", "top", "bottom"):
            raise ValueError(
                f"chart.legend(position={position!r}) — must be one of "
                f"'inside', 'right', 'left', 'top', 'bottom'."
            )
        # Record directly — `legend` is in _FRAME_METHODS but our specialized
        # method above shadows __getattr__, so we use `_record` explicitly.
        kw = {"position": position} if position is not None else {}
        return self._record("legend", *args, **kw)

    # ---------- recording (leaf only) ----------

    def __getattr__(self, name):
        # __getattr__ is only called when normal lookup fails, so this won't
        # interfere with _calls / _data_width / etc.
        if name.startswith("_"):
            raise AttributeError(name)
        spec = get_artist(name)
        if name in _FRAME_METHODS or spec is not None:
            def recorder(*args, **kwargs):
                if spec is not None:
                    # Chart-level aesthetic inheritance — fill in missing aes
                    # from `pt.chart(df, x=, y=, color=, palette=)`.
                    for k, v in self._aes.items():
                        if v is not None and k not in kwargs:
                            kwargs[k] = v
                    # Data injection — column-referencing kwargs need a table.
                    if (self._data is not None and "data" not in kwargs
                            and any(k in kwargs for k in
                                    ("x", "y", "fill", "color", "group", "linetype"))):
                        kwargs["data"] = self._data
                if spec is not None and spec.frame_defaults is not None:
                    for call in spec.frame_defaults(list(args), dict(kwargs)) or ():
                        self._calls.append(call)
                self._calls.append((name, list(args), dict(kwargs)))
                return self
            return recorder
        ext_file = Path(__file__).parent / "extensions" / f"{name}.py"
        if ext_file.is_file():
            raise AttributeError(
                f"Chart has no method {name!r}. "
                f"Did you forget `import plotlet.extensions.{name}`? "
                f"Extensions register their artist on import."
            )
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

    def _resolve_aes(self, *, x=None, y=None, palette=None):
        """Fill in missing x/y/palette from chart-level defaults set on
        the constructor (`pt.chart(df, x=, y=, palette=)`). Per-call
        kwargs always win — only `None` slots get the chart-level value."""
        if x is None: x = self._aes.get("x")
        if y is None: y = self._aes.get("y")
        if palette is None: palette = self._aes.get("palette")
        return x, y, palette

    def line(self, *args, x=None, y=None, color=None, group=None,
             linetype=None, alpha=None, palette=None, data=None, **opts):
        x, y, palette = self._resolve_aes(x=x, y=y, palette=palette)
        if color is None: color = self._aes.get("color")
        if group is None: group = self._aes.get("group")
        if linetype is None: linetype = self._aes.get("linetype")
        if x is not None or y is not None:
            self._tabular("line", "line", data, x, y,
                          color, group, linetype, alpha, palette, opts)
        else:
            if color is not None: opts["color"] = color
            if linetype is not None: opts["linestyle"] = linetype
            if alpha is not None: opts["alpha"] = alpha
            self._record("line", *args, **opts)
        return self

    def step(self, *args, x=None, y=None, color=None, group=None,
             linetype=None, alpha=None, palette=None,
             where="post", data=None, **opts):
        """Step plot — sugar over `line(curve=...)`. `where="pre"`,
        `"post"` (default), or `"mid"` map to plotlet's curve names
        (`step-before`, `step-after`, `step-mid`). matplotlib convention."""
        curve = {"pre": "step-before", "post": "step-after", "mid": "step-mid"}.get(where)
        if curve is None:
            raise ValueError(
                f"step() where= expects 'pre', 'post', or 'mid'; got {where!r}"
            )
        opts = dict(opts)
        opts["curve"] = curve
        return self.line(*args, x=x, y=y, color=color, group=group,
                         linetype=linetype, palette=palette, data=data, **opts)

    def scatter(self, *args, x=None, y=None, color=None, group=None,
                alpha=None, palette=None,
                c=None, cmap=None, vmin=None, vmax=None, norm=None,
                size=None, style=None, sizes=(20, 200), data=None, **opts):
        """Plot points. `size=<col>` maps a numeric column to per-point area
        in pixels², linearly rescaled into `sizes=(min, max)`. `style=<col>`
        cycles markers (`o`, `s`, `^`, `v`, `x`, `+`) per unique value.
        Both compose with `color=<col>` (one color per unique value).
        `palette=` pins categories to colors — accepts a dict
        (`{"A": "#3F97C5", ...}`) or a list indexed by category-appearance
        order.

        For numeric color mapping use `c=<col_or_list>` + `cmap=`, with
        optional `vmin`/`vmax`/`norm='linear'|'log'`. `c=` is mutually
        exclusive with a column-driven `color=` — they're alternative
        color sources."""
        x, y, palette = self._resolve_aes(x=x, y=y, palette=palette)
        if color is None: color = self._aes.get("color")
        if group is None: group = self._aes.get("group")
        df_for_aes = data if data is not None else self._data
        color_kind, _ = resolve_aes(df_for_aes, color)
        if c is not None and color_kind == "column":
            raise ValueError(
                "scatter accepts either color=<col> (categorical) or "
                "c= (numeric), not both — they're alternative color sources."
            )
        if c is not None:
            df = data if data is not None else self._data
            if isinstance(c, str):
                if df is None:
                    raise ValueError(
                        "scatter c=<col_name> requires a bound table or data= kwarg."
                    )
                c = to_list(df[c])
            else:
                c = to_list(c)
            opts = dict(opts)
            opts["c"] = c
            if cmap is not None: opts["cmap"] = cmap
            if vmin is not None: opts["vmin"] = vmin
            if vmax is not None: opts["vmax"] = vmax
            if norm is not None: opts["norm"] = norm
        if x is not None or y is not None:
            if size is not None or style is not None:
                self._scatter_with_aesthetics(data, x, y, color, group, alpha,
                                              palette, size, style, sizes, opts)
            elif c is not None:
                df = self._resolve_data(data, "scatter")
                self._record("scatter", to_list(df[x]), to_list(df[y]), **opts)
            else:
                # scatter ignores `linetype` (no line to dash) — pass None
                # so it never appears in opts.
                self._tabular("scatter", "scatter", data, x, y,
                              color, group, None, alpha, palette, opts)
        else:
            if color is not None: opts["color"] = color
            if alpha is not None: opts["alpha"] = alpha
            self._record("scatter", *args, **opts)
        return self

    def _scatter_with_aesthetics(self, data, x_col, y_col, color, group, alpha,
                                 palette, size, style, sizes, opts):
        """Compute per-point `s` and `marker` arrays from data columns, then
        emit one scatter call per (color, group, alpha) tuple. Centralized
        so the color/group/alpha/size/style combinatorics stay in one place."""
        df = self._resolve_data(data, "scatter")
        xs_all = to_list(df[x_col])
        ys_all = to_list(df[y_col])
        n = len(xs_all)
        s_arr   = self._compute_size_array(df[size], sizes) if size is not None else None
        mk_arr  = self._compute_style_array(df[style])      if style is not None else None
        alphas = opts.pop("alphas", self._DEFAULT_ALPHA_RANGE)

        def slice_for(idx_list):
            sub_opts = dict(opts)
            if s_arr is not None:
                sub_opts["s"] = [s_arr[i] for i in idx_list]
            if mk_arr is not None:
                sub_opts["marker"] = [mk_arr[i] for i in idx_list]
            return sub_opts

        color_kind, color_value = resolve_aes(df, color)
        group_kind, group_value = resolve_aes(df, group)
        alpha_kind, alpha_value = resolve_aes(df, alpha)

        if (color_kind == "literal" and group_kind == "literal"
                and alpha_kind == "literal"):
            sub_opts = slice_for(range(n))
            if color_value is not None:
                sub_opts["color"] = color_value
            if alpha_value is not None:
                sub_opts["alpha"] = alpha_value
            self._record("scatter", xs_all, ys_all, **sub_opts)
            return

        color_vec = color_value if color_kind == "column" else [None] * n
        group_vec = group_value if group_kind == "column" else [None] * n
        alpha_vec = alpha_value if alpha_kind == "column" else [None] * n
        color_levels: list = []
        for v in color_vec:
            if v not in color_levels:
                color_levels.append(v)
        alpha_levels: list = []
        for v in alpha_vec:
            if v not in alpha_levels:
                alpha_levels.append(v)
        triples: list = []
        for k in zip(color_vec, group_vec, alpha_vec):
            if k not in triples:
                triples.append(k)

        opts.pop("label", None)
        labeled: set = set()
        for ck, gk, ak in triples:
            idxs = [j for j in range(n)
                    if color_vec[j] == ck and group_vec[j] == gk
                    and alpha_vec[j] == ak]
            xs_g = [xs_all[j] for j in idxs]
            ys_g = [ys_all[j] for j in idxs]
            sub_opts = slice_for(idxs)
            sub_opts.pop("label", None)
            if color_kind == "column":
                idx = color_levels.index(ck)
                sub_opts["color"] = palette_color(palette, ck, idx) or TAB10[idx % 10]
                if ck not in labeled:
                    sub_opts["label"] = str(ck)
                    labeled.add(ck)
            elif color_value is not None:
                sub_opts["color"] = color_value
            if alpha_kind == "column":
                sub_opts["alpha"] = self._alpha_for_level(
                    alpha_levels.index(ak), len(alpha_levels), alphas)
            elif alpha_value is not None:
                sub_opts["alpha"] = alpha_value
            self._record("scatter", xs_g, ys_g, **sub_opts)

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

    def bar(self, *args, x=None, y=None, fill=None, color=None,
            palette=None, data=None, **opts):
        x, y, palette = self._resolve_aes(x=x, y=y, palette=palette)
        if fill is None: fill = self._aes.get("fill")
        if color is None: color = self._aes.get("color")
        long_form = (x is not None or y is not None
                     or fill is not None or data is not None)
        if long_form:
            # Artist's long-form path resolves `fill=` as literal-vs-column
            # and aggregates duplicate (x, group) rows.
            df = self._resolve_data(data, "bar")
            kw = {"data": df}
            if x is not None: kw["x"] = x
            if y is not None: kw["y"] = y
            if fill is not None: kw["fill"] = fill
            if color is not None: kw["color"] = color
            if palette is not None: kw["palette"] = palette
            self._record("bar", **kw, **opts)
        else:
            if color is not None: opts["color"] = color
            if fill is not None: opts["fill"] = fill
            if palette is not None: opts["palette"] = palette
            self._record("bar", *args, **opts)
        return self

    def hist(self, *args, x=None, fill=None, color=None,
             palette=None, data=None, **opts):
        x, _, palette = self._resolve_aes(x=x, palette=palette)
        if fill is None: fill = self._aes.get("fill")
        if color is None: color = self._aes.get("color")
        long_form = (x is not None or fill is not None or data is not None)
        if long_form:
            # Artist's long-form path resolves `fill=` as literal-vs-column
            # and shares bin edges across groups.
            df = self._resolve_data(data, "hist")
            kw = {"data": df}
            if x is not None: kw["x"] = x
            if fill is not None: kw["fill"] = fill
            if color is not None: kw["color"] = color
            if palette is not None: kw["palette"] = palette
            self._record("hist", **kw, **opts)
        else:
            if color is not None: opts["color"] = color
            if fill is not None: opts["fill"] = fill
            if palette is not None: opts["palette"] = palette
            self._record("hist", *args, **opts)
        return self

    def fill_between(self, *args, x=None, y1=None, y2=None, data=None, **opts):
        # Aes inheritance: x can come from chart-level x= default.
        x = x if x is not None else self._aes.get("x")
        if x is not None or y1 is not None or y2 is not None:
            df = self._resolve_data(data, "fill_between")
            self._record("fill_between",
                          to_list(df[x]), to_list(df[y1]), to_list(df[y2]),
                          **opts)
        else:
            self._record("fill_between", *args, **opts)
        return self

    def heatmap(self, df, *, cmap=None, vmin=None, vmax=None, norm="linear",
                center=None, xticklabels=None, yticklabels=None, legend=None,
                annot=False, fmt=".2g", annot_color="auto", annot_fontsize=10):
        # DataFrame-aware companion to imshow: index/columns become tick
        # labels, row 0 sits at the top (origin="upper"), and cell centers
        # land at integer + 0.5 so a future top/left dendrogram pairs cleanly
        # via share_x / share_y. Pure pre-processing — no separate artist;
        # the rendering goes through imshow.
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
        if annot is not False and annot is not None:
            opts["annot"] = annot
            opts["fmt"] = fmt
            opts["annot_color"] = annot_color
            opts["annot_fontsize"] = annot_fontsize
        self._record("imshow", matrix, **opts)
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

    _LINETYPE_CYCLE = (None, "--", ":", "-.")
    _DEFAULT_ALPHA_RANGE = (0.3, 1.0)

    @staticmethod
    def _alpha_for_level(idx, n_levels, alphas):
        """Map a discrete level index to an alpha value within `alphas`
        (a `(lo, hi)` tuple). One level → the high end; otherwise
        linearly spaced."""
        lo, hi = alphas
        if n_levels <= 1:
            return hi
        return lo + (hi - lo) * idx / (n_levels - 1)

    def _tabular(self, public_name, kind, data, x_col, y_col,
                 color, group, linetype, alpha, palette, opts):
        """Long-form table → one or more artist records. Splits into one
        record per unique `(color, group, linetype)` tuple, where each
        aes may be None, a literal, or a column name.

        Color: column → palette-resolved per level, one legend entry per
        level (first sub-record of each level carries the label).
        Group: invisible split — never burns a color or a legend entry.
        Linetype: column → dash cycle per level. When `linetype` maps the
        same column as `color`, the existing color legend swatches inherit
        the dash pattern (via `linestyle` on the labeled sub-record).
        """
        df = self._resolve_data(data, public_name)
        color_kind, color_value = resolve_aes(df, color)
        group_kind, group_value = resolve_aes(df, group)
        ltype_kind, ltype_value = resolve_aes(df, linetype)
        alpha_kind, alpha_value = resolve_aes(df, alpha)
        alphas = opts.pop("alphas", self._DEFAULT_ALPHA_RANGE)
        xs_all = to_list(df[x_col])
        ys_all = to_list(df[y_col])
        n = len(xs_all)

        # Fast path: no column-driven splits — single record.
        if (color_kind == "literal" and group_kind == "literal"
                and ltype_kind == "literal" and alpha_kind == "literal"):
            if color_value is not None:
                opts["color"] = color_value
            if ltype_value is not None:
                opts["linestyle"] = ltype_value
            if alpha_value is not None:
                opts["alpha"] = alpha_value
            self._record(kind, xs_all, ys_all, **opts)
            return

        color_vec = color_value if color_kind == "column" else [None] * n
        group_vec = group_value if group_kind == "column" else [None] * n
        ltype_vec = ltype_value if ltype_kind == "column" else [None] * n
        alpha_vec = alpha_value if alpha_kind == "column" else [None] * n
        color_levels: list = []
        for v in color_vec:
            if v not in color_levels:
                color_levels.append(v)
        ltype_levels: list = []
        for v in ltype_vec:
            if v not in ltype_levels:
                ltype_levels.append(v)
        alpha_levels: list = []
        for v in alpha_vec:
            if v not in alpha_levels:
                alpha_levels.append(v)
        quads: list = []
        for k in zip(color_vec, group_vec, ltype_vec, alpha_vec):
            if k not in quads:
                quads.append(k)

        opts.pop("label", None)  # column-driven grouping overrides any user label
        labeled: set = set()
        for ck, gk, lk, ak in quads:
            idxs = [j for j in range(n)
                    if color_vec[j] == ck and group_vec[j] == gk
                    and ltype_vec[j] == lk and alpha_vec[j] == ak]
            xs_g = [xs_all[j] for j in idxs]
            ys_g = [ys_all[j] for j in idxs]
            sub_opts = dict(opts)
            if color_kind == "column":
                idx = color_levels.index(ck)
                sub_opts["color"] = palette_color(palette, ck, idx) or TAB10[idx % 10]
                if ck not in labeled:
                    sub_opts["label"] = str(ck)
                    labeled.add(ck)
            elif color_value is not None:
                sub_opts["color"] = color_value
            if ltype_kind == "column":
                ls = self._LINETYPE_CYCLE[ltype_levels.index(lk) % len(self._LINETYPE_CYCLE)]
                if ls is not None:
                    sub_opts["linestyle"] = ls
            elif ltype_value is not None:
                sub_opts["linestyle"] = ltype_value
            if alpha_kind == "column":
                sub_opts["alpha"] = self._alpha_for_level(
                    alpha_levels.index(ak), len(alpha_levels), alphas)
            elif alpha_value is not None:
                sub_opts["alpha"] = alpha_value
            self._record(kind, xs_g, ys_g, **sub_opts)

    # Frame-state methods (title/xlabel/ylabel/xlim/ylim/xscale/yscale/
    # grid/legend) forward through __getattr__ above.

    def inset(self, rect, **chart_opts) -> "Chart":
        """Embed a small Chart inside this leaf at axes-fraction coordinates.

        `rect=(x, y, w, h)` is in axes-fraction units (0..1) of this leaf's
        data area, with the origin at the *bottom-left* (matplotlib's
        `inset_axes` convention). Returns a fresh Chart configured to
        render at the requested pixel size — record artists on it normally.
        Render the parent leaf; the inset draws on top of the parent's
        artists with its own scales and frame."""
        x, y, w, h = rect
        if not (0 <= w <= 1 and 0 <= h <= 1):
            raise ValueError(
                f"inset rect width/height must be in [0, 1]; got {rect}"
            )
        dw = max(1, int(round(self._data_width  * w)))
        dh = max(1, int(round(self._data_height * h)))
        # Inset gets a tight margin by default — small canvas, no room
        # for long axis labels unless the user sizes the inset bigger.
        inset = Chart(data_width=dw, data_height=dh,
                      margin=dict(_SIZESPEC["inset_margin"]),
                      **chart_opts)
        inset._inset_owner = self
        self._insets.append((tuple(rect), inset))
        return inset

    # ---------- render ----------

    def _to_svg_unchecked(self) -> str:
        """Render path that skips the root check — used by parents
        embedding this chart (insets, layout panels)."""
        if self._leaf_kind == "legend":
            from .legend import _render_standalone_legend
            return _render_standalone_legend(self)
        if self._leaf_kind == "diagram":
            from .layout_diagram import _render_standalone_diagram
            return _render_standalone_diagram(self)
        # Data leaf. Route through the same pre-pass parents use — single
        # leaf is a degenerate single-cell case; share-scaling, collapse
        # annotation, and margin coordination all no-op for it, leaving
        # just the measure-driven margin computation. One pipeline means
        # outside-legend reservation and similar layout-level concerns can
        # live in one place. `_build_panel_opts` applies theme per leaf
        # during replay; the final `_render` call is themed again because
        # `_render` reads `_FONTSPEC` / `SPEC` inline.
        from ._layout_engine import _build_panel_opts
        panel_opts, states = _build_panel_opts(self)
        po = panel_opts[id(self)]
        M_eff = po.M_eff
        self._last_M_eff = M_eff
        W = self._data_width  + M_eff["left"] + M_eff["right"]
        H = self._data_height + M_eff["top"]  + M_eff["bottom"]
        with active_theme(_extract_theme(self._calls)):
            return _render(states[id(self)], W, H, M_eff)

    def _require_render_root(self):
        super()._require_render_root()
        if self._inset_owner is not None:
            raise RuntimeError(
                "this chart is an inset; render the owning parent leaf instead."
            )


class Layout(_Renderable):
    """A composition of charts — the parent type returned by `|`, `/`,
    and `pt.grid()`. Layouts coordinate panel margins, share scales
    across leaves, and emit one outer SVG containing each leaf rendered
    into its allocated rect.

    `Layout` has no data of its own; record artists on the individual
    `Chart` leaves inside the layout, not on the layout itself. Layouts
    compose further with `|` and `/` to nest layouts (one set of gaps
    per nesting level).
    """

    # Override the base default. Lets tree-walking code in the layout
    # engine treat parents and leaves uniformly via `if x._is_parent:`.
    _is_parent: bool = True

    def __init__(self, kind: str, children: list):
        self._layout_kind: str = kind          # "h" | "v" | "grid"
        self._children: list = list(children)
        self._parent: "Layout | None" = None
        self._gap: float | None = None
        # Grid-specific shape; left at None for h/v parents.
        self._grid_rows: int | None = None
        self._grid_cols: int | None = None
        # Set by `share_x("col")` / `share_y("row")` on h/v compositions
        # — tells the layout engine to treat this node as a virtual grid
        # and coordinate margins per column/row across sub-layouts.
        # Opt-in so plain `(a | b) / (c | d)` keeps natural per-row sizing.
        self._virtual_grid_aligned: bool = False
        # Wire children's back-link so `_require_render_root` and share
        # resolution can walk up.
        for child in self._children:
            if child is not None:
                child._parent = self

    # ---------- parent-only ----------

    def share_x(self, mode: bool | str = "all", *,
                hide_labels: bool = True) -> "Layout":
        """Wire up x-axis sharing across this layout's leaves. Mutates
        the leaves' private share state so layout.py's pre-pass
        coordinates them. Returns self for chaining.

        `hide_labels=True` (default, matches matplotlib's `sharex=True`)
        also suppresses xlabel and x-tick labels on joined-pair sides so
        adjacent shared panels read as one frame. Set `hide_labels=False`
        to keep the share equivalence (xlim auto-syncs, columns align in
        `"col"` mode) but render every panel's xlabel and tick labels —
        useful when the same axis range carries different meaning per
        row, or when the top row needs to own the xlabel.

        For pure column-width alignment without axis equivalence at all,
        use `align_x()` instead.
        """
        self._apply_share("x", mode, hide_labels=hide_labels)
        return self

    def share_y(self, mode: bool | str = "all", *,
                hide_labels: bool = True) -> "Layout":
        """Wire up y-axis sharing across this layout's leaves. See `share_x`."""
        self._apply_share("y", mode, hide_labels=hide_labels)
        return self

    def align_x(self, mode: bool | str = "col") -> "Layout":
        """Coordinate per-column widths across rows without sharing the
        x-axis or hiding any labels.

        On a v-of-h composition with `mode="col"`, flips
        `_virtual_grid_aligned` so the layout engine pads margins and
        canvases per column across rows — the same width alignment
        `share_x("col")` would do, minus the share equivalence and
        joined-pair label hiding. Use when rows happen to have N
        matching columns and you want them lined up visually, but
        each row's x-axis is its own thing (different xlim, different
        meaning, or each row keeps its xlabel/tick labels)."""
        self._apply_align("x", mode)
        return self

    def align_y(self, mode: bool | str = "row") -> "Layout":
        """Coordinate per-row heights across columns. See `align_x`."""
        self._apply_align("y", mode)
        return self

    def gap(self, value: int | float) -> "Layout":
        """Override the inter-panel gap. Falls back to
        `spec.json:layout.gap` (default 0) when unset. Applies uniformly
        — joined share-pairs get the same gap as non-joined siblings.
        Negative values are accepted (panels overlap)."""
        self._gap = float(value)
        return self

    def touch(self) -> "Layout":
        """Set the gap so adjacent panels' spines coincide. Useful for
        joined share-pairs whose joined-side margins are pure floor:
        the negative gap `-2 * margin_floor` cancels both floors exactly,
        making the two spines render as one continuous line.

        Auto-adapts to the active theme's `margin_floor`."""
        self._gap = -2.0 * _MARGIN_FLOOR["top"]
        return self

    def _apply_share(self, axis: str, mode, *,
                     hide_labels: bool = True) -> None:
        norm = _normalize_share_mode(axis, mode)
        if norm == "none":
            return
        if norm in ("col", "row") and self._layout_kind != "grid":
            # Also accepted: v-of-h composition with share_x("col"), or
            # h-of-v composition with share_y("row"). These are virtual
            # grids where each child is a row (or column) of equal length;
            # `_compute_share_classes` validates the shape match.
            expected_outer = "v" if norm == "col" else "h"
            if self._layout_kind != expected_outer:
                raise ValueError(
                    f"share_{axis}={norm!r} requires a pt.grid layout, or "
                    f"a {expected_outer!r} composition of "
                    f"{'h' if norm == 'col' else 'v'}-sub-layouts; got "
                    f"{self._layout_kind!r}."
                )
            # Mark for `_coordinate_margins` to run the per-column /
            # per-row coordination — alignment is opt-in so the user
            # can't be surprised when sub-layout widths differ.
            self._virtual_grid_aligned = True
        classes = self._compute_share_classes(norm)
        attr = "_share_x" if axis == "x" else "_share_y"
        hide_attr = f"_share_hide_labels_{axis}"
        for cls in classes:
            if len(cls) < 2:
                continue
            anchor = cls[0]
            for leaf in cls[1:]:
                setattr(leaf, attr, anchor)
            if not hide_labels:
                # Flag every leaf in the class (anchor included) so the
                # joined-pair walk skips hide_* / suppress_*_labels on
                # both sides of every joint in this share class.
                for leaf in cls:
                    setattr(leaf, hide_attr, False)

    def _apply_align(self, axis: str, mode) -> None:
        """Geometric counterpart to `_apply_share` — flips
        `_virtual_grid_aligned` so per-column/per-row coordination runs,
        but never wires share chains or touches `_share_hide_labels_*`."""
        norm = _normalize_share_mode(axis, mode)
        if norm in ("none", "all"):
            # `align_x("all")` doesn't have a meaningful geometric reading
            # (every leaf shares some axis at once). Restrict to col/row.
            raise ValueError(
                f"align_{axis}={mode!r}: expected 'col' or 'row'."
            )
        if self._layout_kind != "grid":
            expected_outer = "v" if norm == "col" else "h"
            if self._layout_kind != expected_outer:
                raise ValueError(
                    f"align_{axis}={norm!r} requires a pt.grid layout, or "
                    f"a {expected_outer!r} composition of "
                    f"{'h' if norm == 'col' else 'v'}-sub-layouts; got "
                    f"{self._layout_kind!r}."
                )
        self._virtual_grid_aligned = True

    def _compute_share_classes(self, mode: str) -> list[list]:
        from ._layout_engine import _iter_leaves

        def cell_leaves(cell):
            if cell is None:
                return []
            if cell._is_parent:
                return [l for l in _iter_leaves(cell) if l._leaf_kind == "data"]
            return [cell] if cell._leaf_kind == "data" else []

        if mode == "all":
            return [[l for l in _iter_leaves(self) if l._leaf_kind == "data"]]

        # Grid layout: original semantics — children laid out in row-major
        # order with explicit (rows, cols) shape.
        if self._layout_kind == "grid":
            rows, cols = self._grid_rows, self._grid_cols
            children = self._children
            if mode == "col":
                return [
                    [l for r in range(rows) for l in cell_leaves(children[r * cols + c])]
                    for c in range(cols)
                ]
            return [
                [l for c in range(cols) for l in cell_leaves(children[r * cols + c])]
                for r in range(rows)
            ]

        # Composition layout treated as a virtual grid:
        #   share_x("col") on v-of-h → group by column index across rows.
        #   share_y("row") on h-of-v → group by row index across columns.
        # Every child must be a same-kind parent and all must agree on
        # cell count — otherwise the column/row mapping is ambiguous.
        inner = "h" if self._layout_kind == "v" else "v"
        axis_word = "x" if mode == "col" else "y"
        counts = []
        for ch in self._children:
            if not ch._is_parent or ch._layout_kind != inner:
                what = (f"{ch._layout_kind!r} layout" if ch._is_parent
                        else "bare chart")
                raise ValueError(
                    f"share_{axis_word}({mode!r}) on a {self._layout_kind!r} "
                    f"composition requires every child to be an {inner!r} "
                    f"sub-layout; found a {what}."
                )
            counts.append(len(ch._children))
        if len(set(counts)) != 1:
            raise ValueError(
                f"share_{axis_word}({mode!r}): every sub-layout must have "
                f"the same number of cells; got {counts}."
            )
        n = counts[0]
        return [
            [l for ch in self._children for l in cell_leaves(ch._children[i])]
            for i in range(n)
        ]

    # ---------- render ----------

    def _to_svg_unchecked(self) -> str:
        from ._layout_engine import _render_layout
        return _render_layout(self)


def chart(data=None, **opts) -> Chart:
    """Construct a table-bound Chart. See `Chart` for keyword arguments."""
    return Chart(data, **opts)


def grid(cells: list[list],
         gap: int | float | None = None,
         **kwargs) -> "Layout":
    """Build a grid-layout `Layout` from a list-of-lists of cells.

    Each cell is either a `Chart` or `None` (empty). All rows must have
    the same number of columns. The grid does **no proportional
    redistribution** — each column's width is the max natural canvas
    width across cells in that column; each row's height is the max
    natural canvas height across cells in that row. To make a column
    twice as wide as another, set `data_width=` directly on the leaf
    charts; the grid then sums their natural canvases plus per-boundary
    gaps.

    For axis sharing, chain `.share_x("col"/"row"/"all")` /
    `.share_y(...)` on the returned `Layout`. The constructor takes only
    the structural arguments (`cells`, `gap`); behavior knobs live on
    methods so they compose uniformly across grid-built and `|`/`/`-built
    layouts.
    """
    # Migration error — `widths=` / `heights=` were canvas-ratio overrides
    # in 0.1.x. With body-size-first composition there's no longer a
    # well-defined "redistribute the canvas" operation: leaves carry data,
    # parents derive canvas. Set per-leaf `data_width=` to control sizing.
    if "widths" in kwargs or "heights" in kwargs:
        raise TypeError(
            "pt.grid() no longer accepts `widths=` / `heights=` (changed "
            "in 0.2.0). To make a column 2× wider than another, set "
            "`data_width=` on each leaf — e.g. "
            "`pt.chart(data_width=200) | pt.chart(data_width=100)`. The grid "
            "sums each cell's natural canvas; per-leaf data sizes give you "
            "all the control ratios used to."
        )
    # Migration error — `share_x=` / `share_y=` were constructor kwargs
    # that duplicated the post-construction methods. Methods scale better
    # to new options (e.g. `share_x("col", hide_labels=False)`).
    if "share_x" in kwargs or "share_y" in kwargs:
        raise TypeError(
            "pt.grid() no longer accepts `share_x=` / `share_y=` kwargs. "
            "Call the methods after construction instead: "
            "`pt.grid([[...]]).share_x('col').share_y('row')`. This keeps "
            "one configuration path across grid- and `|`/`/`-built layouts "
            "and leaves room for options like `hide_labels=`."
        )
    if kwargs:
        raise TypeError(f"pt.grid() got unexpected keyword arguments: {list(kwargs)!r}")
    if not cells or not isinstance(cells, list):
        raise ValueError("pt.grid expects a non-empty list of rows.")
    rows = len(cells)
    cols = len(cells[0])
    if any(len(row) != cols for row in cells):
        raise ValueError("pt.grid rows must all have the same number of columns.")

    flat: list[Chart | None] = []
    for row in cells:
        for cell in row:
            if cell is not None and not isinstance(cell, Chart):
                raise TypeError(
                    f"pt.grid cells must be Chart or None; got {type(cell).__name__}."
                )
            if cell is not None and cell._parent is not None:
                raise ValueError(
                    "Each chart can be in at most one parent. "
                    "Compose fresh charts, or copy your sub-assembly."
                )
            flat.append(cell)

    parent = Layout("grid", flat)      # row-major; may contain None
    parent._grid_rows = rows
    parent._grid_cols = cols
    if gap is not None:
        parent._gap = float(gap)
    return parent


def _scale_data_dims(node, s: float) -> None:
    """Multiply every data leaf's `_data_width` / `_data_height` by `s`,
    rederiving `_canvas_*`. Non-data leaves (legend, diagram) keep their
    explicitly-sized canvases — their dimensional primitive isn't the
    data region. Used by `Chart.fit()` / `Layout.fit()`."""
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


def _compose(left, right, kind: str):
    """Implement `|` / `/`. Either operand may be a `Chart` (leaf) or a
    `Layout` (parent). Flattens same-direction parents in place on LHS
    so `a | b | c` is one row of three rather than nested pairs."""
    if not isinstance(right, (Chart, Layout)):
        return NotImplemented
    if left._parent is not None or right._parent is not None:
        raise ValueError(
            "Each chart can be in at most one parent. "
            "Compose fresh charts, or copy your sub-assembly."
        )
    # Flatten LHS if it's a same-direction parent.
    if left._is_parent and left._layout_kind == kind:
        if right._is_parent and right._layout_kind == kind:
            for child in right._children:
                child._parent = left
            left._children.extend(right._children)
        else:
            left._children.append(right)
            right._parent = left
        return left
    return Layout(kind, [left, right])


