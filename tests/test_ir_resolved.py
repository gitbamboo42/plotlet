"""Resolved-IR sanity: for every baseline plot, `resolve_ir` must:

  * run without error
  * produce a JSON-safe projection (envelopes only via `_json_layer`)
  * be deterministic (same figure built twice → equal resolved IR)
  * emit valid IRScale kinds and populated IRArtist kinds

The resolved IR is the second stage of the render pipeline:
`render.render_svg` is `resolve_ir(ir).to_svg()`, so the projection
under `.root` and the rendered SVG are two views of one resolution.
The staged-pipeline pins at the bottom hold that property in place.
The byte-identical round-trip proof lives with the journal / figure-IR
suites (`test_journal_roundtrip.py`, `test_ir.py`) — the resolved IR
itself is one-way.
"""
from __future__ import annotations

import json
import math

import pytest

import plotlet as pt
from plotlet import resolve_ir
from plotlet.render.resolved import (
    IRArtist,
    IRCoord,
    IRLayout,
    IRPanel,
    IRScale,
    ResolvedIR,
)
from test_journal_roundtrip import PLOTS


_VALID_SCALE_KINDS = {"linear", "log", "category", "symlog", "power",
                      "sqrt", "time"}


def _walk_panels(ir):
    """Yield every IRPanel (data or non-data) in the resolved projection."""
    if isinstance(ir, IRPanel):
        yield ir
        for side in ("left", "right", "top", "bottom"):
            for a in ir.attachments.get(side, ()):
                yield from _walk_panels(a)
        for _rect, inset in ir.insets:
            yield from _walk_panels(inset)
    elif isinstance(ir, IRLayout):
        for c in ir.children:
            if c is not None:
                yield from _walk_panels(c)


@pytest.mark.parametrize("label,fn", PLOTS, ids=[p[0] for p in PLOTS])
def test_resolve_ir_structural(label, fn):
    fig = fn()
    rir = resolve_ir(fig)

    assert isinstance(rir, ResolvedIR)
    ir = rir.root
    assert isinstance(ir, (IRPanel, IRLayout)), \
        f"projection root must be a panel or layout, got {type(ir).__name__}"

    for panel in _walk_panels(ir):
        assert panel.leaf_kind in ("data", "legend", "diagram"), \
            f"unknown leaf_kind {panel.leaf_kind!r}"
        if panel.leaf_kind != "data":
            continue
        for axis, sc in panel.scales.items():
            assert axis in ("x", "y")
            assert isinstance(sc, IRScale)
            assert sc.kind in _VALID_SCALE_KINDS, \
                f"scale.kind {sc.kind!r} not in {_VALID_SCALE_KINDS}"
            if sc.kind == "category":
                assert sc.cats is not None, "category scale needs cats"
        for artist in panel.artists:
            assert isinstance(artist, IRArtist)
            assert isinstance(artist.kind, str) and artist.kind != "unknown"
        # Decided chrome visibility rides on every data panel — the
        # same flags the emit pass reads (see render/_chrome_policy.py).
        vis = panel.chrome["visibility"]
        assert set(vis["spines"]) == {"top", "bottom", "left", "right",
                                      "walls"}
        for axis in ("x", "y"):
            assert set(vis[axis]) == {"side", "hidden", "draw_marks",
                                      "outward_mark", "draw_labels",
                                      "draw_axis_label",
                                      "draw_sector_dividers",
                                      "draw_sector_labels"}
            assert all(isinstance(vis[axis][k], bool)
                       for k in ("hidden", "draw_marks", "outward_mark",
                                 "draw_labels", "draw_axis_label",
                                 "draw_sector_dividers",
                                 "draw_sector_labels"))


def _nan_eq(a, b):
    """Recursive equality that treats NaN == NaN (data-carrying fixtures
    like heatmap_nan legitimately contain NaN)."""
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return True
        return a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_nan_eq(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_nan_eq(x, y) for x, y in zip(a, b))
    if hasattr(a, "__dataclass_fields__"):
        return all(_nan_eq(getattr(a, k), getattr(b, k))
                   for k in a.__dataclass_fields__)
    return a == b


@pytest.mark.parametrize("label,fn", PLOTS, ids=[p[0] for p in PLOTS])
def test_resolve_ir_deterministic(label, fn):
    ir1 = resolve_ir(fn())
    ir2 = resolve_ir(fn())
    assert _nan_eq(ir1.root, ir2.root), \
        "resolved IR should be identical across two builds"


@pytest.mark.parametrize("label,fn", PLOTS, ids=[p[0] for p in PLOTS])
def test_resolve_ir_json_safe(label, fn):
    """`to_dict()` — the read-only JSON debug view — dumps cleanly for
    every baseline figure. Enveloping walks the whole tree, so a
    non-JSON-safe leaf value raises somewhere; then json.dumps must not
    fail either."""
    d = resolve_ir(fn()).to_dict()
    json.dumps(d)
    assert set(d) == {"root"}


def test_figure_ir_resolve_method():
    """`FigureIR.resolve()` and `pt.resolve_ir(fig)` agree."""
    data = {"x": [1, 2, 3], "y": [2.0, 3.1, 4.5]}
    c = pt.chart(data_width=200, data_height=140, title="t")
    c.scatter(data=data, x="x", y="y")
    via_method = pt.to_ir(c).resolve()
    via_fn = pt.resolve_ir(c)
    assert _nan_eq(via_method.root, via_fn.root)
    # a lone chart resolves through its 1×1 layout wrapper; the panel
    # title lives on the leaf
    assert isinstance(via_method.root, IRLayout)
    (panel,) = via_method.root.children
    assert panel.chrome.get("title") == "t"


def test_layout_title_projected():
    """A layout's figure-title band is visible in the resolved IR —
    `IRLayout.title`, last call wins, `None` when untitled."""
    def pair():
        a = pt.chart({"x": [1.0, 2.0], "y": [3.0, 4.0]})
        a.scatter(x="x", y="y")
        b = pt.chart({"x": [1.0, 2.0], "y": [4.0, 3.0]})
        b.line(x="x", y="y")
        return a | b

    assert pt.resolve_ir(pair().title("first").title("Figure title")).root.title \
        == "Figure title"
    assert pt.resolve_ir(pair()).root.title is None


# ---------------------------------------------------------------------------
# Staged-pipeline pins — the SVG is rendered FROM the resolved IR
# ---------------------------------------------------------------------------


def _rect_chart():
    c = pt.chart({"x": [1.0, 2.0, 3.0], "y": [2.0, 3.1, 4.5],
                  "g": ["a", "b", "a"]}, title="pin")
    c.scatter(x="x", y="y", color="g")
    return c


def _rect_layout():
    a = pt.chart({"x": [1.0, 2.0], "y": [3.0, 4.0]})
    a.scatter(x="x", y="y")
    b = pt.chart({"x": [1.0, 2.0], "y": [4.0, 3.0]})
    b.line(x="x", y="y")
    return (a | b).title("pinned pair")


def _circular():
    c = pt.chart({"x": [1, 2, 3], "y": [1.0, 4.0, 9.0]})
    c.scatter(x="x", y="y")
    lay = pt.grid([[c]])
    lay.coordinate(pt.CircularCoordinate(r_inner=0.3))
    return lay


@pytest.mark.parametrize("build", [_rect_chart, _rect_layout, _circular],
                         ids=["chart", "layout", "circular"])
def test_resolved_ir_renders_byte_identical(build):
    """`resolve_ir(fig).to_svg()` and the normal render agree byte for
    byte — the resolved IR is the artifact the SVG comes from, not a
    parallel account of it. (The whole baseline suite proves this too:
    `render_svg` itself routes through the projection.)"""
    ir = pt.to_ir(build())
    assert resolve_ir(ir).to_svg() == ir.to_svg()


def test_figures_emit_from_projection_alone():
    """The ResolvedIR holds no hidden working tree — `to_svg()`
    rehydrates from `.root` and nothing else, so every projection field
    is load-bearing. Holds for container-coordinate figures too: the
    rehydrated layout rebuilds the coord's overlay plan from projected
    ring states."""
    from plotlet.render.resolved import ResolvedIR

    for build in (_rect_chart, _rect_layout, _circular):
        rir = resolve_ir(pt.to_ir(build()))
        # Rebuilding the wrapper from the projection alone renders
        # identically — nothing rides outside `.root`.
        rebuilt = ResolvedIR(root=rir.root)
        assert rebuilt.to_svg() == pt.to_ir(build()).to_svg()


def test_rehydrated_tree_has_no_journal():
    """Rehydration synthesizes no journal ops — emit reads explicit
    fields (`_theme` / `_font` / `_title_text` / `_had_state`), so
    every node in the rebuilt working tree carries empty `_calls`
    (except ring leaves, whose journals the rebuilt coord plan ignores:
    their states are already resolved)."""
    from plotlet.render.resolved import _rehydrate

    def walk(n):
        assert n._calls == [], \
            f"rehydrated node carries synthesized ops: {n._calls!r}"
        if n._is_parent:
            for c in n._children:
                if c is not None:
                    walk(c)
        else:
            for side in (n._attached_left, n._attached_right,
                         n._attached_above, n._attached_below):
                for a in side:
                    walk(a)
            for _rect, inset in n._insets:
                walk(inset)

    for build in (_rect_chart, _rect_layout, _circular):
        plan = _rehydrate(resolve_ir(pt.to_ir(build())).root)
        walk(plan.root)


def test_resolved_ir_stable_under_render():
    """Rendering a ResolvedIR does not change it — draw-derived artist
    keys (`_color`, hist `_bin_groups`) are stamped at resolve time, so
    a rendered ResolvedIR stays field-equal to a freshly built one."""
    def build():
        c = pt.chart({"v": [1.0, 1.5, 2.0, 2.2, 3.0], "g": ["a"] * 3 + ["b"] * 2})
        c.hist(x="v", fill="g")
        c.scatter(data={"x": [1.0, 2.0], "y": [1.0, 2.0]}, x="x", y="y")
        return pt.to_ir(c)

    rendered = resolve_ir(build())
    rendered.to_svg()
    assert _nan_eq(rendered.root, resolve_ir(build()).root)


@pytest.mark.parametrize("build", [_rect_chart, _rect_layout, _circular],
                         ids=["chart", "layout", "circular"])
def test_emit_never_resolves(build):
    """Once resolved, emitting runs zero resolution — `to_svg()` on a
    ResolvedIR must not touch `_build_panel_opts`, circular included
    (its overlay plan is rebuilt from projected ring states)."""
    from plotlet.render import _layout_engine

    rir = resolve_ir(pt.to_ir(build()))
    orig = _layout_engine._build_panel_opts

    def forbidden(root):
        raise AssertionError("emit re-entered resolution")

    _layout_engine._build_panel_opts = forbidden
    try:
        svg = rir.to_svg()
    finally:
        _layout_engine._build_panel_opts = orig
    assert svg.lstrip().startswith("<svg")


def test_render_resolves_exactly_once():
    """The public render path runs one resolution pass — `render_svg`
    consumes the ResolvedIR's plan instead of re-resolving. (Figures
    with insets legitimately re-enter for the nested render; this pin
    uses a flat chart.)"""
    from plotlet.render import _layout_engine

    calls = {"n": 0}
    orig = _layout_engine._build_panel_opts

    def counting(root):
        calls["n"] += 1
        return orig(root)

    _layout_engine._build_panel_opts = counting
    try:
        _rect_chart().to_svg()
    finally:
        _layout_engine._build_panel_opts = orig
    assert calls["n"] == 1
