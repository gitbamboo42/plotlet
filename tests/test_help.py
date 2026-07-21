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
