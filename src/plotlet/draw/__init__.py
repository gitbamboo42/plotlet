"""Drawing primitives — single entry point for all `draw.*` tools.

    from plotlet import draw

    def my_draw(a, ctx):
        out = []
        for x, y, label in zip(a["xs"], a["ys"], a["labels"]):
            px = ctx.x_scale(x); py = ctx.y_scale(y)
            out.append(draw.marker("o", px, py, 4, ctx.color, 1))
            out.append(draw.text_path(label, px, py - 8, 10, anchor="middle"))
        return "".join(out)
"""
from .primitives import (
    text_path, op, marker, dash_attr,
    segment, rect, circle, path, polyline, polygon,
    arc, errorbar_v, errorbar_h, split_rect, split_pie,
)
from .colors import TAB10, resolve_color, palette, list_palettes, Palette
from .colormaps import (colormap, colormap_lut, list_colormaps,
                        register_colormap, ContinuousNorm)
from .font import (measure_text, cap_height, descender, tick_band_height,
                   rotated_label_bbox, line_height, text_block_height,
                   svg_family)
from .format import coord, stroke_w, opacity, degree
from .linestyles import resolve_linestyle
from ._png import encode_rgb, image_png, encode_rgba, image_png_rgba
from ._raster import (parse_rgb, should_rasterize, splat_disks,
                      splat_disks_by_color, splat_ticks)

__all__ = [
    "text_path", "marker", "op", "segment", "rect", "circle",
    "path", "polyline", "polygon", "arc", "split_rect", "split_pie",
    "errorbar_v", "errorbar_h", "dash_attr",
    "TAB10", "resolve_color", "palette", "list_palettes", "Palette",
    "colormap", "colormap_lut", "list_colormaps", "register_colormap",
    "ContinuousNorm",
    "measure_text", "cap_height", "descender", "tick_band_height",
    "rotated_label_bbox", "line_height", "text_block_height",
    "svg_family",
    "coord", "stroke_w", "opacity", "degree",
    "resolve_linestyle",
    "encode_rgb", "image_png", "encode_rgba", "image_png_rgba",
    "parse_rgb", "should_rasterize", "splat_disks",
    "splat_disks_by_color", "splat_ticks",
]
