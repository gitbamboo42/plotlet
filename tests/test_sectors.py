"""Baseline tests for ``c.sectors(...)`` — named, length-weighted
partitions of the x-axis.

Covers:

  - single-panel sectored scatter (dict input)
  - multi-track stack with layout-level ``sectors()`` sugar
  - silent passthrough when an artist's data lacks the sector column
    (cross-sector reflines should not error out)
"""
from __future__ import annotations

import pytest

import plotlet as pt
from plotlet import Sectors


PHASES = {"warmup": 100, "training": 500, "cooldown": 200}


def sectors_single_scatter():
    c = pt.chart(title="scatter — three phases",
                 data_width=480, data_height=180,
                 ylim=(0.0, 1.0))
    c.sectors(PHASES, column="phase")
    c.scatter(
        data={
            "phase": ["warmup", "warmup", "training", "training",
                      "cooldown", "cooldown"],
            "t":     [40, 90, 100, 400, 50, 150],
            "v":     [0.4, 0.8, 0.3, 0.9, 0.5, 0.7],
        },
        x="t", y="v", size=8,
    )
    return c


def sectors_multi_track_share_x():
    t1 = pt.chart(data_width=480, data_height=80,
                  ylabel="scatter", ylim=(0.0, 1.0))
    t1.scatter(
        data={
            "phase": ["warmup", "warmup", "training", "training", "cooldown"],
            "t":     [40, 90, 100, 400, 80],
            "v":     [0.4, 0.7, 0.3, 0.9, 0.5],
        },
        x="t", y="v", size=8,
    )

    t2 = pt.chart(data_width=480, data_height=80,
                  ylabel="line", ylim=(0.0, 1.0))
    t2.line(
        data={
            "phase": ["warmup", "warmup", "training", "training",
                      "cooldown", "cooldown"],
            "t":     [10, 95, 10, 480, 10, 180],
            "v":     [0.3, 0.6, 0.5, 0.8, 0.2, 0.7],
        },
        x="t", y="v", group="phase",
    )
    # Cross-sector reference line — no sector column on its data, so
    # the sector remap must silently pass through.
    t2.axhline(0.5, color="#888888", linestyle="--")

    return (pt.grid([[t1], [t2]])
              .share_x("col")
              .sectors(PHASES, column="phase"))


def sectors_from_sectors_value():
    # Pre-built Sectors value, passed verbatim — exercises the
    # ``isinstance(spec, cls)`` short-circuit in Sectors.coerce.
    sec = Sectors(names=("a", "b", "c"),
                  lengths=(10.0, 20.0, 5.0))
    c = pt.chart(title="prebuilt Sectors",
                 data_width=380, data_height=140,
                 ylim=(0.0, 1.0))
    c.sectors(sec, column="grp")
    c.line(
        data={
            "grp": ["a", "a", "b", "b", "c", "c"],
            "x":   [0, 9, 0, 19, 0, 4],
            "y":   [0.2, 0.9, 0.4, 0.6, 0.3, 0.8],
        },
        x="x", y="y", group="grp",
    )
    return c


def sectors_categorical_x():
    # Categorical x-sectors: label-only — the category-scale gap is the
    # visual separator, so a divider line on top would read as clutter.
    c = pt.chart(title="categorical x-sectors",
                 data_width=440, data_height=200,
                 ylabel="value")
    c.sectors(
        {"groupA": ["c1", "c2", "c3"],
         "groupB": ["c4", "c5"],
         "groupC": ["c6", "c7", "c8", "c9"]},
        axis="x", divider=False,
    )
    c.bar(
        data={"cat": ["c1","c2","c3","c4","c5","c6","c7","c8","c9"],
              "v":   [3,    5,    2,    8,    6,    4,    7,    5,    3]},
        x="cat", y="v",
    )
    return c


def sectors_continuous_x():
    # Continuous x-sectors with user-explicit ticks: tick mark + tick label
    # + sector label all coexist on the bottom (the parallel of
    # categorical_x). Tick positions are per-sector LOCAL — they replicate
    # across every sector at sector.offset(name) + tick.
    c = pt.chart(title="continuous x-sectors with ticks",
                 data_width=440, data_height=180, ylabel="value")
    c.sectors({"A": 100, "B": 60, "C": 80}, column="region", gap=12)
    c.scatter(
        data={"region": ["A",  "A",  "B",  "B",  "C",  "C"],
              "pos":    [30,   80,   20,   50,   10,   60],
              "v":      [3,    5,    8,    6,    4,    7]},
        x="pos", y="v",
    )
    c.xticks([0, 50, 100], rotation=90)
    return c


def sectors_continuous_y():
    # Continuous y-sectors — partition the y-axis by named band.
    c = pt.chart(title="continuous y-sectors",
                 data_width=220, data_height=320,
                 xlabel="value")
    c.sectors({"low": 10, "mid": 20, "high": 15},
              column="band", axis="y")
    c.scatter(
        data={"band": ["low","low","mid","mid","mid","high","high"],
              "val":  [2,    7,    5,    12,   18,   3,     10],
              "v":    [0.2,  0.5,  0.3,  0.7,  0.4,  0.6,   0.8]},
        x="v", y="val", size=8,
    )
    return c


def sectors_categorical_y_heatmap():
    # Categorical y-sectors on a heatmap: label-only — the gap is the
    # separator. Annotated-heatmap row clusters with visible labels.
    c = pt.chart(title="annotated-heatmap row clusters",
                 data_width=320, data_height=260)
    c.sectors({"pwA": ["g1", "g2", "g3"], "pwB": ["g4", "g5"]},
              axis="y", divider=False)
    rows = ["g1", "g2", "g3", "g4", "g5"]
    matrix = [[0.1, 0.2, 0.3, 0.4],
              [0.5, 0.6, 0.7, 0.8],
              [0.2, 0.4, 0.6, 0.8],
              [0.9, 0.1, 0.2, 0.3],
              [0.5, 0.5, 0.5, 0.5]]
    df = {"col": ["c1", "c2", "c3", "c4"]}
    for name, values in zip(rows, matrix):
        df[name] = values
    c.heatmap(data=df, x="col", values=rows)
    return c


# ---------------------------------------------------------------------------
# Data-model tests for the categorical kind.
# ---------------------------------------------------------------------------

def test_sector_labels_follow_axis_side():
    # Sector labels flip to whichever edge the tick band uses. They used
    # to hardcode left/bottom: with yticks(side="right") the margin was
    # reserved on the right but the labels drew at negative x, off-canvas.
    def make(tick_side):
        c = pt.chart({"cat": ["a", "b", "c", "d"], "v": [1, 2, 3, 4]},
                     data_width=280, data_height=160)
        c.bar(x="cat", y="v")
        c.sectors({"g1": ["a", "b"], "g2": ["c", "d"]}, axis="x")
        c.xticks(side=tick_side)
        c.yticks(side="right" if tick_side == "top" else "left")
        c.sectors({"lo": 1, "hi": 1}, column="band", axis="y")
        return c

    for tick_side in ("bottom", "top"):
        regs = make(tick_side).regions()
        panel = next(r for r in regs if r["name"] == "panel")
        px, py, pw, ph = panel["bbox"]
        secs = [r for r in regs if r["name"] == "sector-label"]
        assert secs, "sector labels missing"
        for r in secs:
            x, y, w, h = r["bbox"]
            assert x >= 0 and y >= 0, "sector label off-canvas"
            if r["meta"].get("text") in ("g1", "g2"):   # x-axis sectors
                ok = y >= py + ph if tick_side == "bottom" else y + h <= py
            else:                                        # y-axis sectors
                ok = x + w <= px if tick_side == "bottom" else x >= px + pw
            assert ok, (tick_side, r["meta"].get("text"), r["bbox"])


def test_sectors_categorical_basic():
    s = Sectors.coerce(
        {"groupA": ["c1", "c2"], "groupB": ["c3", "c4", "c5"]},
        divider=False, label=False,
    )
    assert s.kind == "categorical"
    assert s.cats() == ("c1", "c2", "c3", "c4", "c5")
    assert s.split_indices() == [2]
    assert s.cat_to_group() == {"c1": "groupA", "c2": "groupA",
                                "c3": "groupB", "c4": "groupB", "c5": "groupB"}
    assert s.total() == 5
    assert s.offset("groupB") == 2
    assert s.divider is False
    assert s.label is False


def test_sectors_categorical_rejects_duplicate_cats():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        Sectors.coerce({"A": ["x", "y"], "B": ["y", "z"]})  # 'y' twice


def test_sectors_categorical_rejects_empty_sector():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        Sectors.coerce({"A": ["x"], "B": []})


def test_sectors_rejects_both_lengths_and_members():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        Sectors(names=("a",), lengths=(1.0,), members=(("x",),))


def test_sectors_categorical_center_and_boundaries():
    s = Sectors.coerce({"A": ["c1", "c2"], "B": ["c3"], "C": ["c4", "c5", "c6"]})
    # center returns midpoint band index for categorical
    assert s.center("A") == 0.5      # cats 0,1 → midpoint 0.5
    assert s.center("B") == 2.0      # cat 2
    assert s.center("C") == 4.0      # cats 3,4,5 → midpoint 4.0
    assert s.boundaries() == [0.0, 2.0, 3.0, 6.0]
    assert s.split_indices() == [2, 3]


def test_sectors_axis_kwarg_validation():
    import pytest as _pytest
    c = pt.chart(data_width=200, data_height=80)
    c.sectors({"a": ["x"], "b": ["y"]}, axis="diagonal")  # invalid axis
    with _pytest.raises(ValueError, match="axis"):
        c.to_svg()


def test_sectors_typo_in_data_raises_clearly():
    """A row tagged with a sector name that doesn't exist in the Sectors
    declaration is a typo — silent passthrough would corrupt the global
    offset and produce a wrong-but-plausible plot. Must raise."""
    import pytest as _pytest
    c = pt.chart(data_width=200, data_height=80)
    c.sectors({"warmup": 100, "training": 500}, column="phase")
    c.scatter(
        data={"phase": ["warmup", "tarining", "warmup"],  # ← typo
              "t":     [10, 20, 30],
              "v":     [0.5, 0.5, 0.5]},
        x="t", y="v",
    )
    with _pytest.raises(ValueError, match="tarining"):
        c.to_svg()


def test_sectors_after_artist_still_remaps():
    """Regression: `c.coordinate(...).sectors(...)` chained after an artist
    on a plain Chart used to silently no-op the sector remap — every row's
    data stacked in the first sector. `Chart.coordinate()` returns self
    (not a `Layout`), so the trailing `.sectors()` lands at the end of
    `_calls` after any prior artist. `_replay`'s sectors-to-front pass
    enforces the sectors-before-artists invariant independent of
    recording order; this test pins that behavior."""
    from plotlet.render._resolution import _replay
    c = pt.chart(data_width=200, data_height=80, ylim=(0, 1))
    c.scatter(
        data={"grp": ["g1", "g2"], "x": [25, 25], "y": [0.5, 0.5]},
        x="x", y="y",
    )
    c.coordinate(pt.CircularCoordinate()).sectors(
        {"g1": 100, "g2": 100}, column="grp",
    )
    state = _replay(c._calls)
    assert state["x_sectors"] is not None, "sectors recorded after artist must reach replay state"
    # Both rows tagged grp=g1/g2 with the same local x=25. After remap,
    # g2's x must be offset to 25 + 100 = 125 (g1's offset is 0).
    [artist] = state["artists"]
    assert artist["xs"] == [25.0, 125.0], (
        f"sector remap must offset g2's x by g1's length; got xs={artist['xs']!r}"
    )


def test_layout_sectors_cascade_no_leaf_mutation():
    """Regression: `Layout.sectors(...)` no longer fans out via insert(0)
    into each leaf's `_calls`. Instead the entry stays on the Layout's
    own journal and `_resolve_panels` prepends it via parent-chain
    cascade. This test pins that the leaf's journal is not touched, so
    a Layout-level sectors call composes cleanly with re-renders /
    fit() / regions() without leaking entries between calls."""
    t1 = pt.chart(data_width=200, data_height=60)
    t1.line(data={"phase": ["warmup"], "t": [50], "v": [0.5]}, x="t", y="v")
    t2 = pt.chart(data_width=200, data_height=60)
    t2.line(data={"phase": ["training"], "t": [50], "v": [0.5]}, x="t", y="v")
    snapshot_t1 = list(t1._calls)
    snapshot_t2 = list(t2._calls)
    layout = (t1 / t2).sectors(PHASES, column="phase")
    # After Layout.sectors, leaf journals should be unchanged.
    assert t1._calls == snapshot_t1, "Layout.sectors must not mutate leaf _calls"
    assert t2._calls == snapshot_t2, "Layout.sectors must not mutate leaf _calls"
    # Sector partition still reaches the leaves at render via cascade.
    layout.to_svg()
    # And re-renders don't accumulate anything on the leaves either.
    layout.to_svg()
    assert t1._calls == snapshot_t1, "re-render must not mutate leaf _calls"
    assert t2._calls == snapshot_t2, "re-render must not mutate leaf _calls"


def test_sectors_passthrough_when_column_absent():
    """Cross-sector reference lines (data without the sector column) must
    silently pass through — they're an intentional shape."""
    c = pt.chart(data_width=200, data_height=80, ylim=(0, 1))
    c.sectors({"warmup": 100, "training": 500}, column="phase")
    c.scatter(
        data={"phase": ["warmup", "training"],
              "t":     [50, 300],
              "v":     [0.4, 0.7]},
        x="t", y="v",
    )
    # No 'phase' column on axhline data → no remap, no error.
    c.axhline(0.5, color="#888888")
    c.to_svg()  # smoke


# ---------------------------------------------------------------------------
# Pure data-model tests — no rendering.
# ---------------------------------------------------------------------------

def test_sectors_offsets_and_total():
    s = Sectors.coerce({"a": 10, "b": 5, "c": 7}, name_col="grp")
    assert s.offset("a") == 0
    assert s.offset("b") == 10
    assert s.offset("c") == 15
    assert s.total() == 22
    assert s.center("b") == 12.5
    assert s.boundaries() == [0.0, 10.0, 15.0, 22.0]


def test_sectors_unknown_name_raises():
    s = Sectors.coerce({"a": 10, "b": 5}, name_col="grp")
    with pytest.raises(KeyError):
        s.offset("missing")


def test_sectors_rejects_duplicates_and_nonpositive():
    with pytest.raises(ValueError):
        Sectors(names=("a", "a"), lengths=(1.0, 1.0))
    with pytest.raises(ValueError):
        Sectors(names=("a", "b"), lengths=(1.0, 0.0))


def test_sectors_requires_column_kwarg():
    c = pt.chart(data_width=200, data_height=80)
    c.sectors({"a": 1, "b": 2}, column="grp")  # ok
    c.line(data={"grp": ["a", "b"], "x": [0, 0], "y": [1, 2]},
           x="x", y="y", group="grp")
    c.to_svg()  # smoke

    c2 = pt.chart(data_width=200, data_height=80)
    c2.sectors({"a": 1, "b": 2})  # missing column=
    with pytest.raises(TypeError, match="column"):
        c2.to_svg()


# ---------------------------------------------------------------------------
# Baseline-image tests.
# ---------------------------------------------------------------------------

PLOTS = {
    "single_scatter":      sectors_single_scatter,
    "multi_track_share_x": sectors_multi_track_share_x,
    "from_sectors_value":  sectors_from_sectors_value,
    "categorical_x":       sectors_categorical_x,
    "continuous_x":        sectors_continuous_x,
    "continuous_y":        sectors_continuous_y,
    "categorical_y_heatmap": sectors_categorical_y_heatmap,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_sectors_baseline(name, fn, baseline_compare):
    baseline_compare("sectors", name, fn().to_svg())
