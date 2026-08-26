"""The spec.json root namespace and artist-block ownership, enforced.

The contract (`docs/THEMES.md`): the spec root holds chrome sections
(`font`, `frame`, `grid`, …), a handful of shared scalar keys any
artist may read (`linewidth`, `marker_size`, `cmap`, …), and one block
per plot type (`scatter`, `errorbar`, …) read only by the modules
declared in OWNERS below. A block with more than one owner is a
*deliberate* consistency decision — error whiskers look the same
whether `errorbar` or `bar` draws them — never convenience reuse
("that value looks about right for my new artist"). Adding a reader
means editing OWNERS here, which is the point: cross-reads happen as a
visible one-line decision, not silent drift. The map doubles as the
record of which sharings are intentional.

Enforced in both directions: every block read in `src/plotlet/` must
be declared, and every declared owner must still read its block — so
the map can't rot into fiction. The root partition is pinned too
(every root key is a chrome section, a shared scalar, or a declared
block), and a read of a key that doesn't exist in the spec at all
fails — the scan is how a phantom read gets caught before the
KeyError ships.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "plotlet"

# Chrome sections: figure-level machinery, not artist ink.
CHROME = {"size", "figure", "font", "pad", "frame", "grid", "sectors",
          "linestyles", "scale", "raster", "legend", "layout"}

# Shared scalar keys any artist may read.
SHARED = {"linewidth", "marker_size", "marker_stroke_width", "cmap"}

# Artist block -> module stems (under src/plotlet/, any subpackage)
# that may read it. `_shared` appears where it paints an artist's
# legend swatch with that artist's own ink.
OWNERS = {
    "scatter":    {"scatter"},
    "bar":        {"bar", "numeric_bar", "shapes"},   # bar family
    "hist":       {"hist"},
    "fill":       {"fills"},
    "refline":    {"references", "_shared"},
    "refspan":    {"references", "_shared"},
    "errorbar":   {"errorbar", "bar"},    # whiskers look the same everywhere
    "dendrogram": {"dendrogram"},
    "qq":         {"qq"},
    "heatmap":    {"heatmap", "image_cmap"},   # image_cmap shares cell-annotation style
    "text":       {"text"},
    "annotate":   {"text"},   # the annotate artist lives in text.py
}

# `SPEC["key"]` and `ctx.spec["key"]` — the first subscript after a
# handle for the root spec dict.
_READ = re.compile(r'(?:(?<![A-Za-z_])SPEC|\.spec)\["([^"]+)"\]')


def _spec() -> dict:
    return json.loads((SRC / "spec.json").read_text(encoding="utf-8"))


def _reads() -> list[tuple[str, str]]:
    """(module stem, first-level spec key) for every read in src."""
    out = []
    for py in SRC.rglob("*.py"):
        if py.name == "_spec.py":
            continue  # owns the handles, reads nothing
        for m in _READ.finditer(py.read_text(encoding="utf-8")):
            out.append((py.stem, m.group(1)))
    return out


def test_root_partition():
    spec = _spec()
    blocks = set(OWNERS)
    root = set(spec) - {"version"}
    assert root == CHROME | SHARED | blocks, (
        "spec.json root keys and the declared partition disagree — "
        f"undeclared or stale: {sorted(root ^ (CHROME | SHARED | blocks))}"
    )
    for k in CHROME | blocks:
        assert isinstance(spec[k], dict), f"{k} should be a dict"
    for k in SHARED:
        assert not isinstance(spec[k], dict), f"{k} should be a scalar"


def test_block_reads_are_declared():
    spec = _spec()
    for module, key in _reads():
        assert key in spec, (
            f"{module}.py reads SPEC[{key!r}], which does not exist "
            "in spec.json — phantom read"
        )
        if key in OWNERS:
            assert module in OWNERS[key], (
                f"{module}.py reads the {key!r} block but is not a "
                f"declared owner {sorted(OWNERS[key])}. Same visual "
                "concept? Add it to OWNERS. Different concept? Give "
                "your artist its own key."
            )


def test_declared_owners_still_read():
    per_block: dict[str, set] = {b: set() for b in OWNERS}
    for module, key in _reads():
        if key in per_block:
            per_block[key].add(module)
    stale = {b: sorted(OWNERS[b] - readers)
             for b, readers in per_block.items() if OWNERS[b] - readers}
    assert not stale, f"OWNERS lists modules that no longer read the block: {stale}"
