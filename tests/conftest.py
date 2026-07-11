"""Shared pytest fixtures for plotlet's baseline-image suites.

Each baseline test parametrizes over a `PLOTS` dict (name → callable that
returns a `pt.Chart`), and calls `baseline_compare(set_name, plot_name,
svg)`. Baselines live at `tests/baseline_images/<set>/<name>.svg`.

Custom CLI flags:
    pytest --update     regenerate baseline files instead of comparing
                        (review the diff before committing)

Gallery HTML is its own script: `python tests/gen_gallery.py`.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
BASELINE_ROOT = HERE / "baseline_images"

# `data-plotlet-version` changes every release by definition — strip it
# before comparing so a version bump alone doesn't invalidate every
# committed baseline. All other `data-plotlet-*` attrs describe the plot
# itself and stay in the compare.
_VOLATILE_ATTR_RE = re.compile(
    r' data-plotlet-version="[^"]*"'
)


def _normalize(svg: str) -> str:
    return _VOLATILE_ATTR_RE.sub("", svg)


def pytest_addoption(parser):
    parser.addoption(
        "--update", action="store_true", default=False,
        help="Regenerate baseline SVGs instead of comparing.",
    )


@pytest.fixture
def baseline_compare(request):
    """Returns a function `(set_name, plot_name, svg) -> None` that either
    regenerates the baseline file (when `--update`) or asserts byte-equal
    to the existing baseline (after normalizing the volatile version attr).
    On mismatch, writes `<name>.actual.svg` next to the baseline so the
    diff is easy to view, and surfaces a short unified diff in the
    failure message."""
    update = request.config.getoption("--update")

    # Encoding and newline are pinned so Windows behaves like everywhere
    # else: the locale default there is cp1252 (breaks non-ASCII labels)
    # and text-mode writes would translate \n to \r\n. Reads keep
    # universal-newline translation so an autocrlf checkout still
    # compares clean.
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _write(path: Path, svg: str) -> None:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(svg)

    def _compare(set_name: str, plot_name: str, svg: str) -> None:
        baseline_dir = BASELINE_ROOT / set_name
        baseline_dir.mkdir(parents=True, exist_ok=True)
        target = baseline_dir / f"{plot_name}.svg"
        if update:
            if target.exists() and _normalize(_read(target)) == _normalize(svg):
                return
            _write(target, svg)
            return
        assert target.exists(), (
            f"baseline missing: {target} — run `pytest --update` to create it"
        )
        expected = _read(target)
        if _normalize(expected) == _normalize(svg):
            return
        actual_path = target.with_suffix(".actual.svg")
        _write(actual_path, svg)
        diff = list(difflib.unified_diff(
            _normalize(expected).splitlines(),
            _normalize(svg).splitlines(),
            fromfile="baseline", tofile="actual", lineterm="", n=1,
        ))
        head = "\n".join(diff[:12])
        tail = f"\n... ({len(diff) - 12} more diff lines)" if len(diff) > 12 else ""
        pytest.fail(
            f"{set_name}/{plot_name}.svg mismatch — wrote {actual_path.name}\n{head}{tail}"
        )

    return _compare
