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

import re
from pathlib import Path

from ._spec import _SIZESPEC, _MARGIN_FLOOR, _OUTER_MARGIN, _LAYOUTSPEC, active_theme
from .core import (
    _FRAME_METHODS, _replay, _render,
    _to_px,
)
from .utils import to_list_2d
from .registry import get_artist, all_artist_names


# Strip every `data-plotlet-*="..."` attribute. The leading space is part of
# the match so we don't leave a double space behind — every attr is emitted
# with a leading separator (see `_attrs_str` in core.py and the inline
# `f'data-plotlet-...'` writes in `_layout_engine.py`, which sit after another
# attr or end up with their own trailing space).
_CLEAN_ATTR_RE = re.compile(r' data-plotlet-[\w-]+="[^"]*"')
# Strip `<metadata data-plotlet-payload="...">...</metadata>` blocks. CDATA
# content can include `<` `>` `&` but `json.dumps` won't emit `]]>` (see
# `_metadata_block` in core.py), so the non-greedy match is safe.
_CLEAN_METADATA_RE = re.compile(
    r'<metadata data-plotlet-payload="[^"]*">.*?</metadata>', re.DOTALL
)


def _strip_plotlet_attrs(svg: str) -> str:
    """Remove every `data-plotlet-*` attribute and `<metadata
    data-plotlet-payload=...>` block from a rendered SVG. Used by
    `to_svg(clean=True)` for users who want a plain SVG with no AI/schema
    metadata. Class names like `plotlet-artist` stay — they're structural,
    not metadata."""
    svg = _CLEAN_METADATA_RE.sub("", svg)
    svg = _CLEAN_ATTR_RE.sub("", svg)
    return svg


def _extract_theme(calls) -> str | None:
    """Last-call-wins scan for the active theme. Returns `None` when the
    chart never set a theme — `active_theme(None)` is a passthrough that
    leaves the spec dicts on their current values."""
    name = None
    for call in calls:
        # Calls are 3-tuples from user code or 4-tuples from frame_defaults
        # (see Chart.__getattr__). Theme is always user-set, but iterating
        # the same list requires tolerating both shapes.
        call_name, args = call[0], call[1]
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

    def to_svg(self, *, clean: bool = False) -> str:
        """Render to an SVG string. `clean=True` strips every
        `data-plotlet-*` attribute and metadata block — use it when you
        want a plain SVG for embedding or sharing and don't need the
        AI/schema surface documented in `docs/AI_ATTRS.md`."""
        self._require_render_root()
        svg = self._to_svg_unchecked(outer=dict(_OUTER_MARGIN))
        if clean:
            svg = _strip_plotlet_attrs(svg)
        return svg

    def regions(self) -> list[dict]:
        """Return the chrome regions emitted during a render of this
        chart — title, axis labels, ticks, spines, panel, legend and
        its sub-elements. Each entry is `{"kind", "bbox", "name",
        "meta"}` where `bbox` is in outer-SVG coords and `meta` may
        carry `polygon` (precise rotated corners), `text`, etc. Filter
        with list comprehensions, e.g. `[r for r in c.regions() if
        r["name"] == "title"]`.

        Data marks (scatter dots, bar rects, heatmap cells) are
        deliberately excluded — this surface is for layout debugging
        (overlap, clipping), not data inspection. Re-renders under a
        region-collecting sink and discards the SVG: cheap,
        deterministic, no chart state change."""
        from . import _regions
        self._require_render_root()
        with _regions.collecting() as sink:
            self._to_svg_unchecked(outer=dict(_OUTER_MARGIN))
        return [{"kind": r.kind, "bbox": r.bbox, "name": r.name, "meta": r.meta}
                for r in sink.regions]

    def _to_svg_unchecked(self, *, outer=None) -> str:
        raise NotImplementedError

    def to_html(self, full_page: bool = False) -> str:
        svg = self.to_svg()
        if full_page:
            return ('<!doctype html><html><head><meta charset="utf-8">'
                    '<title>plotlet</title></head>'
                    f'<body style="margin:24px">{svg}</body></html>')
        return svg

    def _repr_html_(self) -> str:
        # Overlay responsive CSS for notebook display only — the file
        # output from `to_svg()` is not touched. `max-width:100%` lets the
        # figure shrink with a narrow cell; the existing `width` attribute
        # caps it at natural size; `height:auto` preserves aspect via the
        # viewBox. Merged into the existing `style="background:..."` to
        # avoid a duplicate attribute (browsers would drop one).
        return self.to_svg().replace(
            'style="background:',
            'style="max-width:100%;height:auto;background:',
            1,
        )

    def show(self):
        self._require_render_root()
        try:
            from IPython.display import HTML, display
        except ImportError:
            print(self.to_html(full_page=True))
            return
        display(HTML(self._repr_html_()))

    def save_svg(self, path, *, clean: bool = False):
        Path(path).write_text(self.to_svg(clean=clean))
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
                 linestyle: str | None = None,
                 palette=None,
                 **kwargs):
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
        # Chart-level aesthetic defaults inherited by artist calls — set
        # once at chart construction, overridden by per-artist kwargs.
        self._aes = {"x": x, "y": y,
                     "fill": fill, "color": color, "group": group,
                     "linestyle": linestyle,
                     "palette": palette}
        self._parent: "Layout | None" = None
        # Share-class membership. Set by parent-level .share_x() / .share_y();
        # not user-settable on the leaf directly.
        self._share_x: "Chart | None" = None
        self._share_y: "Chart | None" = None
        # Whether this leaf opts in to joined-pair label hiding on its
        # shared axis. Default True. `share_x(..., hide_labels=False)`
        # flips this to False so the share-equivalence still applies
        # (xlim sync) but adjacent cells keep their xlabel/xtick labels
        # visible.
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

        # Attachments — user-defined sub-charts placed in this chart's
        # margin space, like extended axis decorations. Index 0 is closest
        # to the host's data area; later entries extend further out.
        # Left/right attachments auto-share y with this host (heights
        # align, row order propagates); top/bottom auto-share x. Composing
        # the host with `|` / `/` treats host-with-attachments as one
        # block — peer composition is unchanged.
        self._attached_left:  list["Chart"] = []
        self._attached_right: list["Chart"] = []
        self._attached_above: list["Chart"] = []
        self._attached_below: list["Chart"] = []
        # Set on a Chart that has been attached to a host. Tells the
        # share-scaling pre-pass to lock only the shared dim and preserve
        # the user's perpendicular dim (no aspect-ratio scaling).
        self._is_attached: bool = False
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
        leaf._attached_left  = []
        leaf._attached_right = []
        leaf._attached_above = []
        leaf._attached_below = []
        leaf._is_attached = False
        return leaf

    def legend(self, *args, position: str | None = None, **kwargs) -> "Chart":
        """Toggle the in-frame overlay legend.

        `chart.legend()` or `chart.legend(True)` turns it on; `False` off.
        `position=` places the block (modeled on vega-lite's `orient`):

        - **Outside tokens** reserve margin space beside the data area:
          `"right"` (default), `"left"`, `"top"`, `"bottom"`.
        - **Inside tokens** overlay the data area:
          `"top-right"`, `"top-left"`, `"bottom-right"`, `"bottom-left"`,
          `"center"`.

        Outside legends draw with no frame; inside legends get a
        translucent background for readability over plot marks.

        For a separate, layout-level legend leaf (the kind that lives in
        its own panel and harvests entries from sibling charts), use
        `pt.legend(...)` or `parent.legend(...)` on a `Layout`."""
        if kwargs:
            raise TypeError(
                f"Chart.legend() got unexpected keyword arguments: {list(kwargs)!r}"
            )
        if args and not isinstance(args[0], bool):
            raise TypeError(
                f"chart.legend() (leaf in-frame overlay) takes an optional bool; "
                f"got {type(args[0]).__name__}."
            )
        _VALID_POSITIONS = ("right", "left", "top", "bottom",
                            "top-right", "top-left",
                            "bottom-right", "bottom-left", "center")
        if position is not None and position not in _VALID_POSITIONS:
            raise ValueError(
                f"chart.legend(position={position!r}) — must be one of "
                f"{_VALID_POSITIONS}."
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
                                    ("x", "y", "fill", "color", "group", "linestyle"))):
                        kwargs["data"] = self._data
                if spec is not None and spec.frame_defaults is not None:
                    for call in spec.frame_defaults(list(args), dict(kwargs)) or ():
                        # Tag with a 4th element so `_replay` can route
                        # `xscale(order=...)` from frame_defaults to
                        # `<axis>_order_default` — letting a peer artist's
                        # `axis_order` hook (e.g. dendrogram) win over the
                        # frame_default's suggested order without
                        # disturbing user-explicit `c.xscale(order=...)`.
                        self._calls.append((*call, True))
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
        so they need to record explicitly. Returns `self` for chaining,
        matching the `__getattr__` recorder."""
        self._calls.append((name, list(args), dict(kwargs)))
        return self

    # Reflines, imshow, and any user-registered artist forward through
    # __getattr__ above — long-form (`data=`, `x=`, etc.) and aes
    # inheritance are handled inside each artist's `record()` plus the
    # generic recorder closure in `__getattr__`.

    def inset(self, rect, **chart_opts) -> "Chart":
        """Embed a small Chart inside this leaf at axes-fraction coordinates.

        `rect=(x, y, w, h)` is in axes-fraction units (0..1) of this leaf's
        data area, with the origin at the *bottom-left*. Returns a fresh
        Chart configured to
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
        # Inherits the global floor (zero by default) — content-fit
        # margins only, no pre-reserved breathing room. Small canvas: no
        # room for long axis labels unless the user sizes it bigger.
        inset = Chart(data_width=dw, data_height=dh, **chart_opts)
        inset._inset_owner = self
        self._insets.append((tuple(rect), inset))
        return inset

    # ---------- attachments ----------

    def attach_left(self, *charts, hide_labels: bool = True,
                    gap: float | None = None) -> "Chart":
        """Attach one or more charts to this chart's left side.

        Attachments extend the host's margin: they occupy reserved space
        around the data area, like axis labels and ticks do, but with
        user-defined content. The host-with-attachments behaves as one
        Chart from the outside — peer composition (`|` / `/`) sees it
        as a single block.

        Order is host-outward: the first arg sits immediately left of
        the host's data area; later args extend further left. Each
        attachment auto-shares y with the host so row order propagates
        and the heights align. Call multiple times to append.

        `hide_labels=True` (default) suppresses tick labels and axis
        labels on the inner-facing edge of each pair (the attachment's
        host-facing side and the host's attachment-facing side) so the
        composite reads as one frame without duplicated decorations.
        Pass `hide_labels=False` to keep both sides labeled — useful
        when the attachment is an independent chart whose own axis
        carries meaning at the joined edge.

        `gap=` is the pixel separation between each attachment's data
        area and its inward neighbor (host or previous attachment).
        Defaults to `spec.json:layout.attach_gap`. Pass `gap=0` for a
        flush join with no visual separation.
        """
        return self._attach("left", charts, hide_labels=hide_labels, gap=gap)

    def attach_right(self, *charts, hide_labels: bool = True,
                     gap: float | None = None) -> "Chart":
        """Attach charts to the right side. See `attach_left`."""
        return self._attach("right", charts, hide_labels=hide_labels, gap=gap)

    def attach_above(self, *charts, hide_labels: bool = True,
                     gap: float | None = None) -> "Chart":
        """Attach charts above. First arg sits immediately above the host;
        later args extend further up. Top/bottom attachments auto-share x
        with the host (widths align, column order propagates). See
        `attach_left` for `hide_labels=` and `gap=`."""
        return self._attach("above", charts, hide_labels=hide_labels, gap=gap)

    def attach_below(self, *charts, hide_labels: bool = True,
                     gap: float | None = None) -> "Chart":
        """Attach charts below. First arg sits immediately below the host;
        later args extend further down. See `attach_above`."""
        return self._attach("below", charts, hide_labels=hide_labels, gap=gap)

    def _attach(self, side: str, charts, *, hide_labels: bool = True,
                gap: float | None = None) -> "Chart":
        target_list = {
            "left":  self._attached_left,
            "right": self._attached_right,
            "above": self._attached_above,
            "below": self._attached_below,
        }[side]
        share_axis = "y" if side in ("left", "right") else "x"
        share_attr = "_share_x" if share_axis == "x" else "_share_y"
        for c in charts:
            if not isinstance(c, Chart):
                raise TypeError(
                    f"attach_{side}() expects Chart instances; got {type(c).__name__}."
                )
            if c is self:
                raise ValueError("cannot attach a chart to itself.")
            if c._parent is not None:
                raise ValueError(
                    "each chart can be in at most one parent. "
                    "Compose fresh charts, or copy your sub-assembly."
                )
            if (c._attached_left or c._attached_right
                    or c._attached_above or c._attached_below):
                raise ValueError(
                    "nested attachments are not supported (attached charts "
                    "cannot themselves have attachments)."
                )
            # Existing share targets get a warning; we still wire the host
            # as the new share target so size and descriptors lock to it.
            existing = getattr(c, share_attr, None)
            if existing is not None and existing is not self:
                import warnings
                warnings.warn(
                    f"attach_{side}(): chart already has share_{share_axis}= "
                    f"set; overriding to share with host.",
                    stacklevel=3,
                )
            setattr(c, share_attr, self)
            c._parent = self
            c._is_attached = True
            if not hide_labels:
                # Per-leaf flag read by the joined-pair walk; setting it on
                # the attachment alone is enough — `_mark_joined_pair`
                # skips the hide step if either side opts out.
                hide_flag = f"_share_hide_labels_{share_axis}"
                setattr(c, hide_flag, False)
            # Per-attachment gap to inward neighbor. None falls back to the
            # spec default at allocate time so a theme override flows in.
            c._attachment_gap = (float(gap) if gap is not None
                                 else _LAYOUTSPEC["attach_gap"])
            target_list.append(c)
        return self

    # ---------- render ----------

    def _to_svg_unchecked(self, *, outer=None) -> str:
        """Render path that skips the root check — used by parents
        embedding this chart (insets, layout panels). `outer` is the
        figure-level breathing-room margin; only the public `to_svg()`
        passes it. Embedded callers (insets) leave it None."""
        if self._leaf_kind == "legend":
            from .legend import _render_standalone_legend
            return _render_standalone_legend(self)
        if self._leaf_kind == "diagram":
            from .layout_diagram import _render_standalone_diagram
            return _render_standalone_diagram(self)
        # Chart with attachments behaves as a mini-layout — route through
        # the full layout engine so attachments get measured, allocated,
        # and rendered as siblings.
        if (self._attached_left or self._attached_right
                or self._attached_above or self._attached_below):
            from ._layout_engine import _render_layout
            return _render_layout(self, outer=outer)
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
            return _render(states[id(self)], W, H, M_eff, outer=outer)

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
        self._gap:   float | None = None  # unified override
        self._gap_x: float | None = None  # per-axis override (between cols)
        self._gap_y: float | None = None  # per-axis override (between rows)
        # Grid-specific shape; left at None for h/v parents.
        self._grid_rows: int | None = None
        self._grid_cols: int | None = None
        # Set by `share_x("col")` / `share_y("row")` on h/v compositions
        # — tells the layout engine to treat this node as a virtual grid
        # and coordinate margins per column/row across sub-layouts.
        # Opt-in so plain `(a | b) / (c | d)` keeps natural per-row sizing.
        self._virtual_grid_aligned: bool = False
        # Set by `.coordinate(...)` to apply a single coordinate transform
        # to the whole composition. When set, `_render_layout` delegates
        # to `coord.render_layout(root)` — the coord owns its own render
        # strategy (overlay, faceting, etc.).
        self._coordinate = None
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

        `hide_labels=True` (default) also suppresses xlabel and x-tick
        labels on joined-pair sides so
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

    def sectors(self, spec, *, column: str | None = None,
                axis: str = "x",
                divider: bool = True, label: bool = True,
                gap: float | None = None) -> "Layout":
        """Apply ``c.sectors(spec, ...)`` to every leaf chart in this
        layout — sugar so a stacked-track figure only declares the
        sector partition once.

        Inserted at the *front* of each leaf's call list: sectors must be
        replayed before any artist call so ``_sector_remap_data`` sees
        ``st["x_sectors"]`` when each row's data gets offset into global
        coords. Otherwise leaves constructed with artist calls before the
        Layout.sectors propagation would render every chromosome's data
        overlapping in the first sector slot. A leaf-level
        ``c.sectors(...)`` recorded after layout construction still wins
        — it's replayed last and overwrites the propagated value.
        """
        kw = {"axis": axis, "divider": divider, "label": label}
        if column is not None:
            kw["column"] = column
        if gap is not None:
            kw["gap"] = gap
        for leaf in self._iter_leaves():
            leaf._calls.insert(0, ("sectors", [spec], kw))
        return self

    def coordinate(self, coord) -> "Layout":
        """Apply ``coord`` to the whole composition as a single coordinate.

        Hands the entire render off to ``coord.render_layout(root)`` — the
        coord owns its strategy (overlay, faceting, etc.). Coords without
        a ``render_layout`` method fall through to the standard
        rectangular layout — the coord is then a no-op at the container
        level. See the coord's own docs for what its `render_layout`
        does and what knobs it exposes.
        """
        self._coordinate = coord
        return self

    def _iter_leaves(self):
        """Depth-first yield of every leaf Chart under this layout."""
        for child in self._children:
            if child is None:
                continue
            if getattr(child, "_is_parent", False):
                yield from child._iter_leaves()
            else:
                yield child

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

    def gap(self, value: int | float | None = None, *,
            x: int | float | None = None,
            y: int | float | None = None) -> "Layout":
        """Override the inter-panel gap. Two forms:

        - `.gap(8)` — unified: both x (between columns) and y (between
          rows) use 8. Clears any prior per-axis overrides.
        - `.gap(x=4)` / `.gap(y=8)` / `.gap(x=4, y=8)` — per-axis:
          override just the named axis (or both), leaving the others
          on their current setting.

        Mixing the positional and kwarg forms in one call is rejected
        (chain two calls instead). Falls back to `spec.json:layout.gap_x`
        / `gap_y` (then unified `gap`) when nothing is set. Joined
        share-pairs get the same gap as non-joined siblings. Negative
        values are accepted (panels overlap)."""
        if value is not None and (x is not None or y is not None):
            raise TypeError(
                "Layout.gap(): pass either a positional value (unified) "
                "or `x=` / `y=` kwargs (per-axis), not both. To set both, "
                "chain: `.gap(8).gap(x=4)`."
            )
        if value is not None:
            self._gap = float(value)
            self._gap_x = None
            self._gap_y = None
        if x is not None:
            self._gap_x = float(x)
        if y is not None:
            self._gap_y = float(y)
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

    def _to_svg_unchecked(self, *, outer=None) -> str:
        from ._layout_engine import _render_layout
        return _render_layout(self, outer=outer)


def chart(data=None, **opts) -> Chart:
    """Construct a table-bound Chart. See `Chart` for keyword arguments."""
    return Chart(data, **opts)


def grid(cells: list[list], **kwargs) -> "Layout":
    """Build a grid-layout `Layout` from a list-of-lists of cells.

    Each cell is either a `Chart` or `None` (empty). All rows must have
    the same number of columns. The grid does **no proportional
    redistribution** — each column's width is the max natural canvas
    width across cells in that column; each row's height is the max
    natural canvas height across cells in that row. To make a column
    twice as wide as another, set `data_width=` directly on the leaf
    charts; the grid then sums their natural canvases plus per-boundary
    gaps.

    The constructor takes only the structural argument (`cells`); all
    behavior knobs live on methods so they compose uniformly across
    grid-built and `|`/`/`-built layouts. For inter-panel gap, chain
    `.gap(N)` for a unified value or `.gap(x=..., y=...)` for per-axis
    control. For axis sharing, chain `.share_x("col"/"row"/"all")` /
    `.share_y(...)`.
    """
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
    Accepts True ("all"), False / None ("none"), or the four literal strings."""
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


