"""`pt.describe` — one-call text summary of a rendered figure.

Reads only the `data-plotlet-*` schema off the SVG (docs/AI_ATTRS.md),
like `pt.layout_diagram` — a schema consumer, not a pipeline stage. The
summary states what the finished SVG *actually says*, not what the
recording intended; if the two disagree, that disagreement is the bug.

    >>> print(pt.describe(c))
    SVG 668×405 plotlet=0.6.4 schema=2
      PANEL 0 title="Daily revenue" xlabel="day" ylabel="USD"
        xscale=linear xlim=1,4  yscale=linear ylim=10.05,15.15
        ARTIST 0 line label="actual" color=#1f77b4 n=4 x-min=1 x-max=4 ...

Keys are the schema's own attribute names (minus the `data-plotlet-`
prefix), so a line here can be grepped straight back to the SVG.
Accepts a Chart / Layout / anything with `to_svg()`, or a raw SVG
string (e.g. read from a saved file).
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

_P = "data-plotlet-"

# Attrs woven into the PANEL header / scale lines — everything else a
# panel carries (bboxes, yflip, ...) trails on the scale line as-is.
_PANEL_HEAD = ("title", "xlabel", "ylabel")
_PANEL_GEOM = ("panel-bbox", "data-area")


def describe(fig) -> str:
    """Summarize a figure's semantics as indented text — plot kinds,
    axis labels, scales, resolved limits, and per-artist label / color /
    range attrs. One line per element; print the result."""
    svg = fig if isinstance(fig, str) else fig.to_svg()
    root = ET.fromstring(svg)
    w, h = root.get("width"), root.get("height")
    lines = [f"SVG {w}×{h}"
             f" plotlet={root.get(_P + 'version')}"
             f" schema={root.get(_P + 'schema')}"]
    counters = {"panel": 0, "artist": 0}
    _walk(root, lines, indent=1, counters=counters)
    return "\n".join(lines)


def _attrs(el) -> dict:
    """The element's `data-plotlet-*` attrs, prefix stripped, document
    order preserved."""
    return {k[len(_P):]: v for k, v in el.attrib.items() if k.startswith(_P)}


def _walk(el, lines, indent, counters):
    for child in el:
        a = _attrs(child)
        kind = a.get("kind")
        if kind == "panel":
            _emit_panel(child, a, lines, indent, counters)
        elif kind == "inset":
            lines.append("  " * indent + "INSET")
            _walk(child, lines, indent + 1, counters)
        elif kind == "legend":
            bbox = a.get("legend-bbox", "")
            _x, _y, w, h = bbox.split(",") if bbox else ("", "", "?", "?")
            lines.append("  " * indent + f"LEGEND {w}×{h}")
        elif kind == "diagram":
            lines.append("  " * indent + "DIAGRAM")
        elif child.get("class") == "plotlet-artist":
            _emit_artist(a, lines, indent)
        else:
            _walk(child, lines, indent, counters)


def _emit_panel(el, a, lines, indent, counters):
    pad = "  " * indent
    head = [f"PANEL {counters['panel']}"]
    counters["panel"] += 1
    for k in _PANEL_HEAD:
        if a.get(k):
            head.append(f'{k}="{a[k]}"')
    lines.append(pad + " ".join(head))

    scale = []
    for axis in ("x", "y"):
        bits = [f"{axis}scale={a.get(axis + 'scale', '?')}"]
        if a.get(axis + "lim"):
            bits.append(f"{axis}lim={a[axis + 'lim']}")
        cats = _categories(el, axis)
        if cats is not None:
            shown = ",".join(map(str, cats[:6]))
            more = f",… +{len(cats) - 6}" if len(cats) > 6 else ""
            bits.append(f"{axis}categories=[{shown}{more}]")
        scale.append(" ".join(bits))
    trailing = [f"{k}={v}" for k, v in a.items()
                if k not in ("kind", *_PANEL_HEAD, *_PANEL_GEOM)
                and not k.startswith(("xscale", "yscale", "xlim", "ylim"))]
    lines.append(pad + "  " + "  ".join(scale + trailing))

    # Artists render inside the panel <g>; a per-panel artist counter
    # would just repeat data-plotlet-index, so recurse with the shared
    # counters and let the artist attr speak.
    _walk(el, lines, indent + 1, counters)


def _emit_artist(a, lines, indent):
    head = [f"ARTIST {a.get('index', '?')}", a.get("type", "?")]
    if a.get("label") is not None:
        head.append(f'label="{a["label"]}"')
    if a.get("color"):
        head.append(f"color={a['color']}")
    rest = [f"{k}={v}" for k, v in a.items()
            if k not in ("type", "index", "label", "color")]
    lines.append("  " * indent + " ".join(head + rest))


def _categories(panel_el, axis) -> list | None:
    """Category labels from the panel's `<metadata>` payload child
    (docs/AI_ATTRS.md, "Categorical lists"). None on numeric axes."""
    for md in panel_el:
        if md.get(_P + "payload") == f"{axis}categories":
            return json.loads(md.text)
    return None
