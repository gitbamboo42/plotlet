"""JSON layer for Journal.

Envelopes numpy / pandas values so a Journal can be dumped through
`json.dumps` and rehydrated. Kept out of `_journal.py` so the journal
core has no coupling to any specific data library — the journal is
an event log; pandas / numpy support is a JSON concern.
"""
from __future__ import annotations
from typing import Any


def json_safe(value: Any) -> Any:
    """Walk `value`, replace numpy arrays and pandas DataFrames with
    JSON-native envelopes. Plotlet envelopes ($node / $coord / $sectors)
    are pre-existing dicts and pass through unchanged (their inner
    values still get recursed)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
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
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def json_hydrate(value: Any) -> Any:
    """Inverse of `json_safe`. Plotlet envelopes are left alone — the
    journal's own `_decode` handles them at replay time."""
    if isinstance(value, dict):
        if "$ndarray" in value:
            import numpy as np
            arr = np.array(value["$ndarray"], dtype=value["dtype"])
            return arr.reshape(value["shape"])
        if "$dataframe" in value:
            import pandas as pd
            d = value["$dataframe"]
            df = pd.DataFrame(d["data"], columns=d["columns"])
            for col, dt in zip(d["columns"], d.get("dtypes", [])):
                df[col] = df[col].astype(dt)
            return df
        return {k: json_hydrate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_hydrate(v) for v in value]
    return value
