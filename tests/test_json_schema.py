"""The shipped journal-lite JSON Schema stays true.

Three guarantees: the checked-in file is byte-identical to what
`tests/gen_json_schema.py` derives from `pt.op_schema()` today (no
drift from the registry), every shipped twin validates against it,
and a kwarg-name typo fails validation — the cheap pre-render check
the schema exists for. Validation tests skip when the `jsonschema`
package (a test extra) is missing.
"""
import functools
import json

import pytest

import plotlet as pt

from gen_json_examples import JSON_DIR
from gen_json_schema import OUT, schema_text

jsonschema = pytest.importorskip("jsonschema")


@functools.cache
def _validator():
    schema = json.loads(OUT.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def test_schema_file_is_current():
    assert OUT.is_file(), "missing schema — run tests/gen_json_schema.py."
    assert OUT.read_text(encoding="utf-8") == schema_text(), (
        "journal_lite.schema.json is stale — run tests/gen_json_schema.py "
        "and review the diff."
    )


def test_every_twin_validates():
    v = _validator()
    twins = sorted(JSON_DIR.glob("*.json"))
    assert twins
    for twin in twins:
        errors = list(v.iter_errors(json.loads(twin.read_text())))
        assert not errors, (twin.name, errors[0].message)


def test_canonical_journal_validates_too():
    # Lite is a superset acceptance — the fully explicit form passes.
    c = pt.chart({"x": [1, 2], "y": [3, 4]}, pt.aes(x="x", y="y"))
    c.add_line()
    blob = pt.to_journal(c).to_dict()
    assert not list(_validator().iter_errors(blob))


def test_kwarg_typo_fails_validation():
    bad = {"entries": [
        {"op": "add_scatter", "nid": 1, "kwargs": {"hue": "g"}}]}
    errors = list(_validator().iter_errors(bad))
    assert errors and "hue" in errors[0].message


def test_unknown_op_passes_schema():
    # Extension ops aren't in the generated schema — they must pass
    # the envelope checks and fail at render with the better message.
    blob = {"entries": [
        {"op": "add_sankey", "nid": 1, "kwargs": {"anything": 1}}]}
    assert not list(_validator().iter_errors(blob))
