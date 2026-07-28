"""`pt.skill()` prints the AI guides shipped inside the package, and the
files the guides point at (docs/, examples/) actually ship next to them."""
from pathlib import Path

import pytest

import plotlet as pt

PKG = Path(pt.__file__).parent


def test_skill_prints_users_guide(capsys):
    pt.skill()
    out = capsys.readouterr().out
    assert "# plotlet users guide" in out
    assert "pt.skill()" in out  # the guide explains how it was loaded


def test_skill_prints_developer_guide(capsys):
    pt.skill("developer")
    out = capsys.readouterr().out
    assert "# plotlet developer guide" in out


def test_skill_rejects_unknown_guide():
    with pytest.raises(ValueError, match="unknown guide"):
        pt.skill("designer")


def test_guides_docs_and_examples_ship_in_the_package():
    assert (PKG / "skills" / "users.md").is_file()
    assert (PKG / "skills" / "developers.md").is_file()
    assert (PKG / "docs" / "AI_ATTRS.md").is_file()
    examples = list((PKG / "examples").glob("*.py"))
    assert len(examples) > 10
