"""Help-bridge tests — `Chart.__getattr__` attaches each artist's module
docstring to the returned recorder so `c.add_line?` / `help(c.add_line)` /
`c.add_line.__doc__` work via Python's standard introspection."""

import plotlet as pt


def test_artist_doc_surfaces_on_recorder():
    c = pt.chart()
    assert "arc=False" in (c.add_line.__doc__ or "")
    assert c.add_line.__name__ == "add_line"


def test_frame_method_has_no_artist_doc():
    # Frame methods go through the recorder path too but have no artist
    # spec — they document via docs/API.md, not module docstrings. Pin
    # the current behavior so a future change is explicit.
    c = pt.chart()
    assert c.title.__doc__ is None


# ---------------------------------------------------------------------------
# reprs — one-line state summaries for the terminal REPL / print /
# debugger. Built from recorded state only; must never render (a child
# chart inside a layout can't).
# ---------------------------------------------------------------------------


def test_chart_repr_summarizes_state():
    from plotlet import aes
    df = {"x": [1, 2, 3], "y": [1.0, 2.0, 3.0], "g": ["a", "b", "a"]}
    c = pt.chart(df, aes(x="x", y="y", color="g"),
                 data_width=300, data_height=200)
    c.add_line()
    c.add_scatter()
    r = repr(c)
    assert "300×200px" in r
    assert "3 rows × 3 cols" in r
    assert "color='g'" in r
    assert "line, scatter" in r


def test_empty_chart_repr():
    r = repr(pt.chart())
    assert r.startswith("<Chart") and "no artists" in r


def test_repr_works_on_parented_child():
    from plotlet import aes
    df = {"x": [1, 2], "y": [1.0, 2.0]}
    a = pt.chart(df, aes(x="x", y="y")); a.add_line()
    b = pt.chart(df, aes(x="x", y="y")); b.add_line()
    lay = a | b
    # a child can't render, but its repr must still work
    assert "line" in repr(a)
    assert repr(lay) == "<Layout h, 2 children>"


def test_facet_grid_repr():
    from plotlet import aes
    g = pt.facet({"x": [1, 2], "s": ["a", "b"]}, by="s")
    g.add_scatter(aes(x="x", y="x"))
    assert repr(g) == "<FacetGrid by='s', 1 recorded call>"
