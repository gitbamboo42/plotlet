"""Figure IR correctness: journal → IR → plot, byte-identical.

Two sweeps over the same PLOTS registry the journal round-trip uses:

  - In-memory:  `pt.to_ir(fig).to_svg()` == `fig.to_svg()`, and the IR
                flattens back to a journal that replays identically
                (lowering is loss-free both ways).
  - JSON:       `pt.from_ir(json.loads(json.dumps(ir.to_dict())))`
                renders identically — exercises the `_json_layer` on
                the IR's dict form.

Plus structural checks on the IR itself: dependency ordering of the
node table, kind mapping, and version guarding.
"""
from __future__ import annotations

import json

import pytest

import plotlet as pt
from plotlet._ir import journal_to_ir, ir_to_journal, _node_refs

from test_journal_roundtrip import PLOTS


@pytest.mark.parametrize("label,fn", PLOTS, ids=[p[0] for p in PLOTS])
def test_ir_roundtrip(label, fn):
    """journal → IR → plot must render byte-identical to the tree path,
    and IR → journal → plot must too."""
    fig = fn()
    svg_original = fig.to_svg()

    ir = pt.to_ir(fig)
    svg_from_ir = ir.to_svg()
    assert svg_original == svg_from_ir, (
        f"{label}: IR round-trip diverged "
        f"(original={len(svg_original)} bytes, "
        f"materialized={len(svg_from_ir)} bytes)"
    )

    svg_via_journal = pt.from_journal(ir_to_journal(ir)).to_svg()
    assert svg_original == svg_via_journal, (
        f"{label}: IR → journal flattening diverged"
    )


@pytest.mark.parametrize("label,fn", PLOTS, ids=[p[0] for p in PLOTS])
def test_ir_json_roundtrip(label, fn):
    """IR dict form must survive `json.dumps` / `json.loads` and
    rehydrate to an identical render."""
    fig = fn()
    svg_original = fig.to_svg()

    blob = pt.to_ir(fig).to_dict()
    text = json.dumps(blob)
    ir2 = pt.from_ir(json.loads(text))
    svg_from_json = ir2.to_svg()

    assert svg_original == svg_from_json, (
        f"{label}: IR JSON round-trip diverged "
        f"(original={len(svg_original)} bytes, "
        f"replayed={len(svg_from_json)} bytes)"
    )


def _composed_fig():
    """A figure exercising every cross-node reference form: layout
    children, a legend with sources and name overrides, an attachment,
    and an inset."""
    data = {"x": [1, 2, 3, 4, 5], "y": [2.0, 3.5, 3.1, 4.8, 4.2]}
    a = pt.chart(data_width=200, data_height=140, title="a")
    a.scatter(data=data, x="x", y="y", label="pts")
    inset = a.inset(rect=(0.55, 0.55, 0.4, 0.4))
    inset.line(data=data, x="x", y="y")

    top = pt.chart(data_width=200, data_height=40)
    top.bar(data=data, x="x", y="y")
    a.attach_above(top)

    b = pt.chart(data_width=200, data_height=140, title="b")
    b.line(data=data, x="x", y="y", label="trend")

    return a | b | pt.legend(a, b, names={a: "Panel A"})


def test_nodes_dependency_ordered():
    """Every nid a node references must appear earlier in `ir.nodes`."""
    ir = pt.to_ir(_composed_fig())
    position = {n.nid: i for i, n in enumerate(ir.nodes)}
    assert len(position) == len(ir.nodes), "duplicate nid in node table"
    for n in ir.nodes:
        for ref in _node_refs(n):
            assert position[ref] < position[n.nid], (
                f"node {n.nid} ({n.kind}) references {ref} "
                f"which appears later in the table"
            )
    assert ir.root_nid == ir.nodes[-1].nid, "root should close the table"


def test_ir_node_kinds():
    """Kinds map from journal create ops: leaf_kind lifts into `kind`."""
    from collections import Counter
    ir = pt.to_ir(_composed_fig())
    kinds = Counter(n.kind for n in ir.nodes)
    # a, b, the attachment, and the inset are data charts; the legend
    # leaf carries kind "legend"; composition contributes layout nodes.
    assert kinds["chart"] == 4
    assert kinds["legend"] == 1
    assert kinds["layout"] >= 1
    for n in ir.nodes:
        assert "leaf_kind" not in n.init


def test_ir_insets_are_first_class():
    """`_inset_add` journal events become the host node's `insets` list,
    not opaque ops."""
    ir = pt.to_ir(_composed_fig())
    hosts = [n for n in ir.nodes if n.insets]
    assert len(hosts) == 1
    (ins,) = hosts[0].insets
    assert ins["rect"] == [0.55, 0.55, 0.4, 0.4]
    assert ins["chart_nid"] in {n.nid for n in ir.nodes}
    assert not any(op["op"] == "_inset_add"
                   for n in ir.nodes for op in n.ops)


def test_journal_ir_journal_stable():
    """Lowering and flattening are inverses up to entry ordering:
    journal → IR → journal → IR reproduces the same IR."""
    fig = _composed_fig()
    ir1 = pt.to_ir(fig)
    ir2 = journal_to_ir(ir_to_journal(ir1))
    assert ir1 == ir2


def test_from_ir_version_check():
    ir = pt.to_ir(_composed_fig())
    blob = ir.to_dict()
    blob["version"] = 99
    with pytest.raises(ValueError, match="unsupported version"):
        pt.from_ir(blob)


def test_journal_to_ir_requires_root():
    with pytest.raises(ValueError, match="root_nid"):
        journal_to_ir(pt.Journal(entries=[]))
