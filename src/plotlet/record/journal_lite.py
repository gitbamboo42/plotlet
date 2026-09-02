"""journal-lite — the terse authoring form of the journal.

Same expressive power as the canonical journal, fewer keystrokes:
everything derivable may be omitted, and `expand` fills it back in.
The canonical journal (what `to_json` emits, `from_json` loads) is
untouched by this module — lite is a pure pre-pass in front of it,
one more inspectable seam: lite → journal → IR → SVG. "Lite" means
terser, not weaker.

The authoring rules (taught in skills/json.md):

1. `args` / `kwargs` on an entry default to empty.
2. Any omitted kwarg means the op's default (`pt.op_help(op)` names
   them) — `new_chart` sizing and margin included.
3. An artist entry with no `aes` inherits the chart's (filtered
   to kwargs the artist accepts), plus the chart's literal aesthetic
   defaults and its `data`. A present `aes` is taken as complete
   — no per-key merging — and `"inherit_aes": false` opts out of all
   of it. (This is the one deliberate divergence from the Python
   recorder, which merges per key: an all-or-nothing rule keeps
   `expand` a fixed point on every canonical journal, including
   figures recorded with `inherit_aes=False`, whose opt-out the
   canonical form doesn't carry.)
4. A table may be written inline where a `{"$data": id}` reference
   belongs; expansion interns it into the data section. Inline
   tables must not use `$`-prefixed column names.
5. `root_nid` defaults to the last node created; `version` to 1.
6. Order is semantics and nids are required: a node's `new_*` entry
   precedes any use of its nid.
7. Every canonical journal is a valid lite blob — `expand` is
   idempotent and canonical journals are its fixed points.

`expand` never validates: anything it doesn't understand passes
through unchanged for the journal's own validation to catch at
render. `simplify` is the inverse direction (canonical → lite), used
by `to_json_lite` and the shipped JSON twins; it verifies its own
output round-trips (`expand(simplify(j)) == j`) before returning.
"""
from __future__ import annotations

import json

from .._spec import _MARGIN_FLOOR, _SIZESPEC
from ..registry import op_to_artist
from .journal import Journal, from_journal, to_journal

# Literal aesthetic-default keys a `new_chart` may carry (Chart._aes).
_CHART_AES_KEYS = ("x", "y", "fill", "color", "group", "linestyle",
                   "palette")


def _is_inline_table(value) -> bool:
    """A dict written where a `{"$data": id}` reference belongs, that
    isn't an envelope — i.e. a hand-inlined table."""
    return (isinstance(value, dict) and value
            and not any(isinstance(k, str) and k.startswith("$")
                        for k in value))


def _known_kwargs(spec):
    """The artist's kwarg-name set (None = accepts anything)."""
    return getattr(spec.record, "__kwarg_names__", None)


def _inherit_entry(e: dict, chart_kw: dict, spec) -> None:
    """Fill an artist entry's omitted `aes` / literal aesthetics /
    `data` from its chart's `new_chart` kwargs — the lite rule 3.
    All-or-nothing on purpose (see module docstring); mutates `e`."""
    kw = e["kwargs"]
    if kw.pop("inherit_aes", True) is False:
        return
    known = _known_kwargs(spec)
    if "aes" not in kw:
        mapping = {k: v for k, v in (chart_kw.get("aes") or {}).items()
                   if known is None or k in known}
        if mapping:
            kw["aes"] = mapping
        for k in _CHART_AES_KEYS:
            v = chart_kw.get(k)
            if (v is not None and k not in kw and k not in mapping
                    and (known is None or k in known)):
                kw[k] = v
    # Same condition the recorder uses: the chart's table comes along
    # only when a mapping is in play and the call brought no data of
    # its own (neither `data=` nor a positional).
    if (chart_kw.get("data") is not None and "data" not in kw
            and not e["args"] and kw.get("aes")
            and (known is None or "data" in known)):
        kw["data"] = chart_kw["data"]


def expand(blob: dict) -> dict:
    """Lite journal dict → canonical journal dict. Pure fill-in;
    idempotent; canonical input comes back equal."""
    data = dict(blob.get("data", {}))
    counter = 1

    def intern(value):
        nonlocal counter
        while f"d{counter}" in data:
            counter += 1
        did = f"d{counter}"
        data[did] = value
        return {"$data": did}

    entries = []
    charts: dict = {}       # nid → new_chart kwargs (as expanded)
    last_new_nid = None
    for entry in blob["entries"]:
        e = dict(entry)
        e["args"] = list(e.get("args", []))
        e["kwargs"] = dict(e.get("kwargs", {}))
        if _is_inline_table(e["kwargs"].get("data")):
            e["kwargs"]["data"] = intern(e["kwargs"]["data"])
        spec = op_to_artist(e["op"])
        if spec is not None and e["args"]:
            first = e["args"][0]
            # A matrix artist's bare row lists, or a table artist's
            # inline positional table — both intern in place.
            if ((spec.data_input == "matrix" and type(first) is list)
                    or (spec.data_input == "table"
                        and _is_inline_table(first))):
                e["args"][0] = intern(first)
        if spec is not None and e["nid"] in charts:
            _inherit_entry(e, charts[e["nid"]], spec)
        if e["op"].startswith("new_"):
            last_new_nid = e["nid"]
            if e["op"] == "new_chart":
                # The canonical form always spells the sizing out
                # (`to_journal` writes it) — lite rule 2 makes it
                # omissible, so expansion owns the defaults.
                kw = e["kwargs"]
                kw.setdefault("data_width", _SIZESPEC["data_width"])
                kw.setdefault("data_height", _SIZESPEC["data_height"])
                kw.setdefault("margin", dict(_MARGIN_FLOOR))
                charts[e["nid"]] = kw
        entries.append(e)

    root_nid = blob.get("root_nid")
    return {
        "version": blob.get("version", 1),
        "root_nid": root_nid if root_nid is not None else last_new_nid,
        "entries": entries,
        "data": data,
    }


def _simplify_entry(entry: dict, charts: dict) -> dict:
    """One entry, minus everything `expand` re-derives."""
    e = dict(entry)
    e["args"] = list(e.get("args", []))
    e["kwargs"] = dict(e.get("kwargs", {}))
    if e["op"] == "new_chart":
        kw = e["kwargs"]
        if kw.get("data_width") == _SIZESPEC["data_width"]:
            kw.pop("data_width", None)
        if kw.get("data_height") == _SIZESPEC["data_height"]:
            kw.pop("data_height", None)
        if kw.get("margin") == dict(_MARGIN_FLOOR):
            kw.pop("margin", None)
    spec = op_to_artist(e["op"])
    if spec is not None and e["nid"] in charts:
        # Greedy: drop aes+data / data / aes, keeping the
        # first candidate whose re-inheritance reproduces the entry.
        for drop in (("aes", "data"), ("data",), ("aes",)):
            if not all(k in e["kwargs"] for k in drop):
                continue
            cand = dict(e)
            cand["kwargs"] = {k: v for k, v in e["kwargs"].items()
                              if k not in drop}
            check = dict(cand)
            check["kwargs"] = dict(cand["kwargs"])
            check["args"] = list(cand["args"])
            _inherit_entry(check, charts[e["nid"]], spec)
            if check == e:
                e = cand
                break
    if not e["args"]:
        del e["args"]
    if not e["kwargs"]:
        del e["kwargs"]
    return e


def simplify(blob: dict) -> dict:
    """Canonical journal dict → lite journal dict. Removes only what
    `expand` re-derives, and proves it: raises if the result doesn't
    expand back to the input."""
    charts = {e["nid"]: e.get("kwargs", {})
              for e in blob["entries"] if e["op"] == "new_chart"}
    out = {
        "version": blob["version"],
        "entries": [_simplify_entry(e, charts) for e in blob["entries"]],
    }
    new_nids = [e["nid"] for e in blob["entries"]
                if e["op"].startswith("new_")]
    if not new_nids or blob["root_nid"] != new_nids[-1]:
        out["root_nid"] = blob["root_nid"]
    if blob.get("data"):
        out["data"] = blob["data"]
    if expand(out) != {**blob, "data": blob.get("data", {})}:
        raise RuntimeError(
            "journal_lite.simplify: output does not expand back to its "
            "input — a lite rule and the recorder have drifted apart. "
            "Please report this figure."
        )
    return out


def to_json_lite(node) -> str:
    """Serialize a plot to journal-lite JSON text — the terse authoring
    form of `pt.to_json` (same figure, everything derivable omitted).
    Loads with `pt.from_json_lite`; `pt.to_json` stays the canonical,
    fully explicit record."""
    from .._json_layer import pretty_dumps
    return pretty_dumps(simplify(to_journal(node).to_dict()))


def from_json_lite(blob: str | dict):
    """Load journal-lite JSON (text or parsed dict): `expand` fills
    the omissions, then the blob takes the normal `from_json` path.
    Accepts canonical journals too — expansion is a no-op on them."""
    if isinstance(blob, str):
        blob = json.loads(blob)
    return from_journal(Journal.from_dict(expand(blob)))
