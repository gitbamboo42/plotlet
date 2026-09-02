"""`pt.op_help` — the per-op reference for journal authors.

Every op a journal can carry must serve a non-trivial reference
(signature + docs) keyed by the op string alone — the JSON-authoring
counterpart of `help(c.add_bar)`, see skills/json.md. These tests are
also the guard that a future artist or frame op can't ship
undocumented: op_help derives everything live, so a missing module
docstring or `_FRAME_DOCS` entry fails here.
"""
import inspect

import pytest

import plotlet as pt
from plotlet.op_help import (_CHART_METHOD_OPS, _FRAME_HANDLERS,
                             _LAYOUT_OPS, _NODE_OPS)
from plotlet.record.chart import _FRAME_DOCS, Chart
from plotlet.registry import get_artist


def test_every_artist_op_serves_signature_and_journal_notes():
    for row in pt.artist_table():
        op = f"add_{row['name']}"
        text = pt.op_help(op)
        assert f'"op": "{op}"' in text, f"{op}: journal-form note missing"
        assert f"{op}(" in text, f"{op}: derived parameter list missing"


def test_every_artist_module_has_a_real_docstring():
    # op_help serves the artist module docstring as the reference —
    # an artist without one would return a stub.
    for row in pt.artist_table():
        mod = inspect.getmodule(get_artist(row["name"]).record)
        doc = (mod.__doc__ or "").strip()
        assert len(doc) > 100, f"{row['name']}: artist module needs a docstring"


def test_every_frame_op_serves_reference():
    for op in _FRAME_DOCS:
        text = pt.op_help(op)
        assert f"{op}(" in text, f"{op}: parameter list missing"
        assert "chart node" in text


def test_none_docs_mark_real_chart_methods():
    # A None doc in _FRAME_DOCS means "the specialized Chart method
    # shadows __getattr__ and carries the docstring" — hold that true.
    for op, doc in _FRAME_DOCS.items():
        if doc is None:
            method = getattr(Chart, op, None)
            assert method is not None and method.__doc__, op


def test_frame_handler_map_matches_the_frame_docs():
    # Every __getattr__-dispatched frame op needs a handler to derive
    # its parameter list from; the real-method ops need none.
    real_methods = {op for op, doc in _FRAME_DOCS.items() if doc is None}
    assert set(_FRAME_HANDLERS) == set(_FRAME_DOCS) - real_methods


def test_every_layout_op_serves_reference():
    for op in _LAYOUT_OPS:
        text = pt.op_help(op)
        assert "layout node" in text
        assert f"{op}(" in text


def test_ops_on_both_chart_and_layout_serve_both_sections():
    for op in ("title", "theme", "spec", "coordinate", "sectors"):
        text = pt.op_help(op)
        assert "chart node" in text and "layout node" in text, op


def test_attach_ops_serve_the_chart_method_reference():
    for op in _CHART_METHOD_OPS:
        text = pt.op_help(op)
        assert "chart node" in text
    assert "hide_labels" in pt.op_help("attach_left")


def test_node_ops():
    for op in _NODE_OPS:
        assert pt.op_help(op)
    new_chart = pt.op_help("new_chart")
    assert "(data=None, *" in new_chart          # Chart.__init__, minus self
    assert "**kwargs" not in new_chart           # the reject-trap catch-all
    assert "data_width" in new_chart
    new_layout = pt.op_help("new_layout")
    assert "layout_kind" in new_layout and "bare ints" in new_layout
    assert "legend_sources" in pt.op_help("new_leaf")
    assert "col_wrap" in pt.op_help("new_facet_grid")
    assert "inset_nid" in pt.op_help("_inset_add")


def test_matrix_and_settings_artists_get_matching_journal_notes():
    # The journal-form notes track ArtistSpec.data_input, not one
    # table-shaped boilerplate for everything.
    assert '"args": [{"$data": "d1"}]' in pt.op_help("add_image_cmap")
    assert "reads no table" in pt.op_help("add_axhline")


def test_unset_sentinel_is_explained_when_it_appears():
    text = pt.op_help("xlim")                    # xlim(lo, hi=UNSET)
    assert "UNSET" in text and "omit the key" in text


def test_index_lists_every_op_family():
    idx = pt.op_help()
    for probe in ("new_chart", "new_leaf", "share_x", "xlim",
                  "add_bar", "add_heatmap", "attach_left"):
        assert probe in idx, probe


def test_unknown_op_raises_and_names_the_closest_match():
    with pytest.raises(ValueError) as e:
        pt.op_help("add_barr")
    assert "add_bar" in str(e.value)
    with pytest.raises(ValueError):
        pt.op_help("frobnicate")


def test_op_schema_is_json_serializable_for_every_op():
    import json
    dump = pt.op_schema()
    assert dump["schema_version"] == 1
    json.dumps(dump)                       # the whole point: pure data
    assert "add_bar" in dump["ops"] and "share_x" in dump["ops"]


def test_op_schema_artist_section():
    s = pt.op_schema("add_bar")["sections"][0]
    assert s["kind"] == "artist" and s["data_input"] == "table"
    params = {p["name"]: p for p in s["params"]}
    assert params["stat"]["default"] == "identity"
    assert params["ci"]["default"] == "UNSET"      # repr'd sentinel
    assert "aes" in s["extra_kwargs"]


def test_op_schema_dual_ops_carry_both_sections():
    ons = [s["on"] for s in pt.op_schema("title")["sections"]]
    assert ons == ["chart", "layout"]


def test_op_schema_unknown_op_raises():
    with pytest.raises(ValueError):
        pt.op_schema("add_barr")


def test_node_param_lists_match_what_to_journal_writes():
    # _NODE_PARAMS is hand-listed — pin it to reality: every kwarg
    # to_journal emits for a node entry must be in the list, and the
    # probe figures must between them emit every listed op (a probe
    # set that skips one would quietly unpin it).
    from plotlet.op_help import _NODE_PARAMS
    df = {"x": [1, 2], "y": [3, 4]}

    def pair():
        a = pt.chart(df, pt.aes(x="x", y="y"))
        a.add_scatter(label="pts")
        b = pt.chart(df, pt.aes(x="x", y="y"))
        b.add_line()
        return a, b

    lay = pt.grid([[*pair()]])
    c, d = pair()
    lay2 = c | d | pt.legend(c, d)
    host, _ = pair()
    ins = host.inset((0.6, 0.6, 0.35, 0.35), data=df,
                     aes=pt.aes(x="x", y="y"))
    ins.add_line()
    fdf = {"x": [1, 2, 3, 4], "y": [3, 4, 2, 5], "g": ["a", "a", "b", "b"]}
    fac = pt.facet(fdf, by="g")
    fac.add_scatter(pt.aes(x="x", y="y"))
    seen = set()
    for fig in (lay, lay2, host, fac):
        for entry in pt.to_journal(fig).entries:
            listed = _NODE_PARAMS.get(entry["op"])
            if listed is not None:
                seen.add(entry["op"])
                extra = set(entry["kwargs"]) - set(listed)
                assert not extra, (entry["op"], extra)
    assert seen == set(_NODE_PARAMS)


def test_frame_docs_reach_interactive_help():
    # The same prose serves `help(c.xlim)` — __getattr__ stamps it on
    # the recorder (artists already got their module docstring there).
    c = pt.chart()
    assert "x-axis range" in c.xlim.__doc__
    assert c.xticks.__doc__
    assert c.add_bar.__doc__.startswith("Bar chart")
