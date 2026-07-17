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

DataFrame-shaped and numpy inputs never reach this layer: they're
normalized to `DataFrameLite` / plain lists at the recorder boundary
in `record/chart.py` (via `utils._normalize_data`). So the JSON layer is
data-library-neutral by construction — it never imports pandas or
numpy, never grows a branch per data library.

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
*reference* envelopes ($node / $coord / $sectors) that journals and IRs
carry whether or not they ever touch JSON. It lives here because both
halves need it (the render tree's hydrator and the front half's facet
expansion) and it resolves only against shared vocabulary.
"""
from __future__ import annotations
from typing import Any

from .utils import DataFrameLite


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
        return [json_hydrate(v) for v in value]
    return value


def _decode(value: Any, nid_to_node: dict) -> Any:
    """Resolve plotlet's *reference* envelopes back to live objects —
    `{"$node"}` via `nid_to_node`, `{"$coord"}` via the coord registry,
    `{"$sectors"}` via `Sectors`. Containers recurse; everything else
    passes through.

    Distinct from `json_hydrate` above: that undoes the JSON-native
    envelopes at the JSON boundary, while these three envelopes live in
    journals and IRs whether or not they ever touch JSON, and decode at
    hydration time. Shared vocabulary — used by the render tree's
    hydrator (`render.hydrate`) and by the facet expansion in
    `record/figure_ir.py`."""
    if isinstance(value, dict):
        if "$node" in value and len(value) == 1:
            return nid_to_node[value["$node"]]
        if "$coord" in value:
            from ._coord_registry import resolve_coord
            cls = resolve_coord(value["$coord"])
            return cls._from_dict(_decode(value.get("kwargs", {}), nid_to_node))
        if "$sectors" in value:
            from .sectors import Sectors
            return Sectors._from_dict(_decode(value["$sectors"], nid_to_node))
        return {k: _decode(v, nid_to_node) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v, nid_to_node) for v in value]
    if isinstance(value, tuple):
        return tuple(_decode(v, nid_to_node) for v in value)
    return value
