"""JSON envelope layer — shared by `record/` and `render/`.

Envelopes Python values that aren't JSON-native (tuple, set, date,
datetime, dicts with non-string keys, DataFrameLite) so they can be
dumped through `json.dumps` and rehydrated. Four consumers: the
journal's JSON form (`record/journal.py`), the FigureIR wire format
(`record/figure_ir.py`), value-envelope decoding at render hydration
(`_decode`, `render/_nodes.py`), and the resolved IR's debug view
(`render/resolved_ir.py`). It sits at the package root because both
`record/` and `render/` need it and neither may import the other
(`tests/test_import_boundary.py`). It also keeps JSON support out of
`journal.py` itself — the journal stays a plain event log.

DataFrame-shaped inputs never reach this layer: they're normalized to
`DataFrameLite` / plain lists at the recorder boundary in
`record/chart.py` (via `utils._normalize_data`), so it never imports
pandas or grows a branch per data library. numpy is the one exception:
a matrix artist's data rides through record as a 2-D ndarray (numpy is
a guaranteed dependency, via scipy), and `json_safe` lowers it to
nested lists — the JSON wire format itself carries no array types.

Envelope keys used here:
    $dataframe    utils.DataFrameLite (canonical DataFrame form)
    $tuple        tuple (JSON has no tuple type; without this every
                  tuple would silently degrade to list, breaking
                  isinstance dispatch inside artist code)
    $set          set
    $date         datetime.date
    $datetime     datetime.datetime
    $dict_pairs   dict whose keys aren't all JSON-native strings

`_decode` at the bottom handles the other envelope family — the
*reference* envelopes ($node / $coord / $sectors / $data) that journals
and IRs carry whether or not they ever touch JSON. It lives here because
both halves need it (the render tree's hydrator and the front half's
facet expansion) and it resolves only against shared vocabulary.
"""
from __future__ import annotations
import json
from typing import Any

import numpy as np

from .utils import DataFrameLite, all_primitive


def json_safe(value: Any) -> Any:
    """Walk `value`, replace non-JSON types with envelopes. Plotlet
    envelopes ($node / $coord / $sectors) already added at `to_journal`
    time pass through as regular dicts — their inner values still get
    recursed."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    # datetime.datetime is a subclass of datetime.date — check the more
    # specific type first so datetimes get $datetime, not $date.
    import datetime as _dt
    if isinstance(value, _dt.datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, _dt.date):
        return {"$date": value.isoformat()}
    if isinstance(value, DataFrameLite):
        # index and cell values recurse — a date/datetime column must
        # wire as `$date` / `$datetime` cells, same as anywhere else.
        return {"$dataframe": {
            "columns": value.columns,
            "index":   [json_safe(v) for v in value.index],
            "values":  [[json_safe(v) for v in row] for row in value.values],
        }}
    from .sectors import Sectors
    if isinstance(value, Sectors):
        # Live instance → the same envelope `to_journal` emits and
        # `_decode` reconstructs (`Sectors._from_dict`). Reached by
        # values that never passed through the journal emitter, e.g. a
        # resolved-IR state dict.
        return {"$sectors": json_safe(value._to_dict())}
    if isinstance(value, np.ndarray):
        # A matrix artist's data section entry. The wire format stays
        # plain nested lists — identical JSON whether the matrix came
        # in as an array or as lists. Recursing catches the rare
        # object-dtype cell.
        return json_safe(value.tolist())
    if isinstance(value, tuple):
        return {"$tuple": [json_safe(v) for v in value]}
    if isinstance(value, (set, frozenset)):
        # Iteration order is hash order, which varies across processes
        # (PYTHONHASHSEED) — sort the serialized elements so $set
        # payloads are byte-stable.
        return {"$set": sorted((json_safe(v) for v in value), key=repr)}
    if isinstance(value, dict):
        if all(isinstance(k, str) for k in value):
            return {k: json_safe(v) for k, v in value.items()}
        # Non-string key means the whole dict can't be a JSON object;
        # emit as a list of [key, value] pairs.
        return {"$dict_pairs": [[json_safe(k), json_safe(v)]
                                for k, v in value.items()]}
    if isinstance(value, list):
        # Bulk numeric rows are already JSON-native — one flat scan
        # instead of per-cell recursion (same bail-out in json_hydrate,
        # _decode, and the journal/IR walkers).
        if all_primitive(value):
            return list(value)
        return [json_safe(v) for v in value]
    return value


def json_hydrate(value: Any) -> Any:
    """Inverse of `json_safe`. Plotlet envelopes ($node / $coord /
    $sectors) are left as dicts — the journal's own `_decode` handles
    them at replay time."""
    if isinstance(value, dict):
        if "$dataframe" in value:
            d = value["$dataframe"]
            return DataFrameLite(
                values=[[json_hydrate(v) for v in row]
                        for row in d["values"]],
                columns=d["columns"],
                index=[json_hydrate(v) for v in d["index"]],
            )
        if "$tuple" in value:
            return tuple(json_hydrate(v) for v in value["$tuple"])
        if "$set" in value:
            return {json_hydrate(v) for v in value["$set"]}
        if "$date" in value:
            import datetime as _dt
            return _dt.date.fromisoformat(value["$date"])
        if "$datetime" in value:
            import datetime as _dt
            return _dt.datetime.fromisoformat(value["$datetime"])
        if "$dict_pairs" in value:
            return {json_hydrate(k): json_hydrate(v)
                    for k, v in value["$dict_pairs"]}
        return {k: json_hydrate(v) for k, v in value.items()}
    if isinstance(value, list):
        if all_primitive(value):
            return list(value)
        return [json_hydrate(v) for v in value]
    return value


_PRETTY_WIDTH = 100     # target line width for pretty_dumps


def pretty_dumps(value: Any) -> str:
    """Canonical JSON text form — what `pt.to_json` returns and the
    shipped example twins use. Objects and arrays stay on one line when
    they fit in `_PRETTY_WIDTH` columns; a too-long dict or mixed list
    expands one element per line (1-space indent steps); a too-long
    list of primitives wraps at the width, continuation lines aligned
    under its opening bracket — so journal entries read structurally
    while data columns stay a few dense lines. Deterministic (same
    value → same bytes) and whitespace-only: `json.loads` of the
    result equals `json.loads(json.dumps(value))`."""
    return _pretty(value, 0, "")


def _pretty(value: Any, col: int, pad: str) -> str:
    """Render `value` starting at column `col`; `pad` is the
    indentation of the enclosing construct."""
    compact = json.dumps(value)
    if col + len(compact) <= _PRETTY_WIDTH \
            or not isinstance(value, (dict, list)):
        return compact
    inner = pad + " "
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            key = f"{inner}{json.dumps(k)}: "
            lines.append(key + _pretty(v, len(key), inner))
        return "{\n" + ",\n".join(lines) + "\n" + pad + "}"
    if all(not isinstance(v, (dict, list)) for v in value):
        room = max(_PRETTY_WIDTH - col - 1, 20)     # width left after "["
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


def _decode(value: Any, nid_to_node: dict, data_table: dict) -> Any:
    """Resolve plotlet's *reference* envelopes back to live objects —
    `{"$node"}` via `nid_to_node`, `{"$coord"}` via the coord registry,
    `{"$sectors"}` via `Sectors`, `{"$data"}` via `data_table` (the
    Journal's / FigureIR's data section). Containers recurse; everything
    else passes through.

    Distinct from `json_hydrate` above: that undoes the JSON-native
    envelopes at the JSON boundary, while these reference envelopes live
    in journals and IRs whether or not they ever touch JSON, and decode
    at hydration time. Shared vocabulary — used by the render tree's
    hydrator (`render.hydrate`) and by the facet expansion in
    `record/figure_ir.py`."""
    if isinstance(value, dict):
        if "$node" in value and len(value) == 1:
            return nid_to_node[value["$node"]]
        if "$data" in value and len(value) == 1:
            return data_table[value["$data"]]
        if "$coord" in value:
            from ._coord_registry import resolve_coord
            cls = resolve_coord(value["$coord"])
            return cls._from_dict(
                _decode(value.get("kwargs", {}), nid_to_node, data_table))
        if "$sectors" in value:
            from .sectors import Sectors
            return Sectors._from_dict(
                _decode(value["$sectors"], nid_to_node, data_table))
        if "$aes" in value and len(value) == 1:
            from .utils import Aes
            return Aes(value["$aes"])
        return {k: _decode(v, nid_to_node, data_table)
                for k, v in value.items()}
    if isinstance(value, list):
        if all_primitive(value):
            return list(value)
        return [_decode(v, nid_to_node, data_table) for v in value]
    if isinstance(value, tuple):
        if all_primitive(value):
            return value
        return tuple(_decode(v, nid_to_node, data_table) for v in value)
    return value
