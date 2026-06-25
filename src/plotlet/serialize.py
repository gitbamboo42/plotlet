"""JSON serialization of plotlet charts and layouts.

A `Chart` or `Layout` is a recorded journal: `_calls` holds every
artist / frame / state-method call, and a `Layout`'s `_children` holds
the compose tree. Both are append-only since Phase 1, which makes the
in-memory model JSON-able with a small surface.

Format (version 1):

    {
        "version": 1,
        "root": "n0",
        "nodes": [
            {"id": "n0", "type": "chart", ...},
            {"id": "n1", "type": "layout", ...}
        ]
    }

A chart node carries the construction-time state that isn't journaled
(`data_width`, `data_height`, `data`, `aes`, `leaf_kind`, `margin`) and
its `calls` list. A layout node carries `kind`, `children` (refs into
the node table), optional `grid_rows`/`grid_cols`, and its own `calls`.

Value envelopes used inside `data`, `aes`, and `calls`:

    {"$ref":       "n0"}                    Chart / Layout reference
    {"$ndarray":   [...], "dtype": "...",
                          "shape": [...]}    numpy array
    {"$dataframe": {"columns": [...],
                    "data": [...],
                    "dtypes": [...]}}        pandas DataFrame
    {"$coord":     "ClassName",
                          "kwargs": {...}}   Coordinate (Linear, Circular, …)

Primitives, lists/tuples, and dicts pass through directly (tuples come
back as lists — JSON has no tuple type, and plotlet's recorded args
treat them interchangeably).

Coords register via `register_coord_codec(cls)` — the class must expose
`_to_dict() -> dict` and `_from_dict(dict) -> cls`. Encoded kwargs are
recursed into, so a coord that holds a Chart (e.g.
`CircularCoordinate(inner=...)`) round-trips with the inner Chart as a
`$ref` like any other cross-node reference.

Palette objects and `Sectors` objects raise `TypeError` until a codec is
added; pass dict forms for now.
"""
from __future__ import annotations
from typing import Any


_VERSION = 1

# Coord class registry. Populated by `register_coord_codec`; default
# entries (LinearCoordinate, CircularCoordinate) registered at the
# bottom of the module after the class import.
_COORD_REGISTRY: dict[str, type] = {}


def register_coord_codec(cls: type) -> type:
    """Register `cls` as a serializable coord. The class must define
    `_to_dict(self) -> dict` and `_from_dict(cls, dict) -> cls`. Returns
    `cls` so this can be used as a decorator."""
    if not hasattr(cls, "_to_dict") or not hasattr(cls, "_from_dict"):
        raise TypeError(
            f"register_coord_codec: {cls.__name__} must define "
            f"`_to_dict` and `_from_dict`."
        )
    _COORD_REGISTRY[cls.__name__] = cls
    return cls


def to_json(node) -> dict:
    """Serialize a Chart or Layout (and everything reachable from it) to
    a JSON-compatible dict. Use `json.dumps(...)` for the string form."""
    ids: dict[int, str] = {}
    ordered: list = []

    def _collect_refs(value):
        # Recursively walk a value, calling `_collect` on every Chart or
        # Layout encountered. Used so coord objects carrying an `inner=`
        # Chart (and any future ref-bearing codec) get their references
        # collected before encoding tries to write a `$ref`.
        if value is None or isinstance(value, (bool, int, float, str)):
            return
        if isinstance(value, (list, tuple)):
            for v in value:
                _collect_refs(v)
            return
        if isinstance(value, dict):
            for v in value.values():
                _collect_refs(v)
            return
        if hasattr(value, "_is_parent"):
            _collect(value)
            return
        if type(value).__name__ in _COORD_REGISTRY:
            for v in value._to_dict().values():
                _collect_refs(v)

    def _collect(n):
        if id(n) in ids:
            return
        ids[id(n)] = f"n{len(ids)}"
        ordered.append(n)
        if n._is_parent:
            for child in n._children:
                if child is not None:
                    _collect(child)
            # Layout calls can carry coord objects whose own state
            # references other Charts (e.g. CircularCoordinate.inner).
            # Layout journal args are small config values, not data
            # arrays, so the recursive walk is cheap.
            for _name, args, kw in n._calls:
                for a in args:
                    _collect_refs(a)
                for v in kw.values():
                    _collect_refs(v)
        else:
            # Charts can reference other charts via `attach_*` entries in
            # their journal — collect those too so refs resolve.
            for name, args, _kw in n._calls:
                if name.startswith("attach_"):
                    for c in args:
                        _collect(c)

    _collect(node)

    def _encode(value):
        # bool is a subclass of int, so check it before the numeric branch.
        if value is None or isinstance(value, (bool, str)):
            return value
        if isinstance(value, (int, float)):
            return value
        if id(value) in ids:
            return {"$ref": ids[id(value)]}
        if isinstance(value, (list, tuple)):
            return [_encode(v) for v in value]
        if isinstance(value, dict):
            return {str(k): _encode(v) for k, v in value.items()}
        try:
            import numpy as np
        except ImportError:
            np = None
        if np is not None and isinstance(value, np.ndarray):
            return {"$ndarray": value.tolist(),
                    "dtype": str(value.dtype),
                    "shape": list(value.shape)}
        try:
            import pandas as pd
        except ImportError:
            pd = None
        if pd is not None and isinstance(value, pd.DataFrame):
            return {"$dataframe": {
                "columns": [str(c) for c in value.columns],
                "data": [list(row) for row in value.itertuples(index=False, name=None)],
                "dtypes": [str(value[c].dtype) for c in value.columns],
            }}
        cls_name = type(value).__name__
        if cls_name in _COORD_REGISTRY:
            return {"$coord": cls_name,
                    "kwargs": _encode(value._to_dict())}
        raise TypeError(
            f"to_json: don't know how to encode {type(value).__name__} "
            f"value {value!r}. Pass a JSON-native form (list/dict of "
            f"primitives), a numpy array, a DataFrame, or a Chart/Layout."
        )

    def _encode_calls(calls):
        return [
            [name, [_encode(a) for a in args],
             {str(k): _encode(v) for k, v in kw.items()}]
            for name, args, kw in calls
        ]

    def _encode_node(n):
        out: dict = {"id": ids[id(n)]}
        if n._is_parent:
            out["type"] = "layout"
            out["kind"] = n._layout_kind
            if n._grid_rows is not None:
                out["grid_rows"] = n._grid_rows
                out["grid_cols"] = n._grid_cols
            out["children"] = [
                None if c is None else {"$ref": ids[id(c)]}
                for c in n._children
            ]
        else:
            out["type"] = "chart"
            out["leaf_kind"] = n._leaf_kind
            if n._leaf_kind == "data":
                # Use `_orig_data_*` — share-scaling may have mutated
                # `_data_*` during a prior render. The orig fields are
                # the user's original request and reset target.
                out["data_width"] = n._orig_data_width
                out["data_height"] = n._orig_data_height
            else:
                out["canvas_width"] = n._canvas_width
                out["canvas_height"] = n._canvas_height
            if n._data is not None:
                out["data"] = _encode(n._data)
            aes_set = {k: v for k, v in n._aes.items() if v is not None}
            if aes_set:
                out["aes"] = _encode(aes_set)
            out["margin"] = dict(n._margin)
        out["calls"] = _encode_calls(n._calls)
        return out

    return {
        "version": _VERSION,
        "root": ids[id(node)],
        "nodes": [_encode_node(n) for n in ordered],
    }


def from_json(blob: dict):
    """Reconstruct a Chart or Layout from the dict produced by
    `to_json`. The returned root renders to the same SVG as the
    original (up to any unserialized state like coord objects, which
    are out of scope for stage 2)."""
    from .chart import Chart, Layout

    version = blob.get("version")
    if version != _VERSION:
        raise ValueError(
            f"from_json: unsupported version {version!r}, expected {_VERSION}."
        )

    nodes_by_id: dict[str, Any] = {}

    # Pass 1: build empty shells per node. We can't decode values yet
    # because they may carry `$ref`s into nodes constructed later.
    for raw in blob["nodes"]:
        nid = raw["id"]
        if raw["type"] == "chart":
            if raw["leaf_kind"] == "data":
                node = Chart(
                    data=None,
                    data_width=raw["data_width"],
                    data_height=raw["data_height"],
                    margin=raw.get("margin"),
                )
            else:
                node = Chart._new_sized_leaf(
                    canvas_width=raw["canvas_width"],
                    canvas_height=raw["canvas_height"],
                    leaf_kind=raw["leaf_kind"],
                    margin=raw.get("margin"),
                )
        elif raw["type"] == "layout":
            # Pass empty children — wired in pass 2.
            node = Layout(raw["kind"], [])
            if raw.get("grid_rows") is not None:
                node._grid_rows = raw["grid_rows"]
                node._grid_cols = raw["grid_cols"]
        else:
            raise ValueError(f"from_json: unknown node type {raw['type']!r}")
        nodes_by_id[nid] = node

    def _decode(value):
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, list):
            return [_decode(v) for v in value]
        if isinstance(value, dict):
            if "$ref" in value:
                return nodes_by_id[value["$ref"]]
            if "$ndarray" in value:
                import numpy as np
                arr = np.array(value["$ndarray"], dtype=value["dtype"])
                return arr.reshape(value["shape"])
            if "$dataframe" in value:
                import pandas as pd
                d = value["$dataframe"]
                df = pd.DataFrame(d["data"], columns=d["columns"])
                dtypes = d.get("dtypes")
                if dtypes is not None:
                    for col, dt in zip(d["columns"], dtypes):
                        df[col] = df[col].astype(dt)
                return df
            if "$coord" in value:
                cls = _COORD_REGISTRY.get(value["$coord"])
                if cls is None:
                    raise ValueError(
                        f"from_json: unknown coord class {value['$coord']!r}. "
                        f"Use `register_coord_codec` to register it."
                    )
                return cls._from_dict(_decode(value.get("kwargs", {})))
            return {k: _decode(v) for k, v in value.items()}
        raise TypeError(f"from_json: unexpected value {value!r}")

    # Pass 2: decode args/kwargs, populate `_calls`, wire layout children.
    # The Chart constructor recorded entries (from convenience kwargs like
    # data_width-via-init) get overwritten — the JSON is the truth.
    for raw in blob["nodes"]:
        node = nodes_by_id[raw["id"]]
        node._calls = [
            (name, [_decode(a) for a in args],
             {k: _decode(v) for k, v in kw.items()})
            for name, args, kw in raw["calls"]
        ]
        if raw["type"] == "chart":
            data_raw = raw.get("data")
            node._data = _decode(data_raw) if data_raw is not None else None
            for k, v in _decode(raw.get("aes", {})).items():
                node._aes[k] = v
        else:
            children = [
                None if c is None else nodes_by_id[c["$ref"]]
                for c in raw["children"]
            ]
            node._children = children
            for child in children:
                if child is not None:
                    child._parent = node

    return nodes_by_id[blob["root"]]


# Register the coords that ship with plotlet. New coord classes can call
# `register_coord_codec(cls)` themselves at definition site.
from .coordinates import LinearCoordinate, CircularCoordinate
register_coord_codec(LinearCoordinate)
register_coord_codec(CircularCoordinate)
