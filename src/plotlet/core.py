"""Figure class and render orchestrator — registry-driven version.

The deferred-render pipeline is unchanged in spirit:
  1. `figure()` returns a `Figure` whose methods record into `_calls`.
  2. `Figure.to_svg()` calls `_render(_replay(), ...)`.
  3. `_render` does: pre-process → domain → scales → grid → artists → spines/ticks
     → labels/title → legend.

The difference from the original: every artist-specific branch is now a
registry lookup. Adding a new plot type means calling `add_artist(...)` —
no monkey-patching, no editing this file.
"""
from __future__ import annotations

import math
from pathlib import Path

from ._spec import (
    SPEC, _SIZESPEC, _FRAME, _GRIDSPEC, _FONTSPEC, _LEGSPEC, _D, _DASH,
)
from .colors import _resolve_color, TAB10
from .scales import _LinearScale, _LogScale, _BandScale, _nice_domain, _fmt_tick
from .font import _measure_text, _text_path
from .artists import _histogram
from .registry import RenderContext, get_artist, all_artist_names
from . import builtin_artists  # noqa: F401  — registers built-ins on import

_TICK_LEN = _FRAME["tick_length"]
_TICK_PAD = _FRAME["tick_pad"]
_SPINE = _FRAME["color"]
_SPW = _FRAME["width"]
_GRID = _GRIDSPEC["color"]
_FONT = _FONTSPEC["family"]


# Frame metadata methods (title, xlabel, etc.) — these aren't artists,
# they're just state setters. Kept as a fixed set.
_FRAME_METHODS = {
    "title", "xlabel", "ylabel", "xlim", "ylim",
    "xscale", "yscale", "grid", "legend",
}


class Figure:
    def __init__(self, width: int | None = None, height: int | None = None,
                 margin: dict | None = None):
        self._calls: list[tuple[str, list, dict]] = []
        self._width = width if width is not None else _SIZESPEC["width"]
        self._height = height if height is not None else _SIZESPEC["height"]
        self._margin = margin if margin is not None else dict(_SIZESPEC["margin"])

    def __getattr__(self, name):
        # Recordable if it's a frame method or a registered artist
        if name in _FRAME_METHODS or get_artist(name) is not None:
            def recorder(*args, **kwargs):
                self._calls.append((name, list(args), dict(kwargs)))
                return self
            return recorder
        raise AttributeError(
            f"Figure has no method {name!r}. "
            f"Registered artists: {all_artist_names()}"
        )

    def __dir__(self):
        return sorted(set(super().__dir__()) | _FRAME_METHODS | set(all_artist_names()))

    # ------------------------------------------------------------- replay
    def _replay(self):
        st = {
            "artists": [], "title": "", "xlabel": "", "ylabel": "",
            "xlim": None, "ylim": None, "xscale": "linear", "yscale": "linear",
            "grid": False, "legend": False,
        }
        for name, args, kw in self._calls:
            spec = get_artist(name)
            if spec is not None:
                st["artists"].append(spec.record(args, kw))
            elif name == "title":  st["title"] = args[0]
            elif name == "xlabel": st["xlabel"] = args[0]
            elif name == "ylabel": st["ylabel"] = args[0]
            elif name == "xlim":   st["xlim"] = (args[0], args[1])
            elif name == "ylim":   st["ylim"] = (args[0], args[1])
            elif name == "xscale": st["xscale"] = args[0]
            elif name == "yscale": st["yscale"] = args[0]
            elif name == "grid":   st["grid"] = (args[0] if args else True)
            elif name == "legend": st["legend"] = (args[0] if args else True)
        return st

    # ------------------------------------------------------------- render
    def to_svg(self) -> str:
        return _render(self._replay(), self._width, self._height, self._margin)

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
        try:
            from IPython.display import HTML, display
        except ImportError:
            print(self.to_html(full_page=True))
            return
        display(HTML(self.to_svg()))

    def write_html(self, filename):
        Path(filename).write_text(self.to_html(full_page=True))
        return self

    def save_svg(self, filename):
        Path(filename).write_text(self.to_svg())
        return self


def figure(width: int | None = None, height: int | None = None, **opts) -> Figure:
    return Figure(width=width, height=height, **opts)


# ---------------------------------------------------------------------------
# render orchestrator — now generic over the registry
# ---------------------------------------------------------------------------

def _scan_domain(artists, axis):
    """Collect all values an artist contributes to a given axis ('x' or 'y')."""
    lo, hi = math.inf, -math.inf
    for a in artists:
        spec = get_artist(a["type"])
        if spec is None:
            continue
        fn = spec.xdomain if axis == "x" else spec.ydomain
        vals = fn(a)
        if vals is None:
            continue
        for v in vals:
            if v is None: continue
            if isinstance(v, float) and math.isnan(v): continue
            if v < lo: lo = v
            if v > hi: hi = v
    return lo, hi


def _resolve_domain(lo, hi, user_lim, scale_kind, force_zero=False):
    """Apply user override, log snapping, and nice rounding."""
    if user_lim is not None:
        return user_lim
    if math.isinf(lo):
        return (0, 1)
    if force_zero and lo > 0:
        lo = 0
    if lo == hi:
        return (lo - 0.5, hi + 0.5)
    if scale_kind == "log":
        if lo > 0 and hi > 0:
            return (10 ** math.floor(math.log10(lo)),
                    10 ** math.ceil(math.log10(hi)))
        return (lo, hi)
    return _nice_domain(lo, hi)


def _render(st, W, H, M):
    iw = W - M["left"] - M["right"]
    ih = H - M["top"] - M["bottom"]

    # pre-bin histograms so they participate in y-domain
    # (kept here because hist's binning depends on user-supplied `bins` opt
    # and the result is reused by both domain and draw)
    for a in st["artists"]:
        if a["type"] == "hist":
            a["_bins"] = _histogram(a["data"], a["opts"].get("bins", 10))

    # ---- x scale ----
    has_bar = any(a["type"] == "bar" for a in st["artists"])
    if has_bar:
        cats = []
        for a in st["artists"]:
            if a["type"] == "bar":
                for c in a["cats"]:
                    if c not in cats: cats.append(c)
        x_scale = _BandScale(cats, 0, iw)
        x_ticks = cats
    else:
        x_lo, x_hi = _scan_domain(st["artists"], "x")
        x_min, x_max = _resolve_domain(x_lo, x_hi, st["xlim"], st["xscale"])
        x_scale = (_LogScale if st["xscale"] == "log" else _LinearScale)(x_min, x_max, 0, iw)
        x_ticks = x_scale.ticks(8)

    # ---- y scale ----
    y_lo, y_hi = _scan_domain(st["artists"], "y")
    force_zero = has_bar or any(a["type"] == "hist" for a in st["artists"])
    y_min, y_max = _resolve_domain(y_lo, y_hi, st["ylim"], st["yscale"],
                                    force_zero=force_zero)
    y_scale = (_LogScale if st["yscale"] == "log" else _LinearScale)(y_min, y_max, ih, 0)
    y_ticks = y_scale.ticks(8)

    # ---- emit SVG ----
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{_FONT}" font-size="11" '
        f'style="background:#fff">'
    ]
    parts.append(f'<g transform="translate({M["left"]},{M["top"]})">')

    # grid
    if st["grid"]:
        gw = _GRIDSPEC["width"]; gd = _GRIDSPEC["dasharray"]
        if not has_bar:
            for t in x_ticks:
                x = x_scale(t)
                parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="0" y2="{ih}" '
                             f'stroke="{_GRID}" stroke-width="{gw}" stroke-dasharray="{gd}"/>')
        for t in y_ticks:
            y = y_scale(t)
            parts.append(f'<line x1="0" x2="{iw}" y1="{y:.2f}" y2="{y:.2f}" '
                         f'stroke="{_GRID}" stroke-width="{gw}" stroke-dasharray="{gd}"/>')

    # color assignment — only color-cycle artists consume the cycle
    color_idx = 0
    for a in st["artists"]:
        spec = get_artist(a["type"])
        user_color = _resolve_color(a["opts"].get("color"))
        if user_color is not None:
            a["_color"] = user_color
        elif spec is not None and spec.uses_color_cycle:
            a["_color"] = TAB10[color_idx % 10]
            color_idx += 1
        else:
            a["_color"] = spec.default_color if spec else None

    # build the render context once — passed to every draw call
    def _ctx_for(a):
        return RenderContext(
            x_scale=x_scale, y_scale=y_scale, iw=iw, ih=ih,
            color=a["_color"], defaults=_D, dash=_DASH,
        )

    # three-pass draw: background → data → foreground
    by_layer = {"background": [], "data": [], "foreground": []}
    for a in st["artists"]:
        spec = get_artist(a["type"])
        if spec is None: continue
        by_layer[spec.layer].append(a)
    for layer in ("background", "data", "foreground"):
        for a in by_layer[layer]:
            spec = get_artist(a["type"])
            parts.append(spec.draw(a, _ctx_for(a)))

    # spines (4 sides)
    for x1, y1, x2, y2 in [(0, 0, iw, 0), (0, ih, iw, ih), (0, 0, 0, ih), (iw, 0, iw, ih)]:
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                     f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')

    # x ticks + labels
    tick_size = _FONTSPEC["tick_size"]
    label_size = _FONTSPEC["label_size"]
    title_size = _FONTSPEC["title_size"]

    for t in x_ticks:
        x = (x_scale(t) + x_scale.bandwidth / 2) if has_bar else x_scale(t)
        parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{ih}" y2="{ih - _TICK_LEN}" '
                     f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')
        parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="0" y2="{_TICK_LEN}" '
                     f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')
        parts.append(_text_path(_fmt_tick(t), x, ih + _TICK_LEN + _TICK_PAD + 8,
                                tick_size, anchor="middle"))

    # y ticks + labels
    for t in y_ticks:
        y = y_scale(t)
        parts.append(f'<line x1="0" x2="{_TICK_LEN}" y1="{y:.2f}" y2="{y:.2f}" '
                     f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')
        parts.append(f'<line x1="{iw}" x2="{iw - _TICK_LEN}" y1="{y:.2f}" y2="{y:.2f}" '
                     f'stroke="{_SPINE}" stroke-width="{_SPW}"/>')
        parts.append(_text_path(_fmt_tick(t), -_TICK_PAD, y + 4, tick_size, anchor="end"))

    # axis labels + title
    if st["xlabel"]:
        parts.append(_text_path(st["xlabel"], iw / 2, ih + M["bottom"] - 8,
                                label_size, anchor="middle"))
    if st["ylabel"]:
        ylabel_path = _text_path(st["ylabel"], 0, 0, label_size, anchor="middle")
        parts.append(f'<g transform="translate({-(M["left"] - 12)},{ih/2}) rotate(-90)">'
                     f'{ylabel_path}</g>')
    if st["title"]:
        parts.append(_text_path(st["title"], iw / 2, -10, title_size, anchor="middle"))

    # legend — each artist's spec supplies its own swatch via legend_swatch.
    # Custom artists that don't define one fall back to a colored line.
    if st["legend"]:
        labeled = [a for a in st["artists"] if a["opts"].get("label")]
        if labeled:
            row_h = _LEGSPEC["row_height"]
            pad_x = _LEGSPEC["pad_x"]
            pad_y = _LEGSPEC["pad_y"]
            sw    = _LEGSPEC["swatch_width"]
            max_text = max(_measure_text(a["opts"]["label"], tick_size) for a in labeled)
            lw = sw + 6 + max_text + 2 * pad_x
            lh = len(labeled) * row_h + 2 * pad_y
            lx, ly = iw - lw - _LEGSPEC["border_offset"], _LEGSPEC["border_offset"]
            parts.append(f'<g transform="translate({lx:.2f},{ly})">')
            parts.append(f'<rect x="0" y="0" width="{lw:.2f}" height="{lh}" '
                         f'fill="{_LEGSPEC["background"]}" stroke="{_SPINE}" '
                         f'stroke-width="{_SPW}" opacity="{_LEGSPEC["opacity"]}"/>')
            for i, a in enumerate(labeled):
                ry = pad_y + i * row_h + row_h / 2
                spec = get_artist(a["type"])
                if spec is not None and spec.legend_swatch is not None:
                    parts.append(spec.legend_swatch(a, _ctx_for(a), pad_x, ry))
                else:
                    parts.append(f'<line x1="{pad_x}" x2="{pad_x + sw}" y1="{ry}" y2="{ry}" '
                                 f'stroke="{a["_color"]}" stroke-width="{_D["linewidth"]}"/>')
                parts.append(_text_path(a["opts"]["label"], pad_x + sw + 6, ry + 4,
                                        tick_size, anchor="start"))
            parts.append('</g>')

    parts.append('</g></svg>')
    return "".join(parts)
