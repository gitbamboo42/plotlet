"""Resolved-IR sanity: for every baseline plot, `resolve_ir` must:

  * run without error
  * produce a JSON-safe result (envelopes only via `_json_layer`)
  * be deterministic (same figure built twice → equal resolved IR)
  * emit valid IRScale kinds and populated IRArtist kinds

The resolved IR is a projection, not a round-trip peer — the
byte-identical round-trip proof lives with the journal / figure-IR
suites (`test_journal_roundtrip.py`, `test_ir.py`). This suite is a
structural smoke over the same PLOTS registry.
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
)
from plotlet._json_layer import json_safe

from test_journal_roundtrip import PLOTS


_VALID_SCALE_KINDS = {"linear", "log", "category", "symlog", "power",
                      "sqrt", "time"}


def _walk_panels(ir):
    """Yield every IRPanel (data or non-data) in the resolved IR."""
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
    ir = resolve_ir(fig)

    assert isinstance(ir, (IRPanel, IRLayout)), \
        f"root IR must be a panel or layout, got {type(ir).__name__}"

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
    assert _nan_eq(ir1, ir2), "resolved IR should be identical across two builds"


@pytest.mark.parametrize("label,fn", PLOTS, ids=[p[0] for p in PLOTS])
def test_resolve_ir_json_safe(label, fn):
    ir = resolve_ir(fn())
    # Enveloping walks the whole tree — a non-JSON-safe leaf value
    # raises somewhere. Then json.dumps must not fail either.
    enveloped = json_safe(_to_plain(ir))
    json.dumps(enveloped)


def _to_plain(v):
    """Dataclass IR → plain dict/list so `json_safe` doesn't need to
    grow a dataclass branch. Recurse only through IR containers."""
    if isinstance(v, (IRPanel, IRLayout, IRScale, IRCoord, IRArtist)):
        return {k: _to_plain(getattr(v, k)) for k in v.__dataclass_fields__}
    if isinstance(v, dict):
        return {k: _to_plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_to_plain(x) for x in v]
    return v


def test_figure_ir_resolve_method():
    """`FigureIR.resolve()` and `pt.resolve_ir(fig)` agree."""
    data = {"x": [1, 2, 3], "y": [2.0, 3.1, 4.5]}
    c = pt.chart(data_width=200, data_height=140, title="t")
    c.scatter(data=data, x="x", y="y")
    via_method = pt.to_ir(c).resolve()
    via_fn = pt.resolve_ir(c)
    assert _nan_eq(via_method, via_fn)
    assert via_method.chrome.get("title") == "t"


def test_layout_title_projected():
    """A layout's figure-title band is visible in the resolved IR —
    `IRLayout.title`, last call wins, `None` when untitled."""
    def pair():
        a = pt.chart({"x": [1.0, 2.0], "y": [3.0, 4.0]})
        a.scatter(x="x", y="y")
        b = pt.chart({"x": [1.0, 2.0], "y": [4.0, 3.0]})
        b.line(x="x", y="y")
        return a | b

    assert pt.resolve_ir(pair().title("first").title("Figure title")).title \
        == "Figure title"
    assert pt.resolve_ir(pair()).title is None
