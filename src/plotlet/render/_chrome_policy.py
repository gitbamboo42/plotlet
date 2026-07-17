"""Chrome visibility policy — decided per-panel "draw it?" flags.

`resolve_axis_chrome` combines the replayed chart state with the layout
pre-pass flags (share-pair side hiding, tick-label suppression) into
plain booleans. It is the ONE place such combinations live:

- `_resolution._resolve_panel_inputs` calls it and puts the result on the
  panel inputs (`inp.chrome`), so the margin reservation
  (`_chrome.chrome_stack_extents` / `label_band_sizes`) and the emit
  pass (`_chrome.emit_chrome`) read identical decisions;
- `resolved_ir._chart_to_ir` projects the same result into
  `IRPanel.chrome["visibility"]`, so the resolved IR shows what will
  be drawn, not just the raw ingredients.

Emitters must not re-derive these combinations: when a new "draw X?"
rule mixes more than one state / layout field, add the decided flag
here instead of gating at the emit site.
"""

_SIDES = ("top", "bottom", "left", "right")


def resolve_axis_chrome(st, po=None):
    """Decide chrome visibility for one data panel.

    `st` is the replayed chart state; `po` is the panel's layout
    pre-pass `_PanelOpts` (or `None` for a panel outside any layout
    pass, e.g. a circular ring) — its `hide_*` flags mark sides joined
    to a share-pair neighbor, its `suppress_*_labels` flags mark sides
    whose tick labels a sharing sibling already renders.

    Returns::

        {"spines": {side: bool, ..., "walls": bool},
         "x": {"side", "hidden", "draw_marks", "outward_mark",
               "draw_labels", "draw_axis_label",
               "draw_sector_dividers", "draw_sector_labels"},
         "y": {same keys}}

    Per axis: `side` is where the axis band sits (`x_side` / `y_side`
    state), `hidden` whether that side is share-joined, `draw_marks`
    whether tick marks are drawn (user `marks=` AND the side is not
    joined — marks bleeding into the inter-panel gap read as clutter),
    `outward_mark` whether a drawn mark extends outside the data area
    (drives the tick-band margin and the label offset), `draw_labels`
    whether tick labels are drawn, `draw_axis_label` whether the
    xlabel/ylabel text is drawn (set AND the side is not share-joined;
    the title has no such flag — it renders even on a joined edge,
    it's the panel's identity). Spine visibility is deliberately
    NOT an input to any tick flag — hiding a spine leaves the ticks
    (matplotlib semantics).

    Sector chrome: `draw_sector_dividers` is the sector walls toggle
    (`Sectors.divider` AND `c.spines(walls=)`; on x additionally no
    artist with `crosses_sectors` — walls cutting through cross-sector
    curves read as a layering bug). `draw_sector_labels` follows tick
    labels: sector names drop wherever tick labels are suppressed or
    the side is share-joined.
    """
    from ..registry import get_artist

    if po is None:
        hide = suppress = {side: False for side in _SIDES}
    else:
        hide = {side: getattr(po, f"hide_{side}") for side in _SIDES}
        suppress = {side: getattr(po, f"suppress_{side}_labels")
                    for side in _SIDES}

    # Artists that span sectors (chord_links, ribbons) suppress the
    # x-axis walls. y-sector walls have no crossing artists today.
    x_crossers = any(
        (spec := get_artist(a["type"])) is not None and spec.crosses_sectors
        for a in st["artists"]
    )

    spines = {side: st[f"spine_{side}"] for side in _SIDES}
    spines["walls"] = st["spine_walls"]

    def _axis(axis):
        side = st[f"{axis}_side"]
        hidden = hide[side]
        draw_marks = st[f"{axis}_marks"] and not hidden
        draw_labels = st[f"{axis}_show_labels"] and not suppress[side]
        sec = st[f"{axis}_sectors"]
        return {
            "side": side,
            "hidden": hidden,
            "draw_marks": draw_marks,
            "outward_mark": draw_marks and st[f"{axis}_direction"] != "in",
            "draw_labels": draw_labels,
            "draw_axis_label": bool(st[f"{axis}label"]) and not hidden,
            "draw_sector_dividers": (sec is not None and bool(sec.divider)
                                     and spines["walls"]
                                     and not (axis == "x" and x_crossers)),
            "draw_sector_labels": (sec is not None and bool(sec.label)
                                   and draw_labels and not hidden),
        }

    return {"spines": spines, "x": _axis("x"), "y": _axis("y")}
