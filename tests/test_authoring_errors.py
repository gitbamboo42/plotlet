"""Authoring-error catalog — what a journal author sees when a blob
is wrong.

One case per realistic wrong blob, pinning the message it produces
today. Error messages are UX, like pixel baselines: a change to what
an author sees must show up here as a deliberate re-pin, and when a
new complaint arrives it becomes a case first, then gets fixed.
"""
import pytest

import plotlet as pt

DF = {"x": [1, 2, 3], "y": [2, 4, 3], "g": ["a", "a", "b"]}
CH = {"op": "new_chart", "nid": 1,
      "kwargs": {"data": dict(DF), "aes": {"x": "x", "y": "y"}}}

# (case id, entries, substrings the error must contain,
#  substrings it must NOT contain)
CASES = [
    ("unknown_op",
     [CH, {"op": "add_barr", "nid": 1}],
     ["add_barr", "does not resolve"], []),
    ("dangling_data_ref",
     [{"op": "new_chart", "nid": 1,
       "kwargs": {"data": {"$data": "d9"}, "aes": {"x": "x", "y": "y"}}},
      {"op": "add_line", "nid": 1}],
     ["'d9'", "data section"], []),
    ("no_aes_anywhere",
     [{"op": "new_chart", "nid": 1, "kwargs": {"data": dict(DF)}},
      {"op": "add_line", "nid": 1}],
     ["line requires", "x=", "y="], []),
    ("wrong_kwarg_name",
     [CH, {"op": "add_scatter", "nid": 1, "kwargs": {"hue": "g"}}],
     ["unexpected keyword argument 'hue'"], []),
    ("nid_never_created",
     [CH, {"op": "add_line", "nid": 7}],
     ["no earlier create entry"], []),
    ("artist_before_chart",
     [{"op": "add_line", "nid": 1}, dict(CH)],
     ["no earlier create entry"], []),
    ("node_envelope_in_children",
     [CH, {"op": "new_layout", "nid": 2,
           "kwargs": {"layout_kind": "h", "children": [{"$node": 1}],
                      "grid_rows": None, "grid_cols": None}}],
     ["bare int nids"], []),
    ("bad_option_value",
     [CH, {"op": "add_bar", "nid": 1, "kwargs": {"stat": "avg"}}],
     ["identity", "count", "mean"], []),
    ("unknown_column",
     [CH, {"op": "add_line", "nid": 1,
           "kwargs": {"aes": {"x": "x", "y": "nope"}}}],
     ["no column named 'nope'", "Columns"], []),
    ("matrix_artist_given_table",
     [CH, {"op": "add_image_cmap", "nid": 1, "kwargs": {"data": dict(DF)}}],
     ["unexpected keyword argument 'data'"], []),
]


@pytest.mark.parametrize("name,entries,must,must_not", CASES,
                         ids=[c[0] for c in CASES])
def test_wrong_blob_fails_with_a_self_correcting_message(
        name, entries, must, must_not):
    with pytest.raises(Exception) as excinfo:
        pt.from_json_lite({"entries": entries}).to_svg()
    msg = str(excinfo.value)
    for token in must:
        assert token in msg, f"{name}: error should mention {token!r}\n{msg}"
    for token in must_not:
        assert token not in msg, f"{name}: forbidden text in error\n{msg}"
