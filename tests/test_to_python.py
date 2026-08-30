"""`pt.to_python` round-trip: journal → script → exec → same journal.

The generated script is a flattened rebuild of the figure, so the
testable property is the loop: executing it and re-journaling must give
back the journal it was generated from (and therefore the same SVG,
byte-for-byte). Runs across the same PLOTS registries as the journal
and JSON round-trip suites, so every baseline figure is also a codegen
fixture.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

import plotlet as pt
from plotlet import aes
from test_journal_roundtrip import PLOTS


def _rebuild(src: str):
    ns = {}
    exec(compile(src, "<to_python>", "exec"), ns)
    return ns["fig"]


def _canon_json(fig) -> str:
    # Canonical serialized form: sort_keys makes kwarg order (which
    # replay ignores) irrelevant, the NaN token sidesteps `nan != nan`
    # breaking dict equality, and string compare keeps 0 and 0.0 apart
    # where dict `==` would not.
    return json.dumps(json.loads(pt.to_json(fig)), sort_keys=True)


@pytest.mark.parametrize("label,fn", PLOTS, ids=[p[0] for p in PLOTS])
def test_python_roundtrip(label, fn):
    fig = fn()

    try:
        src = pt.to_python(fig)
    except ValueError as e:
        if "diagram leaves" in str(e):
            pytest.skip("diagram leaves have no source form (documented)")
        raise
    regen = _rebuild(src)
    assert _canon_json(regen) == _canon_json(fig), (
        f"{label}: regenerated journal differs"
    )
    assert regen.to_svg() == fig.to_svg(), (
        f"{label}: regenerated SVG differs"
    )


def test_from_json_blob_directly():
    """The agent flow: journal JSON text in, a script out — no live
    figure objects on the input side."""
    df = {"x": [1, 2, 3], "y": [3, 1, 2]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line()
    text = pt.to_json(c)

    src = pt.to_python(text)
    regen = _rebuild(src)
    assert pt.to_json(regen) == text


def test_root_variable_name():
    df = {"x": [1], "y": [1]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_scatter()
    src = pt.to_python(c, var="my_plot")
    ns = {}
    exec(compile(src, "<to_python>", "exec"), ns)
    assert pt.to_json(ns["my_plot"]) == pt.to_json(c)


def test_inherit_aes_false_survives():
    """A layer that opted out of chart aes must not regain it on regen."""
    df = {"x": [1, 2], "y": [3, 4], "g": ["a", "b"]}

    c = pt.chart(df, aes(x="x", y="y", color="g"))
    c.add_line()
    c.add_scatter(aes(x="x", y="y"), inherit_aes=False)

    regen = _rebuild(pt.to_python(c))
    assert _canon_json(regen) == _canon_json(c)
    assert regen.to_svg() == c.to_svg()


def test_inset_fit_roundtrip():
    """fit() rescales host and inset with independent rounding, so the
    inset's dims can't be re-derived from the rect — they must survive
    as explicit kwargs on the generated `host.inset(...)` call."""
    df = {"x": [1, 2, 3], "y": [3, 1, 2]}

    host = pt.chart(df, aes(x="x", y="y"), data_width=47, data_height=47)
    host.add_line()
    ins = host.inset((0.1, 0.1, 0.45, 0.45), data=df,
                     mapping=aes(x="x", y="y"))
    ins.add_scatter()
    fig = host.fit(canvas_width=93)

    regen = _rebuild(pt.to_python(fig))
    assert _canon_json(regen) == _canon_json(fig)
    assert regen.to_svg() == fig.to_svg()


def test_float_margin_not_dropped():
    """A float margin equal to the int default floor is a different
    journal (0.0 vs 0 in JSON) — it must not be dropped as a default."""
    df = {"x": [1, 2], "y": [3, 4]}

    c = pt.chart(df, aes(x="x", y="y"),
                 margin={"top": 0.0, "right": 0.0,
                         "bottom": 0.0, "left": 0.0})
    c.add_line()

    regen = _rebuild(pt.to_python(c))
    assert _canon_json(regen) == _canon_json(c)


def test_numpy_scalar_kwarg():
    """numpy scalar styling kwargs must emit as plain literals — the
    generated script does not import numpy."""
    df = {"x": [1, 2], "y": [3, 4]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line(linewidth=np.float64(2.5))

    src = pt.to_python(c)
    assert "np." not in src
    regen = _rebuild(src)
    assert _canon_json(regen) == _canon_json(c)
    assert regen.to_svg() == c.to_svg()


def test_facet_call_defaults_survive():
    """FacetGrid records calls verbatim — kwargs equal to a Layout
    method default must not be dropped from the generated script."""
    df = {"t": [1, 2, 3, 4], "v": [5, 6, 4, 7], "grp": ["p", "p", "q", "q"]}

    fg = pt.facet(df, by="grp")
    fg.add_line(aes(x="t", y="v"))
    fg.sectors(pt.Sectors(("a", "b"), lengths=(2.0, 2.0)),
               axis="x", divider=True)

    regen = _rebuild(pt.to_python(fg))
    assert _canon_json(regen) == _canon_json(fg)


def test_var_collision_with_minted_names():
    """var= may collide with a minted data-table name; the allocator
    must steer around it instead of silently rebinding."""
    df = {"x": [1, 2], "y": [3, 4]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line()

    src = pt.to_python(c, var="d1")
    ns = {}
    exec(compile(src, "<to_python>", "exec"), ns)
    assert pt.to_json(ns["d1"]) == pt.to_json(c)


def test_var_must_be_identifier():
    df = {"x": [1], "y": [1]}

    c = pt.chart(df, aes(x="x", y="y"))
    with pytest.raises(ValueError, match="variable name"):
        pt.to_python(c, var="my-fig")


def test_non_identifier_data_id():
    """Agent-authored journal blobs may use data ids that aren't Python
    names — the generated script must still compile and round-trip."""
    df = {"x": [1, 2], "y": [3, 4]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line()
    blob = pt.to_json(c).replace('"d1"', '"my-table"')

    regen = _rebuild(pt.to_python(blob))
    assert regen.to_svg() == c.to_svg()


def test_diagram_leaf_raises():
    df = {"x": [1], "y": [1]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_scatter()
    diagram = pt.layout_diagram(c)
    with pytest.raises(ValueError, match="diagram"):
        pt.to_python(diagram)
