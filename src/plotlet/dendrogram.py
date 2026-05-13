"""Hierarchical clustering dendrogram artist."""
from __future__ import annotations

import math

from scipy.cluster.hierarchy import linkage as _scipy_linkage
from scipy.cluster.hierarchy import dendrogram as _scipy_dendrogram

from ._spec import _D
from .colors import _resolve_color


_ORIENTS = ("top", "bottom", "left", "right")


def _normalize_dcoords(dcoord_rows):
    # Rescale non-zero merge heights so the shortest merge isn't visually
    # zero. Zero entries stay zero (leaf endpoints).
    nonzero = [v for row in dcoord_rows for v in row if v != 0.0]
    if not nonzero:
        return dcoord_rows
    y_min, y_max = min(nonzero), max(nonzero)
    interval = y_max - y_min
    if interval == 0.0:
        return dcoord_rows
    return [
        [((v - y_min) / interval + 0.2) if v != 0.0 else 0.0 for v in row]
        for row in dcoord_rows
    ]


def _compute_coords(data, linkage, method, metric):
    if linkage is None:
        if data is None:
            raise ValueError("dendrogram(): pass either data= or linkage=")
        if len(data) < 2:
            raise ValueError(
                f"dendrogram(): need at least 2 observations, got {len(data)}"
            )
        Z = _scipy_linkage(data, method=method, metric=metric)
    else:
        Z = linkage
    info = _scipy_dendrogram(Z, no_plot=True)
    # scipy emits icoord at 5, 15, 25, ... — rescale via (v-5)/10 so leaf
    # endpoints land at integer category positions 0..n-1, aligning with
    # plotlet's category scale when labels= is supplied. Cast to Python
    # types to keep np scalars out of SVG attrs.
    icoord = [[(float(v) - 5.0) / 10.0 for v in row] for row in info["icoord"]]
    dcoord = _normalize_dcoords([[float(v) for v in row] for row in info["dcoord"]])
    leaves = [int(v) for v in info["leaves"]]
    return icoord, dcoord, leaves


def _dendrogram_record(args, kw):
    kw = dict(kw)
    data = args[0] if args else kw.pop("data", None)
    if data is not None and hasattr(data, "tolist"):
        data = data.tolist()
    linkage = kw.pop("linkage", None)
    method = kw.pop("method", "single")
    metric = kw.pop("metric", "euclidean")
    orient = kw.pop("orient", "top")
    labels = kw.pop("labels", None)
    if orient not in _ORIENTS:
        raise ValueError(
            f"dendrogram(): orient={orient!r}; expected one of {_ORIENTS}"
        )
    icoord, dcoord, leaves = _compute_coords(data, linkage, method, metric)
    n_leaves = len(leaves)
    max_h = max((v for row in dcoord for v in row), default=1.0) or 1.0
    leaf_labels = None
    if labels is not None:
        labels = list(labels)
        if len(labels) != n_leaves:
            raise ValueError(
                f"dendrogram(): labels has {len(labels)} entries but data "
                f"has {n_leaves} leaves"
            )
        leaf_labels = [str(labels[i]) for i in leaves]
    return {
        "type": "dendrogram",
        "_icoord": icoord,
        "_dcoord": dcoord,
        "_leaves": leaves,
        "_n_leaves": n_leaves,
        "_max_h": max_h,
        "_leaf_labels": leaf_labels,
        "orient": orient,
        "opts": kw,
    }


def _dendrogram_xdomain(a):
    if a["orient"] in ("top", "bottom"):
        if a["_leaf_labels"] is not None:
            return a["_leaf_labels"]
        return [0.0, a["_n_leaves"]]
    return [0.0, a["_max_h"]]


def _dendrogram_ydomain(a):
    if a["orient"] in ("top", "bottom"):
        return [0.0, a["_max_h"]]
    if a["_leaf_labels"] is not None:
        return a["_leaf_labels"]
    return [0.0, a["_n_leaves"]]


def _orient_xy(orient, ic, dc, max_h):
    if orient == "top":
        return ic, dc
    if orient == "bottom":
        return ic, [max_h - v for v in dc]
    if orient == "right":
        return dc, ic
    return [max_h - v for v in dc], ic  # left


def _leaf_axis_pos(scale, labels, idx):
    # Numeric path: each leaf occupies the cell [i, i+1] in axis units;
    # center it at i + 0.5. xdomain is [0, n], so the n leaves tile the
    # axis exactly.
    if labels is None:
        return scale(idx + 0.5)
    n = len(labels)
    lo = int(math.floor(idx))
    if idx == lo and 0 <= lo < n:
        return scale(labels[lo])
    lo = max(0, min(n - 2, lo))
    return scale(labels[lo]) + (idx - lo) * scale.step


def _dendrogram_draw(a, ctx):
    col = _resolve_color(a["opts"].get("color")) or ctx.color or _D["dendrogram_color"]
    lw = a["opts"].get("linewidth", _D["dendrogram_linewidth"])
    orient = a["orient"]
    max_h = a["_max_h"]
    labels = a["_leaf_labels"]
    leaf_on_x = orient in ("top", "bottom")
    out = []
    for ic, dc in zip(a["_icoord"], a["_dcoord"]):
        xs, ys = _orient_xy(orient, ic, dc, max_h)
        pts = []
        ok = True
        for x, y in zip(xs, ys):
            if leaf_on_x:
                px = _leaf_axis_pos(ctx.x_scale, labels, x)
                py = ctx.y_scale(y)
            else:
                px = ctx.x_scale(x)
                py = _leaf_axis_pos(ctx.y_scale, labels, y)
            if not (math.isfinite(px) and math.isfinite(py)):
                ok = False
                break
            pts.append((px, py))
        if not ok:
            continue
        d = (
            f"M{pts[0][0]:.2f},{pts[0][1]:.2f}"
            f"L{pts[1][0]:.2f},{pts[1][1]:.2f}"
            f"L{pts[2][0]:.2f},{pts[2][1]:.2f}"
            f"L{pts[3][0]:.2f},{pts[3][1]:.2f}"
        )
        out.append(
            f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{lw}"/>'
        )
    return "".join(out)


def _dendrogram_frame_defaults(args, kw):
    leaf_on_x = kw.get("orient", "top") in ("top", "bottom")
    has_labels = kw.get("labels") is not None
    out = [("spines", [], {"top": False, "right": False,
                            "bottom": False, "left": False})]
    out.append(("yticks" if leaf_on_x else "xticks", [[]], {}))
    if not has_labels:
        out.append(("xticks" if leaf_on_x else "yticks", [[]], {}))
    return out


def _dendrogram_axis_order(a):
    if a["_leaf_labels"] is None:
        return None
    axis = "x" if a["orient"] in ("top", "bottom") else "y"
    return {axis: a["_leaf_labels"]}


def _dendrogram_data_attrs(a):
    out = {
        "orient": a["orient"],
        "n-leaves": a["_n_leaves"],
        "max-height": round(a["_max_h"], 6),
        "leaves": a["_leaves"],
    }
    if a["_leaf_labels"] is not None:
        out["leaf-labels"] = a["_leaf_labels"]
    return out
