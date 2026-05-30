"""Text-rendering artists — `text` for data-anchored labels, `annotate` for
matplotlib-style label-with-arrow.

  c.text(x, y, "label")                          # single label (scalars)
  c.text(xs, ys, ["A", "B", "C"])                # multiple labels (lists)
  c.text(data=df, x="x", y="y", label="name")    # long-form (column names)

Both render glyph paths from the bundled DejaVu Sans so output stays
font-independent.
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._spec import _D
from ..draw import text_path, segment, rect as draw_rect, polygon as draw_polygon
from ..draw import measure_text
from ._shared import _xy_minmax


_HA_TO_ANCHOR = {"left": "start", "center": "middle", "right": "end"}


def _resolve_bbox(bbox):
    """Normalize a `bbox=` value into a dict (or None to skip).
    `True` → spec-default background; dict → used as-is with per-key
    defaults from `spec.json:defaults.text_bbox`."""
    if bbox is None or bbox is False:
        return None
    if bbox is True:
        bbox = {}
    bb = _D["text_bbox"]
    return {
        "facecolor": bbox.get("facecolor", bb["facecolor"]),
        "edgecolor": bbox.get("edgecolor", bb["edgecolor"]),
        "pad":       float(bbox.get("pad", bb["pad"])),
        "alpha":     float(bbox.get("alpha", bb["alpha"])),
        "stroke_width": float(bbox.get("linewidth", bb["linewidth"])),
    }


def _text_bbox_rect(s, x, y_baseline, fontsize, anchor, bb):
    """Emit the rectangle that sits behind a text label. `(x, y_baseline)`
    is the same anchor SVG `text_path` uses; we recover the bounding box
    from the anchor offsets plus the measured glyph width."""
    w = measure_text(s, fontsize)
    if anchor == "middle":   rx = x - w / 2
    elif anchor == "end":    rx = x - w
    else:                    rx = x
    # DejaVu ascent ≈ 0.78 * fontsize, descent ≈ 0.22.
    ry = y_baseline - fontsize * 0.78
    rh = fontsize * 1.0
    pad = bb["pad"]
    return draw_rect(rx - pad, ry - pad, w + 2 * pad, rh + 2 * pad,
                      fill=bb["facecolor"],
                      stroke=bb["edgecolor"] if bb["edgecolor"] != "none" else None,
                      stroke_width=bb["stroke_width"],
                      alpha=bb["alpha"])


def _artist_annotate(a, xs_, ys_, col):
    """Text label at `xytext`, optionally connected to `xy` by an arrow.

    Pixel placement and arrow geometry both run through the panel's
    scales — the user gives data coordinates, we draw in pixels. The
    arrowhead is a small filled triangle; the line stops at the head's
    base so the seam doesn't show through anti-aliasing.
    """
    opts = a["opts"]
    fontsize = opts.get("fontsize", _D["text_size"])
    ha = opts.get("ha", "left")
    va = opts.get("va", "baseline")
    color = opts.get("color") or col or _D["text_color"]
    anchor = _HA_TO_ANCHOR.get(ha, "start")
    if va == "top":      va_offset = fontsize * 0.78
    elif va == "center": va_offset = fontsize * 0.34
    elif va == "bottom": va_offset = 0.0
    else:                va_offset = 0.0

    x_xy, y_xy = a["xy"]
    x_tx, y_tx = a["xytext"]
    px_xy, py_xy = xs_(x_xy), ys_(y_xy)
    px_tx, py_tx = xs_(x_tx), ys_(y_tx)
    if not all(math.isfinite(v) for v in (px_xy, py_xy, px_tx, py_tx)):
        return ""

    out = []
    if opts.get("arrow", True):
        arr = _D["annotate"]
        head_len = opts.get("arrow_head", arr["arrow_head"])
        line_w = opts.get("arrow_width", arr["arrow_width"])
        dx, dy = px_xy - px_tx, py_xy - py_tx
        dist = math.hypot(dx, dy)
        if dist > head_len:
            ux, uy = dx / dist, dy / dist
            # Line stops at the back of the arrowhead.
            line_end_x = px_xy - ux * head_len
            line_end_y = py_xy - uy * head_len
            out.append(segment(px_tx, py_tx, line_end_x, line_end_y,
                                color=color, width=line_w))
            # Triangular head: tip at xy, base perpendicular to the line.
            half = head_len * arr["arrow_base_ratio"]
            perp_x, perp_y = -uy, ux
            x1 = line_end_x + perp_x * half
            y1 = line_end_y + perp_y * half
            x2 = line_end_x - perp_x * half
            y2 = line_end_y - perp_y * half
            out.append(draw_polygon([(px_xy, py_xy), (x1, y1), (x2, y2)],
                                    fill=color))
    bb = _resolve_bbox(opts.get("bbox"))
    text_y = py_tx + va_offset
    if bb is not None:
        out.append(_text_bbox_rect(a["text"], px_tx, text_y, fontsize, anchor, bb))
    out.append(text_path(a["text"], px_tx, text_y,
                          fontsize, anchor=anchor, color=color))
    return "".join(out)


def _artist_text(a, xs_, ys_, col):
    """Render text labels at data coordinates. Accepts parallel
    `xs` / `ys` / `labels` lists. Empty labels are skipped."""
    opts = a["opts"]
    fontsize = opts.get("fontsize", _D["text_size"])
    ha = opts.get("ha", "left")
    va = opts.get("va", "baseline")
    color = opts.get("color") or col or _D["text_color"]
    dx = opts.get("dx", 0)
    dy = opts.get("dy", 0)
    rotation = opts.get("rotation", 0)
    anchor = _HA_TO_ANCHOR.get(ha, "start")
    # va offset on top of the SVG baseline. Cap-height of DejaVu ≈ 0.7 * size;
    # x-height ≈ 0.5. These constants give visually-centered placement for
    # the three common va values without measuring per-glyph metrics.
    if va == "top":
        va_offset = fontsize * 0.78
    elif va == "center":
        va_offset = fontsize * 0.34
    elif va == "bottom":
        va_offset = 0.0
    else:  # baseline
        va_offset = 0.0
    bb = _resolve_bbox(opts.get("bbox"))
    out = []
    for x, y, s in zip(a["xs"], a["ys"], a["labels"]):
        if s is None or s == "":
            continue
        px = xs_(x) + dx
        py = ys_(y) + dy + va_offset
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        parts = []
        if bb is not None:
            parts.append(_text_bbox_rect(str(s), px, py, fontsize, anchor, bb))
        parts.append(text_path(str(s), px, py, fontsize, anchor=anchor, color=color))
        if rotation:
            # SVG `rotate(deg, cx, cy)` is clockwise in screen space (y-down);
            # matplotlib's `rotation=` is counterclockwise. Negate to match.
            # Rotation anchor is the ha/va alignment point — same as matplotlib's
            # `rotation_mode="anchor"`.
            out.append(f'<g transform="rotate({-rotation:g},{px:.2f},{py:.2f})">'
                       + "".join(parts) + "</g>")
        else:
            out.extend(parts)
    return "".join(out)


# --- text ---
# Data-anchored labels. Accepts scalar `(x, y, s)` for a single label or
# parallel lists for batched annotation. Strings broadcast: pass `s="*"`
# with list `xs`/`ys` to mark every point with the same glyph.

def _text_record(args, kw):
    # Long-form path: c.text(data=df, x="col", y="col", label="col")
    if "data" in kw or "x" in kw or "y" in kw or "label" in kw:
        kw = dict(kw)
        data = kw.pop("data", None)
        x_col = kw.pop("x", None)
        y_col = kw.pop("y", None)
        label_col = kw.pop("label", None)
        if data is None or x_col is None or y_col is None or label_col is None:
            raise TypeError(
                "text long-form requires data=, x=, y=, label=."
            )
        xs = to_list(data[x_col])
        ys = to_list(data[y_col])
        labels = [str(v) for v in to_list(data[label_col])]
        return {"type": "text", "xs": xs, "ys": ys, "labels": labels, "opts": kw}

    x, y, s = args[0], args[1], args[2]
    x_is_scalar = not (hasattr(x, "__iter__") and not isinstance(x, str))
    if x_is_scalar:
        xs = [x]; ys = [y]; labels = [s]
    else:
        xs = to_list(x); ys = to_list(y)
        if isinstance(s, str):
            labels = [s] * len(xs)
        else:
            labels = list(s)
        if not (len(xs) == len(ys) == len(labels)):
            raise ValueError(
                f"text() expects xs, ys, labels to share length; "
                f"got {len(xs)}, {len(ys)}, {len(labels)}"
            )
    return {"type": "text", "xs": xs, "ys": ys, "labels": labels, "opts": kw}


def _text_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["ys"]))
    return out


add_artist(ArtistSpec(
    name="text",
    record=_text_record,
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: a["ys"],
    draw=lambda a, ctx: _artist_text(a, ctx.x_scale, ctx.y_scale, ctx.color),
    layer="foreground",
    uses_color_cycle=False,
    default_color=_D["text_color"],
    data_attrs=_text_data_attrs,
))


# --- annotate ---
# Text label at `xytext` with optional arrow to `xy` — matplotlib's
# `ax.annotate(...)` staple. Both points are in data coordinates so the
# arrow follows the axis through resizes / share_x scaling.

def _annotate_record(args, kw):
    # Don't mutate `kw` — record() is called on every re-render against
    # the original recorded dict, so a destructive `kw.pop` would lose
    # xy/xytext on the second to_svg() call.
    text = args[0]
    if "xy" not in kw:
        raise TypeError("annotate() requires xy=(x, y)")
    xy = tuple(kw["xy"])
    xytext = tuple(kw.get("xytext", xy))
    opts = {k: v for k, v in kw.items() if k not in ("xy", "xytext")}
    return {"type": "annotate", "text": str(text),
            "xy": xy, "xytext": xytext, "opts": opts}


def _annotate_xdomain(a):  return [a["xy"][0], a["xytext"][0]]
def _annotate_ydomain(a):  return [a["xy"][1], a["xytext"][1]]


def _annotate_data_attrs(a):
    return {
        "x":  a["xy"][0],     "y":  a["xy"][1],
        "tx": a["xytext"][0], "ty": a["xytext"][1],
        "text": a["text"],
    }


add_artist(ArtistSpec(
    name="annotate",
    record=_annotate_record,
    xdomain=_annotate_xdomain,
    ydomain=_annotate_ydomain,
    draw=lambda a, ctx: _artist_annotate(a, ctx.x_scale, ctx.y_scale, ctx.color),
    layer="foreground",
    uses_color_cycle=False,
    default_color=_D["text_color"],
    data_attrs=_annotate_data_attrs,
))
