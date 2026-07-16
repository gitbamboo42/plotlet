"""Chrome visibility policy — decided per-panel "draw it?" flags.

`resolve_axis_chrome` combines the replayed chart state with the layout
pre-pass flags (share-pair side hiding, tick-label suppression) into
plain booleans. It is the ONE place such combinations live:

- `core._resolve_panel_inputs` calls it and puts the result on the
  panel inputs (`inp.chrome`), so the margin reservation
  (`_chrome.chrome_stack_extents` / `label_band_sizes`) and the emit
  pass (`_chrome.emit_chrome`) read identical decisions;
- `resolved._chart_to_ir` projects the same result into
  `IRPanel.chrome["visibility"]`, so the resolved IR shows what will
  be drawn, not just the raw ingredients.

Emitters must not re-derive these combinations: when a new "draw X?"
rule mixes more than one state / layout field, add the decided flag
here instead of gating at the emit site.
"""

_SIDES = ("top", "bottom", "left", "right")


def resolve_axis_chrome(st, hide, suppress):
    """Decide chrome visibility for one data panel.

    `st` is the replayed chart state; `hide` and `suppress` are
    per-side bool dicts (keys `top/bottom/left/right`) from the layout
    pre-pass — `hide` marks sides joined to a share-pair neighbor,
    `suppress` marks sides whose tick labels a sharing sibling already
    renders.

    Returns::

        {"spines": {side: bool, ..., "walls": bool},
         "x": {"side", "hidden", "draw_marks", "outward_mark",
               "draw_labels"},
         "y": {same keys}}

    Per axis: `side` is where the axis band sits (`x_side` / `y_side`
    state), `hidden` whether that side is share-joined, `draw_marks`
    whether tick marks are drawn (user `marks=` AND the side is not
    joined — marks bleeding into the inter-panel gap read as clutter),
    `outward_mark` whether a drawn mark extends outside the data area
    (drives the tick-band margin and the label offset), `draw_labels`
    whether tick labels are drawn. Spine visibility is deliberately
    NOT an input to any tick flag — hiding a spine leaves the ticks
    (matplotlib semantics).
    """
    def _axis(axis):
        side = st[f"{axis}_side"]
        hidden = hide[side]
        draw_marks = st[f"{axis}_marks"] and not hidden
        return {
            "side": side,
            "hidden": hidden,
            "draw_marks": draw_marks,
            "outward_mark": draw_marks and st[f"{axis}_direction"] != "in",
            "draw_labels": st[f"{axis}_show_labels"] and not suppress[side],
        }

    spines = {side: st[f"spine_{side}"] for side in _SIDES}
    spines["walls"] = st["spine_walls"]
    return {"spines": spines, "x": _axis("x"), "y": _axis("y")}
