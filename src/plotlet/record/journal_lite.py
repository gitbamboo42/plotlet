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
   them) — `new_chart` sizing and margin, a legend `new_leaf`'s
   canvas and `legend_*` state, and `new_facet_grid`'s `pt.facet`
   parameters included. A `$coord` envelope's `container` flag is
   derived from the registered class, so an author never writes it.
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

import copy
import inspect
import json

from .._spec import _MARGIN_FLOOR, _SIZESPEC
from ..registry import op_to_artist
from ..utils import all_primitive
from .journal import Journal, from_journal, to_journal

# Literal aesthetic-default keys a `new_chart` may carry (Chart._aes).
_CHART_AES_KEYS = ("x", "y", "fill", "color", "group", "linestyle",
                   "palette")


def _legend_leaf_defaults() -> dict:
    """The `new_leaf` kwargs `to_journal` writes for a bare
    `pt.legend()` — the journal's own defaults, so they can't drift
    from the recorder. Only legend leaves have an authoring form
    (a diagram leaf embeds pre-rendered SVG and is never hand-written)."""
    from .legend import legend
    return copy.deepcopy(to_journal(legend()).entries[0]["kwargs"])


def _facet_defaults() -> dict:
    """`new_facet_grid` kwargs mirror `pt.facet`'s parameters, so the
    signature is the default table; `chart_opts` is its **kwargs."""
    from .facet import facet
    out = {p.name: p.default
           for p in inspect.signature(facet).parameters.values()
           if p.default is not inspect.Parameter.empty}
    out["chart_opts"] = {}
    return out


def _coord_container(name: str) -> bool:
    """The `container` flag `to_journal` stamps on a `$coord` envelope
    — a fact about the registered class, re-derived here so a lite
    author never states it. `render.validate` still cross-checks the
    filled flag against the class at render."""
    from .._coord_registry import resolve_coord
    return hasattr(resolve_coord(name), "render_layout")


def _fill_coord_flags(value):
    """Return `value` with every `$coord` envelope in it carrying its
    `container` flag. Pure — nested containers are rebuilt, not
    mutated, so the caller's blob stays untouched."""
    if isinstance(value, dict):
        out = {k: _fill_coord_flags(v) for k, v in value.items()}
        if "$coord" in out and "container" not in out:
            out["container"] = _coord_container(out["$coord"])
        return out
    if isinstance(value, list) and not all_primitive(value):
        return [_fill_coord_flags(v) for v in value]
    return value


def _strip_coord_flags(value):
    """Inverse of `_fill_coord_flags` for `simplify`."""
    if isinstance(value, dict):
        out = {k: _strip_coord_flags(v) for k, v in value.items()
               if not (k == "container" and "$coord" in value)}
        return out
    if isinstance(value, list) and not all_primitive(value):
        return [_strip_coord_flags(v) for v in value]
    return value


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
        e["args"] = _fill_coord_flags(list(e.get("args", [])))
        e["kwargs"] = _fill_coord_flags(dict(e.get("kwargs", {})))
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
            kw = e["kwargs"]
            # The canonical form spells every construction kwarg out
            # (`to_journal` writes them) — lite rule 2 makes them
            # omissible, so expansion owns the defaults.
            if e["op"] == "new_chart":
                kw.setdefault("data_width", _SIZESPEC["data_width"])
                kw.setdefault("data_height", _SIZESPEC["data_height"])
                kw.setdefault("margin", dict(_MARGIN_FLOOR))
                charts[e["nid"]] = kw
            elif e["op"] == "new_leaf" and kw.get("leaf_kind") == "legend":
                for k, v in _legend_leaf_defaults().items():
                    kw.setdefault(k, v)
            elif e["op"] == "new_facet_grid":
                for k, v in _facet_defaults().items():
                    kw.setdefault(k, v)
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
    e["args"] = _strip_coord_flags(list(e.get("args", [])))
    e["kwargs"] = _strip_coord_flags(dict(e.get("kwargs", {})))
    kw = e["kwargs"]
    if e["op"] == "new_chart":
        if kw.get("data_width") == _SIZESPEC["data_width"]:
            kw.pop("data_width", None)
        if kw.get("data_height") == _SIZESPEC["data_height"]:
            kw.pop("data_height", None)
        if kw.get("margin") == dict(_MARGIN_FLOOR):
            kw.pop("margin", None)
    elif e["op"] == "new_leaf" and kw.get("leaf_kind") == "legend":
        for k, v in _legend_leaf_defaults().items():
            if k in kw and kw[k] == v and k != "leaf_kind":
                del kw[k]
    elif e["op"] == "new_facet_grid":
        for k, v in _facet_defaults().items():
            if k in kw and kw[k] == v:
                del kw[k]
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
