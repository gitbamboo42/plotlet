"""Text-rendering artists — `text` for data-anchored labels, `annotate` for
matplotlib-style label-with-arrow.

Both render glyph paths from the bundled DejaVu Sans so output stays
font-independent.
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._spec import _D
from .._artist_impl import _artist_text, _artist_annotate
from ._shared import _xy_minmax


# --- text ---
# Data-anchored labels. Accepts scalar `(x, y, s)` for a single label or
# parallel lists for batched annotation. Strings broadcast: pass `s="*"`
# with list `xs`/`ys` to mark every point with the same glyph.

def _text_record(args, kw):
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
