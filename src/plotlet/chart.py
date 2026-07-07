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
`save_*`), and `fit()`.

Composition operators:

  * `a | b` → horizontal `Layout`. Flattens when LHS is already a
    same-direction `Layout` (so `a | b | c` is a single 3-cell row, not
    nested). Mutates LHS in place; LHS should not be reused after.

  * `a / b` → vertical `Layout`. Same flattening rule.

Rendering goes journal → IR → plot: `to_svg()` lowers the tree to the
figure IR (`_ir.py`, contract in `docs/IR.md`) and hands it to the
render half through the `render` package's seam — the IR path is the
only render path, and this half never sees the pipeline internals.

Invariants:

  * Single parent — composing a node that already has a `_parent` raises.
  * Show-on-child raises — calling `.show()` / `.to_svg()` / `_repr_mimebundle_`
    on a node with a non-None `_parent` raises with a pointer up.
"""
from __future__ import annotations

import importlib.util
import inspect
import re
from pathlib import Path

import resvg_py

from ._spec import _SIZESPEC, _MARGIN_FLOOR
from ._tree import compute_share_classes, normalize_share_mode
from .utils import _to_px, _normalize_data
from .registry import get_artist, all_artist_names


# Frame-state methods recordable on a Chart (replayed by `_replay`). Lives
# here because `Chart.__getattr__` / `__dir__` are the only consumers —
# the dispatcher in `_replay` matches on name directly.
_FRAME_METHODS = {
    "title", "xlabel", "ylabel", "xlim", "ylim",
    "xscale", "yscale", "grid", "legend",
    "xticks", "yticks", "spines", "theme",
    "x_expand", "y_expand", "clip", "facecolor",
    "coordinate", "sectors",
}


def _has_column(data, name):
    """True if `name` looks up as a column on `data`. Used by data
    auto-injection — pandas/dict via ``in``, other types fall back to
    "no" so the user passes ``data=`` explicitly."""
    try:
        return name in data
    except (TypeError, KeyError):
        return False


# Notebook display renders PNG at 2x and pins the logical size in the
# output metadata — retina-sharp at natural size.
_REPR_SCALE = 2

# Root-tag size attrs, always integer px in our own emit
# (`_layout_engine` writes `width="{Wt}" height="{Ht}"` on the root).
_SVG_SIZE_RE = re.compile(r'<svg[^>]* width="(\d+)" height="(\d+)"')


def _svg_size(svg: str) -> tuple[int, int]:
    m = _SVG_SIZE_RE.match(svg)
    if m is None:
        raise ValueError("could not read width/height off the SVG root tag")
    return int(m.group(1)), int(m.group(2))


def _svg_to_png(svg: str, *, scale: float = 1.0) -> bytes:
    """SVG → PNG bytes via resvg (statically bundled — no system
    libraries). `skip_system_fonts` keeps rasterization independent of
    installed fonts; plotlet text is already path outlines."""
    return bytes(resvg_py.svg_to_bytes(svg_string=svg, zoom=float(scale),
                                       skip_system_fonts=True))


class _Renderable:
    """Private base for `Chart` and `Layout` — owns the shared rendering
    glue (composition operators, output methods, `fit()`,
    `_require_render_root`).

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
        from ._ir import to_ir
        from .render import render_svg
        return render_svg(to_ir(self), clean=clean)

    def _render_root(self):
        """Lower this tree to the figure IR and hydrate the renderer's
        private node tree from it. Every user-facing render goes
        journal → IR → plot — one pipeline, so the IR provably carries
        everything the renderer consumes. The user's own tree is never
        handed to the engine (and never mutated by it)."""
        from ._ir import to_ir
        from .render import hydrate
        return hydrate(to_ir(self))

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
        self._require_render_root()
        from ._ir import to_ir
        from .render import regions
        return regions(to_ir(self))

    def to_html(self, full_page: bool = False) -> str:
        svg = self.to_svg()
        if full_page:
            return ('<!doctype html><html><head><meta charset="utf-8">'
                    '<title>plotlet</title></head>'
                    f'<body style="margin:24px">{svg}</body></html>')
        return svg

    def _repr_mimebundle_(self, include=None, exclude=None):
        # Notebook display only — the file output from `to_svg()` is not
        # touched. A real `image/png` output (not HTML) so frontends
        # attach their native image affordances: drag out of the cell,
        # Copy Image, Save Image As. Rendered at 2x with the logical
        # size in metadata so it displays retina-sharp at natural size.
        # `show(format="svg")` is the vector alternative.
        svg = self.to_svg()
        w, h = _svg_size(svg)
        return ({"image/png": _svg_to_png(svg, scale=_REPR_SCALE)},
                {"image/png": {"width": w, "height": h}})

    def _svg_img_html(self) -> str:
        # Vector notebook display, wrapped as an <img> (SVG data URI)
        # rather than inline <svg> markup so the browser treats the
        # figure as an image and it can be dragged out of the cell.
        # base64, not percent-encoded UTF-8 — avoids `#`/quote escaping
        # in the URI. No native copy/save buttons: frontends reserve
        # those for bitmap-MIME outputs (the `format="png"` path).
        import base64
        b64 = base64.standard_b64encode(self.to_svg().encode("utf-8")).decode("ascii")
        return (f'<img style="max-width:100%;height:auto" alt="plotlet figure" '
                f'src="data:image/svg+xml;base64,{b64}"/>')

    def show(self, *, format: str = "png", scale: float = _REPR_SCALE):
        """Display in a notebook. `format="png"` (default) emits a real
        `image/png` output — native drag/copy/save in every frontend,
        rendered at `scale`× and displayed at logical size. `format="svg"`
        displays the vector SVG as a draggable <img> — crisp at any zoom,
        but without the native image buttons."""
        self._require_render_root()
        if format not in ("png", "svg"):
            raise ValueError(
                f'show: format= must be "png" or "svg"; got {format!r}.'
            )
        try:
            from IPython.display import HTML, display
        except ImportError:
            print(self.to_html(full_page=True))
            return
        if format == "svg":
            display(HTML(self._svg_img_html()))
            return
        svg = self.to_svg()
        w, h = _svg_size(svg)
        display({"image/png": _svg_to_png(svg, scale=scale)},
                metadata={"image/png": {"width": w, "height": h}}, raw=True)

    def save_svg(self, path, *, clean: bool = False):
        Path(path).write_text(self.to_svg(clean=clean))
        return self

    def save_png(self, path, *, scale: float = 1.0):
        """Rasterize to PNG via the bundled resvg renderer. `scale`
        multiplies the canvas pixel dimensions uniformly (e.g. `scale=2`
        for retina)."""
        Path(path).write_bytes(_svg_to_png(self.to_svg(), scale=scale))
        return self

    def save_pdf(self, path):
        """Rasterize to PDF. Requires `cairosvg` (`pip install cairosvg`,
        or `pip install plotlet[pdf]`)."""
        try:
            import cairosvg
        except ImportError as e:
            raise ImportError(
                "save_pdf() needs cairosvg. Install with: pip install cairosvg"
            ) from e
        cairosvg.svg2pdf(bytestring=self.to_svg().encode("utf-8"),
                         write_to=str(path))
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
        from ._ir import to_ir
        from .render import data_total_size, natural_size
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
        #
        # Measurement goes through the seam, re-lowering per pass —
        # `_scale_data_dims` updates the recorder copy between passes,
        # so each pass measures a fresh IR.
        for _ in range(6):
            ir = to_ir(node)
            W_nat, H_nat = natural_size(ir)
            D_w, D_h = data_total_size(ir)
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
                 x: str | None = None, y: str | None = None,
                 fill: str | None = None,
                 color: str | None = None,
                 group: str | None = None,
                 linestyle: str | None = None,
                 palette=None,
                 **kwargs):
        # Constructor accepts only field-state kwargs (structural dims,
        # margin, data, aes). Everything else (title, xlim, xscale,
        # legend, grid, theme, …) is a method call — chain them after
        # construction. Kept minimal so the journal event `new_chart`
        # can carry exactly the kwargs Chart() accepts, no whitelist
        # needed at replay.
        if kwargs:
            raise TypeError(f"Chart() got unexpected keyword arguments: {list(kwargs)!r}")

        # ---- Render-state init (leaf-only fields used by core._render_inner) ----
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
        # Normalize DataFrame-shaped and numpy inputs to plain Python at
        # the boundary. The journal never holds a library-specific object,
        # so JSON serialization has nothing to envelope.
        self._data = _normalize_data(data)
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
        leaf._legend_valign = "middle"
        leaf._legend_ncols = 1
        leaf._legend_user_width = None
        leaf._legend_user_height = None
        leaf._legend_gap = None
        leaf._insets = []
        leaf._inset_owner = None
        leaf._last_M_eff = None
        leaf._attached_left  = []
        leaf._attached_right = []
        leaf._attached_above = []
        leaf._attached_below = []
        leaf._is_attached = False
        return leaf

    def legend(self, *args, position: str | None = None,
               ncols: int | None = None, **kwargs) -> "Chart":
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

        `ncols=N` wraps each discrete entry list into N columns, filled
        down-then-across (matplotlib's `ncols`, ggplot2's
        `guide_legend(ncol=)`). On `"top"` / `"bottom"` the default is a
        single horizontal row; `ncols=` switches those to the same
        N-column grid.

        For a separate, layout-level legend leaf (the kind that lives in
        its own panel and harvests entries from sibling charts), use
        `pt.legend(...)` or `parent.legend(...)` on a `Layout`."""
        if kwargs:
            raise TypeError(
                f"Chart.legend() got unexpected keyword arguments: {list(kwargs)!r}"
            )
        if ncols is not None and (not isinstance(ncols, int)
                                  or isinstance(ncols, bool) or ncols < 1):
            raise ValueError(
                f"chart.legend(ncols={ncols!r}) — must be an int >= 1."
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
        kw = {}
        if position is not None:
            kw["position"] = position
        if ncols is not None:
            kw["ncols"] = ncols
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
                    # Data injection — inject the chart-level table when any
                    # kwarg value names a column on it. Generic by design:
                    # artists declare their column-referencing kwargs by
                    # naming convention (string-valued kwarg → column ref),
                    # so adding a new artist with new endpoint kwargs needs
                    # no edit here.
                    if (self._data is not None and "data" not in kwargs
                            and any(_has_column(self._data, v)
                                    for v in kwargs.values()
                                    if isinstance(v, str))):
                        kwargs["data"] = self._data
                    # Normalize any user-passed `data=` (chart._data is
                    # already normalized in __init__; idempotent no-op
                    # for that path). Positional args get the same
                    # treatment — `c.heatmap(df, ...)` passes df
                    # positionally, and the artist expects a normalized
                    # value regardless of position.
                    if "data" in kwargs:
                        kwargs["data"] = _normalize_data(kwargs["data"])
                    args = tuple(_normalize_data(a) for a in args)
                # Only the user action is recorded — an artist's
                # frame_defaults regenerate inside `_replay` on every
                # render (see `_expand_frame_defaults` in core.py).
                self._calls.append((name, list(args), dict(kwargs)))
                return self
            # Surface the artist's module docstring on the recorder so
            # `c.line?` / `help(c.line)` / `c.line.__doc__` reach it —
            # __getattr__ dispatch otherwise blocks Python's standard
            # help path. Frame methods (no spec) keep the empty default.
            if spec is not None:
                mod = inspect.getmodule(spec.record)
                recorder.__doc__ = (mod.__doc__ if mod is not None else None) or ""
                recorder.__name__ = name
            return recorder
        # An installed-but-not-imported extension (from core or the
        # plotlet-extensions package — `plotlet.extensions` is a shared
        # namespace) registers its artist only on import; hint at that.
        if importlib.util.find_spec(f"plotlet.extensions.{name}") is not None:
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
        # Route through the `chart()` factory so sugar kwargs (title,
        # xlim, ...) work here the same as at top level.
        inset = chart(data_width=dw, data_height=dh, **chart_opts)
        self._attach_inset(rect, inset)
        return inset

    def _attach_inset(self, rect, inset_chart: "Chart") -> None:
        """Register an already-constructed Chart as an inset of this leaf.
        Shared between `.inset()` (creates the chart, then registers) and
        journal replay (chart already exists, needs registering)."""
        inset_chart._inset_owner = self
        self._insets.append((tuple(rect), inset_chart))

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
        # Validation + warning at user-call time; field state is wired
        # on the render tree (`render._nodes._apply_attach`) at render.
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
            existing = getattr(c, share_attr, None)
            if existing is not None and existing is not self:
                import warnings
                warnings.warn(
                    f"attach_{side}(): chart already has share_{share_axis}= "
                    f"set; overriding to share with host.",
                    stacklevel=3,
                )
        attach_kw = {"hide_labels": hide_labels}
        if gap is not None:
            attach_kw["gap"] = gap
        self._calls.append((f"attach_{side}", list(charts), attach_kw))
        # `_parent` is the structural ownership marker — set here at
        # record time (just like `_compose` sets it for layout
        # children), read by validation (`_attach`, `_compose`,
        # `_require_render_root`) and by cascade (`_ancestor_calls`).
        # The derived fields (`_attached_*`, `_share_*`, `_is_attached`,
        # `_attachment_gap`) are wired on the render tree by
        # `render.materialize` — never on these recorder objects.
        for c in charts:
            c._parent = self
        return self

    # ---------- render ----------

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
        # Journal of state-method calls (sectors, share_x/y,
        # align_x/y, coordinate, gap). Append-only: user calls only ever
        # add entries here; the derived fields below are wired from
        # these entries on the render tree (`render.materialize`)
        # and stay at their defaults on this recorder object. Compose
        # isn't journaled here — every `|` / `/` builds a fresh Layout
        # via `_compose`, never mutating an existing one, so the tree
        # itself stays append-only: each `_children` list is written
        # once at construction and never edited. The engine's flat-row
        # view of `(a|b) | c` comes from `_effective_children()` at
        # read time, not from in-place flatten. Layout state is
        # resolved by parent-chain cascade at render time: each leaf
        # walks up collecting cascadable entries from ancestors. Layout
        # never mutates a leaf's journal.
        self._calls: list[tuple[str, list, dict]] = []
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
        self._validate_share("x", mode)
        self._calls.append(("share_x", [mode], {"hide_labels": hide_labels}))
        return self

    def share_y(self, mode: bool | str = "all", *,
                hide_labels: bool = True) -> "Layout":
        """Wire up y-axis sharing across this layout's leaves. See `share_x`."""
        self._validate_share("y", mode)
        self._calls.append(("share_y", [mode], {"hide_labels": hide_labels}))
        return self

    def sectors(self, spec, *, column: str | None = None,
                axis: str = "x",
                divider: bool = True, label: bool = True,
                gap: float | None = None) -> "Layout":
        """Apply ``c.sectors(spec, ...)`` to every leaf chart in this
        layout — sugar so a stacked-track figure only declares the
        sector partition once.

        Recorded on the Layout's own journal; at render time, each leaf
        walks up its parent chain via `_ancestor_calls` and prepends
        Layout-level sector entries to its effective replay input. No
        fan-out into leaf `_calls` — Layout never mutates a leaf's
        journal. `_replay`'s sectors-to-front pass keeps recorded order
        among sectors, so a leaf-level ``c.sectors(...)`` appended later
        still wins via last-write on `st[\"{axis}_sectors\"]`.
        """
        kw = {"axis": axis, "divider": divider, "label": label}
        if column is not None:
            kw["column"] = column
        if gap is not None:
            kw["gap"] = gap
        self._calls.append(("sectors", [spec], kw))
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
        self._calls.append(("coordinate", [coord], {}))
        return self

    def title(self, text) -> "Layout":
        """Figure-level title: one centered band above this layout's
        rect, styled like a panel title (same font spec, `pad.title`
        gap to the content below). Works on any layout — a rect grid
        gets a suptitle, a coordinate pile (circular overlay) gets the
        band above its canvas, and a nested titled layout gets the band
        above its own sub-rect. Panel-level titles stay on the leaf
        charts (`c.title(...)`); this is the composition-level
        counterpart. Last call wins."""
        self._calls.append(("title", [text], {}))
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

    def _effective_children(self) -> list:
        """The engine's view of this Layout's children. `_compose` never
        flattens at record time — `(a|b) | c` records as a nested 2-2
        tree, faithful to the AST the user typed. This pass absorbs
        same-kind child Layouts whose own `_calls` is empty so the
        engine sees the flat 3-cell row it needs for measurement and
        gap allocation. A child Layout that recorded its own state (e.g.
        `inner.share_x("all")`) is opaque: its state scopes to its own
        children, and it stays as one cell at this level.

        Pure function of `_children` and descendants' `_calls`. No
        mutation, no caching."""
        out: list = []
        for child in self._children:
            if (child is not None and child._is_parent
                    and child._layout_kind == self._layout_kind
                    and not child._calls):
                out.extend(child._effective_children())
            else:
                out.append(child)
        return out

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
        self._validate_align("x", mode)
        self._calls.append(("align_x", [mode], {}))
        return self

    def align_y(self, mode: bool | str = "row") -> "Layout":
        """Coordinate per-row heights across columns. See `align_x`."""
        self._validate_align("y", mode)
        self._calls.append(("align_y", [mode], {}))
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
        args = [value] if value is not None else []
        kw = {}
        if x is not None: kw["x"] = x
        if y is not None: kw["y"] = y
        self._calls.append(("gap", args, kw))
        return self

    def _validate_share(self, axis: str, mode) -> None:
        """Pure-validation pass for `share_x/y`. Called at user-call time
        so layout-kind errors and shape mismatches surface at the user's
        `share_x()` line, not at render. Mutates nothing — the field
        writes happen on the render tree (`render._nodes._apply_share`)
        when `materialize` runs at render."""
        norm = normalize_share_mode(axis, mode)
        if norm in ("none", "all"):
            return
        if self._layout_kind != "grid":
            # Composition fallback: v-of-h with share_x("col"), or
            # h-of-v with share_y("row"). `compute_share_classes`
            # validates the cell-count match below.
            expected_outer = "v" if norm == "col" else "h"
            if self._layout_kind != expected_outer:
                raise ValueError(
                    f"share_{axis}={norm!r} requires a pt.grid layout, or "
                    f"a {expected_outer!r} composition of "
                    f"{'h' if norm == 'col' else 'v'}-sub-layouts; got "
                    f"{self._layout_kind!r}."
                )
        compute_share_classes(self, norm)  # result discarded — call for its raises

    def _validate_align(self, axis: str, mode) -> None:
        """Pure-validation pass for `align_x/y`. See `_validate_share`."""
        norm = normalize_share_mode(axis, mode)
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

def chart(data=None, *,
          data_width=None, data_height=None, margin=None,
          x=None, y=None, fill=None, color=None, group=None,
          linestyle=None, palette=None,
          # Method-sugar kwargs. Each maps to a chained method call
          # after construction. Kept on the factory (not on
          # `Chart.__init__`) so the class stays pure field-state and
          # the journal event `new_chart` can carry exactly what the
          # constructor accepts with no whitelist at replay.
          title=None, xlabel=None, ylabel=None,
          xlim=None, ylim=None, xscale=None, yscale=None,
          x_expand=None, y_expand=None,
          legend=None, grid=None, clip=None,
          facecolor=None, theme=None) -> Chart:
    """Construct a table-bound Chart. Structural kwargs (`data_width`,
    `data_height`, `margin`) and aes kwargs (`x`, `y`, `fill`, `color`,
    `group`, `linestyle`, `palette`) go to the Chart constructor.
    Everything else is a convenience for the equivalent chained method
    call — e.g. `pt.chart(df, title="foo", xlim=(0, 10))` is
    `pt.chart(df).title("foo").xlim(0, 10)`."""
    c = Chart(data, data_width=data_width, data_height=data_height,
              margin=margin, x=x, y=y, fill=fill, color=color,
              group=group, linestyle=linestyle, palette=palette)
    if title    is not None: c.title(title)
    if xlabel   is not None: c.xlabel(xlabel)
    if ylabel   is not None: c.ylabel(ylabel)
    if xlim     is not None: c.xlim(*xlim)
    if ylim     is not None: c.ylim(*ylim)
    if xscale   is not None: c.xscale(xscale)
    if yscale   is not None: c.yscale(yscale)
    if x_expand is not None:
        c.x_expand(*(x_expand if isinstance(x_expand, (tuple, list)) else (x_expand,)))
    if y_expand is not None:
        c.y_expand(*(y_expand if isinstance(y_expand, (tuple, list)) else (y_expand,)))
    if legend    is not None: c.legend(legend)
    if grid      is not None: c.grid(grid)
    if clip      is not None: c.clip(clip)
    if facecolor is not None: c.facecolor(facecolor)
    if theme     is not None: c.theme(theme)
    return c


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

    parent = Layout("grid", flat)  # row-major; may contain None
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




def _compose(left, right, kind: str):
    """Implement `|` / `/`. Either operand may be a `Chart` (leaf) or a
    `Layout` (parent). Always returns a fresh outer Layout — never
    mutates either operand. Same-kind nesting is collapsed for the
    engine by `Layout._effective_children()` at render time; the recorded
    tree preserves the AST shape the user typed, so the journal stays
    append-only."""
    if not isinstance(right, (Chart, Layout)):
        return NotImplemented
    if left._parent is not None or right._parent is not None:
        raise ValueError(
            "Each chart can be in at most one parent. "
            "Compose fresh charts, or copy your sub-assembly."
        )
    return Layout(kind, [left, right])
