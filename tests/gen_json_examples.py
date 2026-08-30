"""Regenerate the JSON twin of every shipped example.

    python tests/gen_json_examples.py

Each `src/plotlet/examples/NN_<name>.py` builds a figure in a variable
named `c`. This script executes each one, serializes the figure with
`pt.to_json`, and writes `src/plotlet/examples/json/NN_<name>.json`.
The pairs are the ground truth for authoring journal JSON by hand (see
`skills/json.md`) — generated, never edited, so they cannot drift from
what `to_json` actually emits. `tests/test_json_examples.py` fails if a
checked-in twin goes stale; rerun this script to fix it.

The twins exist to teach the *format*, not to carry data: every column
table is thinned to at most `MAX_ROWS` evenly spaced rows before
writing, so an AI reading a twin doesn't wade through hundreds of data
rows (and the wheel stays small). Evenly spaced — not first-N — so a
sorted category column keeps all its categories. The entries are
untouched; only the data section shrinks. Matrix tables (nested row
lists) are left whole, and any example whose thinned JSON still
exceeds `MAX_BYTES` gets no twin — that's megabytes of inlined matrix,
useless as a format example.
"""
from __future__ import annotations

import json
from pathlib import Path

import plotlet as pt

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent / "src" / "plotlet" / "examples"
JSON_DIR = EXAMPLES / "json"

MAX_BYTES = 100_000
MAX_ROWS = 60   # per-table row cap in the twins (evenly sampled)
WIDTH = 100     # target line width for the pretty form


def _thin_tables(blob: dict) -> dict:
    """Subsample every column table in `blob["data"]` to at most
    `MAX_ROWS` rows, keeping row alignment across columns (one stride
    per table). The result is still a valid journal that loads and
    renders — it just plots a thinner slice of the data."""
    for did, table in blob["data"].items():
        if not isinstance(table, dict):
            continue    # matrix (nested lists) — leave whole
        if "$dataframe" in table:
            d = table["$dataframe"]
            n = len(d["values"])
            if n > MAX_ROWS:
                step = -(-n // MAX_ROWS)
                d["values"] = d["values"][::step]
                d["index"] = d["index"][::step]
            continue
        lengths = [len(v) for v in table.values() if isinstance(v, list)]
        n = max(lengths, default=0)
        if n <= MAX_ROWS:
            continue
        step = -(-n // MAX_ROWS)
        blob["data"][did] = {
            k: (v[::step] if isinstance(v, list) and len(v) == n else v)
            for k, v in table.items()
        }
    return blob


def _pretty(value, col: int, pad: str) -> str:
    """Render `value` as JSON starting at column `col`, with `pad` as
    the indentation of the enclosing construct. Anything that fits on
    the current line stays on one line; a too-long dict or mixed list
    expands one element per line (1-space indent steps); a too-long
    list of primitives wraps at `WIDTH`, continuation lines aligned
    under its opening bracket. `json.loads` of the result equals the
    input — only whitespace differs from `json.dumps`."""
    compact = json.dumps(value)
    if col + len(compact) <= WIDTH or not isinstance(value, (dict, list)):
        return compact
    inner = pad + " "
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            key = f"{inner}{json.dumps(k)}: "
            lines.append(key + _pretty(v, len(key), inner))
        return "{\n" + ",\n".join(lines) + "\n" + pad + "}"
    if all(not isinstance(v, (dict, list)) for v in value):
        room = max(WIDTH - col - 1, 20)     # width left after "["
        parts, lines, used = [json.dumps(v) for v in value], [], -2
        for part in parts:
            if used < 0 or used + 2 + len(part) > room:
                lines.append([part])
                used = len(part)
            else:
                lines[-1].append(part)
                used += 2 + len(part)
        joined = (",\n" + " " * (col + 1)).join(
            ", ".join(line) for line in lines)
        return "[" + joined + "]"
    lines = [inner + _pretty(v, len(inner), inner) for v in value]
    return "[\n" + ",\n".join(lines) + "\n" + pad + "]"


def example_json(py_path: Path) -> str:
    """Execute one example and return its journal JSON, ready to write."""
    ns: dict = {}
    src = py_path.read_text(encoding="utf-8")
    exec(compile(src, str(py_path), "exec"), ns)
    blob = _thin_tables(pt.to_json(ns["c"]))
    return _pretty(blob, 0, "") + "\n"


def main() -> None:
    JSON_DIR.mkdir(exist_ok=True)
    for py_path in sorted(EXAMPLES.glob("*.py")):
        out = JSON_DIR / (py_path.stem + ".json")
        text = example_json(py_path)
        if len(text) > MAX_BYTES:
            out.unlink(missing_ok=True)
            print(f"skip {py_path.stem}: {len(text):,} bytes > {MAX_BYTES:,}")
            continue
        # newline="\n" so a Windows regeneration doesn't rewrite every
        # twin with CRLF endings (same rule as the SVG baselines in
        # conftest.py).
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"{out.relative_to(EXAMPLES.parent)}  ({len(text):,} bytes)")


if __name__ == "__main__":
    main()
