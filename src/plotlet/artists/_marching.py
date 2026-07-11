"""Marching-squares helpers shared by `contour` and `kde_2d`.

Both artists draw iso-lines and filled level regions on a regular 2-D
scalar grid; the grid geometry lives here so the two stay in lockstep.
Coordinates are grid-index space `(col, row)` — the caller maps them to
data space via its own extent.

Line cases: `MS_CASES[code]` lists `(edge, edge)` pairs to connect for a
cell's 4-bit inside-corner code (bit0=TL, bit1=TR, bit2=BR, bit3=BL,
"inside" = value >= level). The saddle cases (5, 10) use the fixed
topology that keeps the two inside corners disconnected; the filled-region
triangles below match it.
"""
from ..draw import colormap, ContinuousNorm
from ..draw import coord, path as draw_path

MS_CASES = {
    0: [], 15: [],
    1: [(0, 3)], 14: [(0, 3)],
    2: [(0, 1)], 13: [(0, 1)],
    3: [(1, 3)], 12: [(1, 3)],
    4: [(1, 2)], 11: [(1, 2)],
    5: [(0, 3), (1, 2)], 10: [(0, 1), (2, 3)],
    6: [(0, 2)], 9: [(0, 2)],
    7: [(2, 3)], 8: [(2, 3)],
}


def edge_pt(edge, r, c, vtl, vtr, vbr, vbl, lvl):
    """Linear-interpolated level crossing on one cell edge, in grid-index
    space. Edges: 0=top, 1=right, 2=bottom, 3=left."""
    if edge == 0:
        t = (lvl - vtl) / (vtr - vtl) if vtr != vtl else 0.5
        return (c + t, r)
    if edge == 1:
        t = (lvl - vtr) / (vbr - vtr) if vbr != vtr else 0.5
        return (c + 1, r + t)
    if edge == 2:
        t = (lvl - vbl) / (vbr - vbl) if vbr != vbl else 0.5
        return (c + t, r + 1)
    t = (lvl - vtl) / (vbl - vtl) if vbl != vtl else 0.5
    return (c, r + t)


def cell_has_nan(vtl, vtr, vbr, vbl):
    """True if any corner is NaN. Masked cells skip whole (matplotlib's
    corner_mask=False): a crossing interpolated against a NaN corner has
    no defined position, and one NaN coordinate makes browsers drop the
    entire <path>."""
    return vtl != vtl or vtr != vtr or vbr != vbr or vbl != vbl


def _partial_cell_polys(r, c, vtl, vtr, vbr, vbl, lvl):
    """Polygon(s) covering the `value >= lvl` part of one boundary cell.

    Walks the cell border TL → TR → BR → BL, keeping inside corners and
    inserting the edge crossing wherever the inside flag flips. Saddle
    cells (two opposite inside corners) emit two triangles matching the
    disconnected MS_CASES line topology instead of one hexagon that would
    bridge them."""
    ins = (vtl >= lvl, vtr >= lvl, vbr >= lvl, vbl >= lvl)
    code = ins[0] | (ins[1] << 1) | (ins[2] << 2) | (ins[3] << 3)
    ep = lambda e: edge_pt(e, r, c, vtl, vtr, vbr, vbl, lvl)
    if code == 5:    # TL and BR inside, disconnected
        return [[(c, r), ep(0), ep(3)], [ep(1), (c + 1, r + 1), ep(2)]]
    if code == 10:   # TR and BL inside, disconnected
        return [[ep(0), (c + 1, r), ep(1)], [ep(2), (c, r + 1), ep(3)]]
    corners = ((c, r), (c + 1, r), (c + 1, r + 1), (c, r + 1))
    pts = []
    for i in range(4):
        if ins[i]:
            pts.append(corners[i])
        if ins[i] != ins[(i + 1) % 4]:
            pts.append(ep(i))
    return [pts] if len(pts) >= 3 else []


def filled_level_polys(grid, lvl, nrows, ncols):
    """Polygons covering the `value >= lvl` region of the grid, in
    grid-index space. Interior runs of fully-inside cells merge into one
    rectangle per row so the output stays compact; boundary cells emit
    their partial polygons. Cells with a NaN corner are masked — skipped
    whole, leaving a hole in the region (see `cell_has_nan`)."""
    polys = []
    for r in range(nrows - 1):
        run_start = None
        for c in range(ncols - 1):
            vtl = grid[r][c]; vtr = grid[r][c + 1]
            vbr = grid[r + 1][c + 1]; vbl = grid[r + 1][c]
            if cell_has_nan(vtl, vtr, vbr, vbl):
                if run_start is not None:
                    polys.append([(run_start, r), (c, r),
                                  (c, r + 1), (run_start, r + 1)])
                    run_start = None
                continue
            if vtl >= lvl and vtr >= lvl and vbr >= lvl and vbl >= lvl:
                if run_start is None:
                    run_start = c
                continue
            if run_start is not None:
                polys.append([(run_start, r), (c, r),
                              (c, r + 1), (run_start, r + 1)])
                run_start = None
            polys.extend(_partial_cell_polys(r, c, vtl, vtr, vbr, vbl, lvl))
        if run_start is not None:
            polys.append([(run_start, r), (ncols - 1, r),
                          (ncols - 1, r + 1), (run_start, r + 1)])
    return polys


def filled_levels_svg(grid, nrows, ncols, levels, *, cmap_name, color,
                      alpha, x0d, y0d, dxd, dyd, x_scale, y_scale):
    """Painter's-algorithm filled contours: one `<path>` per level, drawn
    lowest level first, each filling the whole `value >= level` region so
    higher levels paint over lower ones. Grid-index coords map to data
    space via the affine `(x0d + col*dxd, y0d + row*dyd)`, then through
    the scales. With `cmap_name` the level picks the fill color (norm over
    the level span, matching iso-line coloring); otherwise the constant
    `color` relies on `alpha` stacking to shade toward the peak."""
    if not levels:
        return ""
    lv = sorted(levels)
    if cmap_name:
        cm = colormap(cmap_name)
        norm = ContinuousNorm(lv[0], lv[-1], "linear")
    out = []
    for lvl in lv:
        if cmap_name:
            r, g, b = cm(norm.to_unit(lvl))
            col = f"rgb({r},{g},{b})"
        else:
            col = color
        segs = []
        for poly in filled_level_polys(grid, lvl, nrows, ncols):
            pts = [f"{coord(x_scale(x0d + gx * dxd))},"
                   f"{coord(y_scale(y0d + gy * dyd))}" for gx, gy in poly]
            segs.append("M" + " L".join(pts) + " Z")
        if segs:
            out.append(draw_path("".join(segs), fill=col, fill_alpha=alpha))
    return "".join(out)
