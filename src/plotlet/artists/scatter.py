"""Scatter — single-series xy.

  c.scatter(data=df, x="col_x", y="col_y")                # long-form
  c.scatter(data=df, x="col_x", y="col_y", color="red")   # literal color
  c.scatter(data=df, ..., color="group")                  # categorical → palette
  c.scatter(data=df, ..., color="weight")                 # numeric col → cmap
  c.scatter(data=df, ..., color="g", group="subject")     # invisible finer split
  c.scatter(data=df, ..., alpha="cohort",                 # opacity per level
            alphas=(0.3, 1.0))
  c.scatter(data=df, ..., size=3)                         # fixed marker radius (px)
  c.scatter(data=df, ..., size="mass", sizes=(2, 8))      # graded per-point radius
  c.scatter(data=df, ..., style="group")                  # per-level marker glyph

`color=` dispatches on the value:
  * not-a-column string → literal color
  * column with all-numeric values → continuous cmap (cmap/vmin/vmax/norm)
  * column with any non-numeric value → categorical palette
To force a numeric column to be treated as categorical, cast to strings
first: `df["clusters"] = df["clusters"].astype(str)`.

Column-driven categorical splitting (`color`/`group`/`alpha`) is handled
at the Chart layer — the artist itself always sees one series per record.
`size`/`style` are computed per-point and stay inside a single record.
Continuous color is single-record-only — `group`/`alpha` column splits
are dropped on that path.
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list, resolve_aes, palette_color
from ..draw import marker
from ..draw import TAB10
from ..draw import colormap_lut, ContinuousNorm
from .._spec import _D, _LEGSPEC
from ._shared import (_xy_minmax, expand_xy_long_form,
                       DEFAULT_ALPHA_RANGE, _alpha_for_level)


def _artist_scatter(a, xs_, ys_, col, xs, ys, warp=None):
    opts = a["opts"]
    raw_size = opts.get("size", _D["scatter_size"])
    raw_mk = opts.get("marker", "o")
    alpha = opts.get("alpha", _D["scatter_alpha"])
    edgecolor = opts.get("edgecolor")
    linewidth = opts.get("linewidth")
    c_vals = opts.get("c")
    n = len(xs)
    radii   = list(raw_size) if isinstance(raw_size, (list, tuple)) else [raw_size] * n
    markers = list(raw_mk)   if isinstance(raw_mk,   (list, tuple)) else [raw_mk]   * n

    if c_vals is not None:
        cmap_name = opts.get("cmap", _D["default_cmap"])
        lut = colormap_lut(cmap_name)
        normalizer = ContinuousNorm(a["_vmin"], a["_vmax"],
                                    kind=opts.get("norm", "linear"))
        point_colors = []
        for v in c_vals:
            if not (isinstance(v, (int, float)) and v == v):
                point_colors.append("rgb(0,0,0)")
            else:
                idx = int(normalizer.to_unit(v) * 255 + 0.5) * 3
                point_colors.append(f"rgb({lut[idx]},{lut[idx+1]},{lut[idx+2]})")
    else:
        point_colors = [col] * n

    out = []
    for i, (x, y) in enumerate(zip(xs, ys)):
        px, py = xs_(x), ys_(y)
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        out.append(marker(markers[i], px, py, float(radii[i]),
                          point_colors[i], alpha,
                          edgecolor=edgecolor, edgewidth=linewidth,
                          project=warp))
    return "".join(out)


_STYLE_CYCLE = ("o", "s", "^", "v", "x", "+")


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


def _compute_style_array(values):
    vals = to_list(values)
    seen: list = []
    for v in vals:
        if v not in seen:
            seen.append(v)
    mapping = {v: _STYLE_CYCLE[i % len(_STYLE_CYCLE)] for i, v in enumerate(seen)}
    return [mapping[v] for v in vals]


def _expand_with_aesthetics(data, x_col, y_col, color, group, alpha,
                             palette, size, style, sizes, alphas, base_opts):
    """Long-form scatter with `size=`/`style=` per-point arrays. Splits by
    `(color, group, alpha)` tuples; size/marker arrays are sliced per
    sub-record. Equivalent to `expand_xy_long_form` but carries the extra
    per-point payload that line/fill_between don't have."""
    xs_all = to_list(data[x_col])
    ys_all = to_list(data[y_col])
    n = len(xs_all)
    s_arr  = _compute_size_array(data[size], sizes) if size is not None else None
    mk_arr = _compute_style_array(data[style])      if style is not None else None

    # Capture size-aesthetic info for the legend (column name + source
    # value range + pixel range). Stashed on the first returned record
    # so a single size guide renders even when color also splits the
    # data into multiple records.
    size_legend = None
    if size is not None:
        src_vals = [v for v in to_list(data[size])
                    if isinstance(v, (int, float)) and v == v]
        if src_vals:
            size_legend = {
                "col_name": str(size),
                "source_min": min(src_vals),
                "source_max": max(src_vals),
                "sizes_range": tuple(sizes),
            }

    def slice_for(idxs):
        out = dict(base_opts)
        if s_arr  is not None: out["size"]   = [s_arr[i]  for i in idxs]
        if mk_arr is not None: out["marker"] = [mk_arr[i] for i in idxs]
        return out

    color_kind, color_value = resolve_aes(data, color)
    group_kind, group_value = resolve_aes(data, group)
    alpha_kind, alpha_value = resolve_aes(data, alpha)

    if (color_kind == "literal" and group_kind == "literal"
            and alpha_kind == "literal"):
        opts = slice_for(range(n))
        if color_value is not None: opts["color"] = color_value
        if alpha_value is not None: opts["alpha"] = alpha_value
        rec = {"type": "scatter", "xs": xs_all, "ys": ys_all, "opts": opts}
        if size_legend is not None:
            rec["_size_legend"] = size_legend
        return [rec]

    color_vec = color_value if color_kind == "column" else [None] * n
    group_vec = group_value if group_kind == "column" else [None] * n
    alpha_vec = alpha_value if alpha_kind == "column" else [None] * n
    color_levels = list(dict.fromkeys(color_vec))
    alpha_levels = list(dict.fromkeys(alpha_vec))
    triples = list(dict.fromkeys(zip(color_vec, group_vec, alpha_vec)))

    base_opts.pop("label", None)
    records = []
    labeled: set = set()
    for ck, gk, ak in triples:
        idxs = [j for j in range(n)
                if color_vec[j] == ck and group_vec[j] == gk
                and alpha_vec[j] == ak]
        xs_g = [xs_all[j] for j in idxs]
        ys_g = [ys_all[j] for j in idxs]
        opts = slice_for(idxs)
        opts.pop("label", None)
        if color_kind == "column":
            idx = color_levels.index(ck)
            opts["color"] = palette_color(palette, ck, idx) or TAB10[idx % 10]
            if ck not in labeled:
                opts["label"] = str(ck)
                labeled.add(ck)
        elif color_value is not None:
            opts["color"] = color_value
        if alpha_kind == "column":
            opts["alpha"] = _alpha_for_level(alpha_levels.index(ak),
                                              len(alpha_levels), alphas)
        elif alpha_value is not None:
            opts["alpha"] = alpha_value
        records.append({"type": "scatter", "xs": xs_g, "ys": ys_g, "opts": opts})
    if size_legend is not None and records:
        records[0]["_size_legend"] = size_legend
    return records


def _resolve_c_range(c_vals, opts):
    """Return (vmin, vmax) for the cmap normalizer. User overrides win;
    otherwise fall back to the data range. Recorded once so draw and
    legend_gradient share a single source of truth."""
    numeric = [v for v in c_vals if isinstance(v, (int, float)) and v == v]
    vmin = opts.get("vmin")
    vmax = opts.get("vmax")
    if vmin is None: vmin = min(numeric) if numeric else 0.0
    if vmax is None: vmax = max(numeric) if numeric else 1.0
    return vmin, vmax


def _is_continuous(values):
    """Dispatch rule for `color=<col>`: True iff every non-missing value
    is a real number (not bool). NaN tolerated; all-NaN or empty falls
    back to categorical (safer — avoids degenerate cmap)."""
    saw_num = False
    for v in values:
        if v is None:
            continue
        if isinstance(v, float) and v != v:
            continue
        if isinstance(v, bool):
            return False
        if isinstance(v, (int, float)):
            saw_num = True
            continue
        return False
    return saw_num


def _scatter_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "scatter requires long-form input: "
            "c.scatter(data=df, x='col', y='col')."
        )
    data  = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    if data is None or x_col is None or y_col is None:
        raise TypeError(
            "scatter requires data=, x=, y= (color/group/alpha/size/style optional)."
        )
    if "c" in kw:
        raise TypeError(
            "scatter takes `color=<numeric column>` for cmap-based coloring "
            "(numeric column → cmap, categorical → palette, literal → fixed)."
        )
    if "s" in kw:
        raise TypeError(
            "scatter takes `size=` for marker radius (px) "
            "(number → fixed, list → per-point, column → graded via sizes=(lo, hi))."
        )
    color   = kw.pop("color", None)
    group   = kw.pop("group", None)
    alpha   = kw.pop("alpha", None)
    palette = kw.pop("palette", None)
    size    = kw.pop("size", None)
    style   = kw.pop("style", None)
    sizes   = kw.pop("sizes", (2, 7))
    alphas  = kw.pop("alphas", DEFAULT_ALPHA_RANGE)
    # scatter has no line to dash; ignore inherited linestyle/fill.
    kw.pop("linestyle", None)
    kw.pop("fill", None)

    # Resolve `size=`: number/list → literal pixel radius into opts["size"];
    # column name → keep as `size` for the column-mapping path below.
    if size is not None:
        size_kind, size_value = resolve_aes(data, size)
        if size_kind == "column":
            pass  # handled by _expand_with_aesthetics / cmap branch
        elif isinstance(size_value, str):
            raise TypeError(
                f"size={size_value!r} — string must match a column in data; "
                f"pass a number or list for a literal size."
            )
        else:
            kw["size"] = (to_list(size_value)
                          if isinstance(size_value, (list, tuple))
                             or hasattr(size_value, "tolist")
                          else size_value)
            size = None

    color_kind, color_value = resolve_aes(data, color)

    if color_kind == "column" and _is_continuous(color_value):
        # Continuous color: numeric column → cmap. Single record (no
        # group/alpha splitting); size/style compose per-point.
        c_vals = list(color_value)
        kw["c"] = c_vals
        vmin, vmax = _resolve_c_range(c_vals, kw)
        if size is not None:
            kw["size"] = _compute_size_array(data[size], sizes)
        if style is not None:
            kw["marker"] = _compute_style_array(data[style])
        rec = {"type": "scatter",
               "xs": to_list(data[x_col]),
               "ys": to_list(data[y_col]),
               "_vmin": vmin, "_vmax": vmax,
               "opts": kw}
        if size is not None:
            src_vals = [v for v in to_list(data[size])
                        if isinstance(v, (int, float)) and v == v]
            if src_vals:
                rec["_size_legend"] = {
                    "col_name": str(size),
                    "source_min": min(src_vals),
                    "source_max": max(src_vals),
                    "sizes_range": tuple(sizes),
                }
        return rec

    if size is not None or style is not None:
        return _expand_with_aesthetics(data, x_col, y_col, color, group, alpha,
                                        palette, size, style, sizes, alphas, kw)

    # Default long-form: split by (color, group, alpha). scatter has no
    # linestyle splits (no line to dash).
    return expand_xy_long_form("scatter", data, x_col, y_col,
                                color, group, None, alpha,
                                palette, alphas, kw)


def _scatter_xdomain(a): return a["xs"]
def _scatter_ydomain(a): return a["ys"]


def _scatter_data_attrs(a):
    xs, ys = a["xs"], a["ys"]
    out = {"n": len(xs)}
    out.update(_xy_minmax(xs, ys))
    out["marker"] = a["opts"].get("marker", "o")
    return out


def _scatter_draw(a, ctx):
    return _artist_scatter(a, ctx.x_scale, ctx.y_scale, ctx.color,
                           a["xs"], a["ys"], warp=ctx.warp)


def _scatter_legend_gradient(a):
    """Describe scatter's continuous color mapping when `c=` is used —
    None otherwise so the legend renderer skips the gradient strip and
    falls through to discrete entries from the categorical color= path."""
    if a["opts"].get("c") is None:
        return None
    legend_opts = a["opts"].get("legend") or {}
    return {
        "kind": "continuous",
        "cmap": a["opts"].get("cmap", _D["default_cmap"]),
        "vmin": a["_vmin"],
        "vmax": a["_vmax"],
        "norm": a["opts"].get("norm", "linear"),
        "center": a["opts"].get("center"),
        "label": legend_opts.get("label"),
        "ticks": legend_opts.get("ticks"),
    }


def _scatter_legend_entries(a):
    opts = a["opts"]
    sw = _LEGSPEC["swatch_width"]
    entries = []
    label = opts.get("label")
    if label:
        def paint(_a, _ctx, x0, y_mid):
            raw_size = opts.get("size", _ctx.defaults["scatter_size"])
            raw_mk = opts.get("marker", "o")
            size_val = (sorted(raw_size)[len(raw_size) // 2]
                        if isinstance(raw_size, (list, tuple)) and raw_size
                        else (raw_size if not isinstance(raw_size, (list, tuple))
                              else _ctx.defaults["scatter_size"]))
            mk_val = (raw_mk[0]
                      if isinstance(raw_mk, (list, tuple)) and raw_mk
                      else (raw_mk if not isinstance(raw_mk, (list, tuple)) else "o"))
            return marker(mk_val, x0 + sw / 2, y_mid, float(size_val), _a["_color"],
                          opts.get("alpha", _ctx.defaults["scatter_alpha"]))
        entries.append({"label": label, "color": a.get("_color"), "paint": paint})
    # Size aesthetic: emit a small grouped guide with representative
    # dots — present only on the record that carries `_size_legend`
    # (attached by `_expand_with_aesthetics`).
    sl = a.get("_size_legend")
    if sl is not None:
        entries.extend(_scatter_size_entries(sl, opts))
    return entries


def _scatter_size_entries(sl, opts):
    """Emit size-graded dot entries showing the size→value mapping.

    Default break selection: ~4 "nice" round values across the source
    range via `_nice_ticks` — mirrors ggplot's `scale_size_continuous`
    using extended-breaks. Users override via
    `size_legend={"breaks": [...], "labels": [...]}` on the scatter call.
    Pixel sizes mirror `_compute_size_array`'s linear interpolation."""
    src_lo, src_hi = sl["source_min"], sl["source_max"]
    s_lo, s_hi = sl["sizes_range"]
    group = sl["col_name"]
    span = src_hi - src_lo

    legend_opts = opts.get("size_legend") or {}
    user_breaks = legend_opts.get("breaks")
    if user_breaks is not None:
        breaks = [float(b) for b in user_breaks]
    else:
        from ..scales import _nice_ticks
        candidates = _nice_ticks(src_lo, src_hi, n=4)
        # Drop ticks outside the source range — those dots wouldn't
        # correspond to any data we'd plot.
        breaks = [b for b in candidates if src_lo <= b <= src_hi]
        if not breaks:
            breaks = [src_lo, src_hi]

    user_labels = legend_opts.get("labels")
    if user_labels is not None:
        if len(user_labels) != len(breaks):
            raise ValueError(
                f"scatter size_legend['labels'] length {len(user_labels)} "
                f"doesn't match breaks length {len(breaks)}."
            )
        labels = [str(l) for l in user_labels]
    else:
        labels = [f"{b:g}" for b in breaks]

    out = []
    for v, label in zip(breaks, labels):
        frac = (v - src_lo) / span if span else 0.5
        radius = s_lo + frac * (s_hi - s_lo)
        marker_kind = opts.get("marker", "o")
        if isinstance(marker_kind, (list, tuple)):
            marker_kind = marker_kind[0] if marker_kind else "o"
        def paint(_a, _ctx, x0, y_mid, _r=radius, _mk=marker_kind):
            sw_ = _LEGSPEC["swatch_width"]
            return marker(_mk, x0 + sw_ / 2, y_mid, _r,
                          _a.get("_color") or _ctx.defaults["color"],
                          opts.get("alpha", _ctx.defaults["scatter_alpha"]))
        out.append({"label": label, "color": "#333", "group": group,
                    "paint": paint})
    return out


add_artist(ArtistSpec(
    name="scatter",
    record=_scatter_record,
    xdomain=_scatter_xdomain,
    ydomain=_scatter_ydomain,
    draw=_scatter_draw,
    legend_entries=_scatter_legend_entries,
    legend_gradient=_scatter_legend_gradient,
    data_attrs=_scatter_data_attrs,
    coord_systems={"Linear", "Circular"},
))
