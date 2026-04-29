"""Figure class, the render orchestrator, and the public `figure()` factory.

This is where the deferred-render pipeline lives:

  1. `figure()` returns a `Figure` whose methods record into `_calls`.
  2. `Figure.to_svg()` calls `_render(_replay(), ...)`.
  3. `_render` does: domain compute → scales → grid → artists → spines/ticks
     → labels/title → legend.
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
from .artists import (
    _to_pylist, _histogram,
    _artist_plot, _artist_scatter, _artist_bar, _artist_hist, _artist_fill_between,
    _marker_at,
)

_TICK_LEN = _FRAME["tick_length"]
_TICK_PAD = _FRAME["tick_pad"]
_SPINE = _FRAME["color"]
_SPW = _FRAME["width"]
_GRID = _GRIDSPEC["color"]
_FONT = _FONTSPEC["family"]


_RECORDABLE = {
    "plot", "scatter", "bar", "hist", "fill_between",
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
        if name in _RECORDABLE:
            def recorder(*args, **kwargs):
                self._calls.append((name, list(args), dict(kwargs)))
                return self
            return recorder
        raise AttributeError(f"Figure has no method {name!r}")

    # ------------------------------------------------------------- replay
    def _replay(self):
        st = {
            "artists": [], "title": "", "xlabel": "", "ylabel": "",
            "xlim": None, "ylim": None, "xscale": "linear", "yscale": "linear",
            "grid": False, "legend": False,
        }
        for name, args, kw in self._calls:
            if name == "plot":
                st["artists"].append({"type": "plot", "xs": _to_pylist(args[0]),
                                      "ys": _to_pylist(args[1]), "opts": kw})
            elif name == "scatter":
                st["artists"].append({"type": "scatter", "xs": _to_pylist(args[0]),
                                      "ys": _to_pylist(args[1]), "opts": kw})
            elif name == "bar":
                st["artists"].append({"type": "bar", "cats": _to_pylist(args[0]),
                                      "vals": _to_pylist(args[1]), "opts": kw})
            elif name == "hist":
                st["artists"].append({"type": "hist",
                                      "data": _to_pylist(args[0]), "opts": kw})
            elif name == "fill_between":
                st["artists"].append({"type": "fill_between",
                                      "xs": _to_pylist(args[0]),
                                      "y1": _to_pylist(args[1]),
                                      "y2": _to_pylist(args[2]), "opts": kw})
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
    """Construct a new Figure. All options are passed through to `Figure(...)`."""
    return Figure(width=width, height=height, **opts)


# ---------------------------------------------------------------------------
# render orchestrator
# ---------------------------------------------------------------------------

def _render(st, W, H, M):
    iw = W - M["left"] - M["right"]
    ih = H - M["top"] - M["bottom"]

    # pre-bin histograms so they participate in y-domain
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
        x_min, x_max = math.inf, -math.inf
        for a in st["artists"]:
            if a["type"] in ("plot", "scatter", "fill_between"):
                for v in a["xs"]:
                    if v < x_min: x_min = v
                    if v > x_max: x_max = v
            elif a["type"] == "hist":
                for b in a["_bins"]:
                    if b["x0"] < x_min: x_min = b["x0"]
                    if b["x1"] > x_max: x_max = b["x1"]
        if st["xlim"] is not None:
            x_min, x_max = st["xlim"]
        elif math.isinf(x_min):
            x_min, x_max = 0, 1
        elif x_min == x_max:
            x_min -= 0.5; x_max += 0.5
        elif st["xscale"] == "log":
            if x_min > 0 and x_max > 0:
                x_min = 10 ** math.floor(math.log10(x_min))
                x_max = 10 ** math.ceil(math.log10(x_max))
        else:
            x_min, x_max = _nice_domain(x_min, x_max)
        x_scale = (_LogScale if st["xscale"] == "log" else _LinearScale)(x_min, x_max, 0, iw)
        x_ticks = x_scale.ticks(8)

    # ---- y scale ----
    y_min, y_max = math.inf, -math.inf
    for a in st["artists"]:
        if a["type"] in ("plot", "scatter"):
            for v in a["ys"]:
                if v < y_min: y_min = v
                if v > y_max: y_max = v
        elif a["type"] == "bar":
            for v in a["vals"]:
                if v < y_min: y_min = v
                if v > y_max: y_max = v
        elif a["type"] == "fill_between":
            for v in a["y1"] + a["y2"]:
                if v < y_min: y_min = v
                if v > y_max: y_max = v
        elif a["type"] == "hist":
            for b in a["_bins"]:
                if b["count"] > y_max: y_max = b["count"]
            if y_min > 0: y_min = 0
    if has_bar and y_min > 0: y_min = 0
    if st["ylim"] is not None:
        y_min, y_max = st["ylim"]
    elif math.isinf(y_min):
        y_min, y_max = 0, 1
    elif y_min == y_max:
        y_min -= 0.5; y_max += 0.5
    elif st["yscale"] == "log":
        if y_min > 0 and y_max > 0:
            y_min = 10 ** math.floor(math.log10(y_min))
            y_max = 10 ** math.ceil(math.log10(y_max))
    else:
        y_min, y_max = _nice_domain(y_min, y_max)
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

    # artists
    color_idx = [0]
    def next_color():
        c = TAB10[color_idx[0] % 10]; color_idx[0] += 1; return c

    for a in st["artists"]:
        col = _resolve_color(a["opts"].get("color")) or next_color()
        a["_color"] = col
        if a["type"] == "plot":
            parts.append(_artist_plot(a, x_scale, y_scale, col))
        elif a["type"] == "scatter":
            parts.append(_artist_scatter(a, x_scale, y_scale, col))
        elif a["type"] == "bar":
            parts.append(_artist_bar(a, x_scale, y_scale, col))
        elif a["type"] == "hist":
            parts.append(_artist_hist(a, x_scale, y_scale, ih, col))
        elif a["type"] == "fill_between":
            parts.append(_artist_fill_between(a, x_scale, y_scale, col))

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

    # legend
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
                if a["type"] in ("plot", "fill_between"):
                    ls = a["opts"].get("linestyle")
                    da = f' stroke-dasharray="{_DASH[ls]}"' if ls and _DASH.get(ls) else ""
                    parts.append(f'<line x1="{pad_x}" x2="{pad_x + sw}" y1="{ry}" y2="{ry}" '
                                 f'stroke="{a["_color"]}" '
                                 f'stroke-width="{a["opts"].get("linewidth", _D["linewidth"])}"{da}/>')
                    if a["opts"].get("marker"):
                        parts.append(_marker_at(a["opts"]["marker"], pad_x + sw / 2, ry,
                                                a["opts"].get("markersize", _D["markersize"]),
                                                a["_color"], 1))
                elif a["type"] == "scatter":
                    s_size = math.sqrt(a["opts"].get("s", _D["scatter_s"])) / 2
                    parts.append(_marker_at(a["opts"].get("marker", "o"),
                                            pad_x + sw / 2, ry, s_size, a["_color"],
                                            a["opts"].get("alpha", _D["scatter_alpha"])))
                else:
                    parts.append(f'<rect x="{pad_x}" y="{ry - 5}" width="{sw}" height="10" '
                                 f'fill="{a["_color"]}" '
                                 f'opacity="{a["opts"].get("alpha", 1)}"/>')
                parts.append(_text_path(a["opts"]["label"], pad_x + sw + 6, ry + 4,
                                        tick_size, anchor="start"))
            parts.append('</g>')

    parts.append('</g></svg>')
    return "".join(parts)
