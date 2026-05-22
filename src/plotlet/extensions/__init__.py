"""Vetted, ready-to-use plot extensions — importable after `pip install plotlet`.

Each module registers a custom artist on `plotlet` at import time, so the
usage pattern is import-for-side-effect, then call the method on a chart:

    import plotlet as pt
    import plotlet.extensions.volcano  # registers c.volcano(...)

    c = pt.chart()
    c.volcano(fc, pvals, labels, fc_threshold=1.0, p_threshold=0.01)
    c.save_svg("out.svg")

Every extension also exposes a `demo()` function that returns a fully built
`pt.Chart` with synthetic data — useful as a starting point:

    from plotlet.extensions.volcano import demo
    demo().save_svg("out.svg")

The `__main__` block at the bottom of each file is the demo harness used by
`_gallery.py` to regenerate `<name>.svg` for the visual gallery; it is not
the user-facing entry point.
"""
