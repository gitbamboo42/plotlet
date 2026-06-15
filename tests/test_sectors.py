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
        {"pathwayA": ["g1", "g2", "g3"],
         "pathwayB": ["g4", "g5"],
         "pathwayC": ["g6", "g7", "g8", "g9"]},
        axis="x", divider=False,
    )
    c.bar(
        data={"gene": ["g1","g2","g3","g4","g5","g6","g7","g8","g9"],
              "v":    [3,    5,    2,    8,    6,    4,    7,    5,    3]},
        x="gene", y="v",
    )
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
    c.heatmap(
        [[0.1, 0.2, 0.3, 0.4],
         [0.5, 0.6, 0.7, 0.8],
         [0.2, 0.4, 0.6, 0.8],
         [0.9, 0.1, 0.2, 0.3],
         [0.5, 0.5, 0.5, 0.5]],
        yticklabels=["g1", "g2", "g3", "g4", "g5"],
        xticklabels=["c1", "c2", "c3", "c4"],
    )
    return c


# ---------------------------------------------------------------------------
# Data-model tests for the categorical kind.
# ---------------------------------------------------------------------------

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
    "continuous_y":        sectors_continuous_y,
    "categorical_y_heatmap": sectors_categorical_y_heatmap,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_sectors_baseline(name, fn, baseline_compare):
    baseline_compare("sectors", name, fn().to_svg())
