"""The shipped JSON example twins stay in sync with the Python examples.

Every `examples/NN_<name>.py` under the size cap must have a
`examples/json/NN_<name>.json` twin that is byte-identical to what
`tests/gen_json_examples.py` emits for that example today (the
journal-lite authoring form: `pt.to_json` piped through
`journal_lite.simplify`, tables thinned, pretty-printed), and every
shipped twin must load through `pt.from_json_lite` and render. On
failure, rerun `python tests/gen_json_examples.py` and review the diff.
"""
import json

import pytest

import plotlet as pt

from gen_json_examples import EXAMPLES, JSON_DIR, MAX_BYTES, example_json

EXAMPLE_PATHS = sorted(EXAMPLES.glob("*.py"))


@pytest.mark.parametrize("py_path", EXAMPLE_PATHS,
                         ids=[p.stem for p in EXAMPLE_PATHS])
def test_json_twin_is_current(py_path):
    twin = JSON_DIR / (py_path.stem + ".json")
    text = example_json(py_path)
    if len(text) > MAX_BYTES:
        assert not twin.exists(), (
            f"{twin.name} is over the {MAX_BYTES:,}-byte cap and should "
            f"not ship — rerun tests/gen_json_examples.py to remove it."
        )
        return
    assert twin.is_file(), (
        f"missing twin {twin.name} — run tests/gen_json_examples.py."
    )
    assert twin.read_text(encoding="utf-8") == text, (
        f"{twin.name} is stale — run tests/gen_json_examples.py "
        f"and review the diff."
    )


@pytest.mark.parametrize("json_path", sorted(JSON_DIR.glob("*.json")),
                         ids=[p.stem for p in sorted(JSON_DIR.glob("*.json"))])
def test_json_twin_loads_and_renders(json_path):
    blob = json.loads(json_path.read_text(encoding="utf-8"))
    svg = pt.from_json_lite(blob).to_svg()
    assert svg.startswith("<svg")


def test_no_orphan_twins():
    stems = {p.stem for p in EXAMPLE_PATHS}
    orphans = [p.name for p in JSON_DIR.glob("*.json") if p.stem not in stems]
    assert not orphans, f"twins with no matching example: {orphans}"
