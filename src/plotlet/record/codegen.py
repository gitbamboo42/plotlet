"""Journal → Python source. The inverse direction of recording.

`to_python` turns any figure (or its journal / JSON form) into a plain
Python script that rebuilds it. The script is a *flattened* view of what
was recorded — loops, helper functions, variable names, and data
provenance from the original session are gone; what remains is one line
per journal event, in house style (data first, bare artists, no
chaining). The contract is exact: running the generated script and
re-journaling gives the same journal, so the same SVG.

Why this exists: the journal's JSON form is the safe interchange format
— an agent or tool can author it without executing any code, and
`from_json(...).to_svg()` renders it through the validated seam. But a
JSON blob is a dead end for a human who wants to tweak the figure.
`to_python` closes the loop: JSON in, editable script out. Generate the
script *from* validated JSON on the trusted side; don't accept scripts
as the interchange format, or the no-code-execution property is gone.

Inheritance is inverted for readability: an artist call whose recorded
mapping/data just restates the chart's is emitted bare. Every such
minimization is verified by re-running the recorder's own inheritance
helper on the emitted form; if it wouldn't reproduce the journal entry
exactly, the generator falls back to the verbatim form
(`inherit_aes=False`, explicit mapping and data). Prettiness never
costs fidelity.

Not reconstructible: diagram leaves (`pt.layout_diagram` output embeds a
pre-rendered SVG whose source figure the journal doesn't carry) — those
raise. Artist ops that don't resolve in the registry raise with the
extension-import hint, same as `render.validate`.
"""
from __future__ import annotations

from .._spec import _MARGIN_FLOOR, _SIZESPEC
from ..registry import op_to_artist
from ..utils import DataFrameLite

import dataclasses
import datetime
import inspect
import json
import keyword
import re

import numpy as np

# Kwargs of `new_chart` that aren't chart-level bare aes defaults.
_CHART_STRUCTURAL = ("data", "data_width", "data_height", "margin", "mapping")

# Journal key → `pt.legend` parameter. The journal stores the leaf's
# post-normalization state, so drop decisions compare against a
# default-constructed legend leaf, not the signature defaults
# (`entries=None` stores `[]`, `gap` stores a float).
_LEGEND_KWARGS = {
    "legend_group_by_chart": "group_by_chart",
    "legend_valign": "valign",
    "legend_ncols": "ncols",
    "legend_reverse": "reverse",
    "legend_manual": "entries",
    "legend_user_width": "canvas_width",
    "legend_user_height": "canvas_height",
    "legend_gap": "gap",
}

_WRAP = 88          # wrap emitted call lines longer than this


def _same(a, b) -> bool:
    """Type-strict equality for drop decisions. Python's `==` says
    `360 == 360.0` and `True == 1`; dropping on that would regenerate
    the default with the *other* type and change the journal's JSON.
    Recurses so container values compare strictly cell by cell."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return (a.keys() == b.keys()
                and all(_same(v, b[k]) for k, v in a.items()))
    if isinstance(a, (list, tuple)):
        return (len(a) == len(b)
                and all(_same(x, y) for x, y in zip(a, b)))
    return a == b


def _canon(kwargs: dict) -> str | None:
    """Canonical JSON of a recorded kwargs dict, for exact comparison —
    `==` on dicts is type-loose (1 == 1.0) and NaN-hostile (nan != nan).
    None when the value doesn't serialize (exotic cells); callers treat
    that as \"not provably equal\"."""
    try:
        return json.dumps(kwargs, sort_keys=True, default=repr)
    except (TypeError, ValueError):
        return None


def to_python(fig, *, var: str = "fig") -> str:
    """Generate a Python script that rebuilds `fig`.

    Accepts a `Chart` / `Layout` / `FacetGrid`, a `Journal`, a
    `JournalNode`, or journal JSON (the `to_json` text or its parsed
    dict). Returns
    source whose final figure is bound to `var` ("fig" by default) —
    `exec` it, or save it and edit like any hand-written plotlet script.

    Round-trip contract: `to_journal` of the rebuilt figure equals the
    input journal, so the rendered SVG is byte-identical.
    """
    from .journal import Journal, JournalNode, to_journal

    if not var.isidentifier() or keyword.iskeyword(var):
        raise ValueError(
            f"to_python: var={var!r} is not a valid Python variable name."
        )
    if isinstance(fig, str):
        fig = json.loads(fig)
    if isinstance(fig, dict):
        journal = Journal.from_dict(fig)
        root_nid = journal.root_nid
    elif isinstance(fig, Journal):
        journal, root_nid = fig, fig.root_nid
    elif isinstance(fig, JournalNode):
        journal, root_nid = fig._journal, fig._root_nid
    else:
        journal = to_journal(fig)
        root_nid = journal.root_nid
    if root_nid is None:
        raise ValueError("to_python: journal has no root_nid.")

    g = _Gen(journal, root_nid, var)
    return g.generate()


class _Gen:
    """One generation pass. State: variable names per nid, the import
    set, and the chart-level aes info needed to invert inheritance."""

    def __init__(self, journal, root_nid: int, root_var: str):
        self.journal = journal
        self.root_nid = root_nid
        self.root_var = root_var
        self.lines: list[str] = []
        self.imports: set[str] = set()
        self.var: dict[int, str] = {}       # nid → variable name
        self.data_var: dict[str, str] = {}  # data id → variable name
        self.used: set[str] = {root_var}    # every allocated name
        self.chart_info: dict[int, dict] = {}   # nid → new_chart kwargs
        self.facet_nids: set[int] = set()
        self.counters = {"c": 0, "g": 0, "leg": 0, "fg": 0}
        # nid → (host_nid, rect) for charts created via `host.inset(...)`
        self.insets = {
            e["kwargs"]["inset_nid"]: (e["nid"], e["kwargs"]["rect"])
            for e in journal.entries if e["op"] == "_inset_add"
        }

    def generate(self) -> str:
        for did, table in self.journal.data.items():
            self._emit_table(did, table)
        for entry in self.journal.entries:
            self._emit_entry(entry)
        header = ["import plotlet as pt", "from plotlet import aes"]
        header += sorted(self.imports)
        return "\n".join(header + [""] + self.lines) + "\n"

    # ---------- naming ----------

    def _name(self, nid: int, prefix: str) -> str:
        if nid == self.root_nid:
            name = self.root_var
        else:
            while True:
                self.counters[prefix] += 1
                name = f"{prefix}{self.counters[prefix]}"
                if name not in self.used:
                    break
            self.used.add(name)
        self.var[nid] = name
        return name

    def _pyname(self, want: str) -> str:
        """Allocate a fresh, valid variable name as close to `want` as
        possible. Journal data ids come from the blob and may not be
        identifiers; `want` may also collide with the root var or a
        name already minted — both would silently rebind."""
        name = re.sub(r"\W", "_", want)
        if not name or name[0].isdigit() or keyword.iskeyword(name):
            name = "_" + name
        base, n = name, 1
        while name in self.used:
            n += 1
            name = f"{base}_{n}"
        self.used.add(name)
        return name

    def _blank(self) -> None:
        """One separating blank line before a create block — never two."""
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def _block(self, head: str, items: list[str], tail: str,
               ind: str = "    ", close_ind: str = "") -> None:
        """Append `head + ", ".join(items) + tail` as one line when it
        fits in _WRAP, else one indented item per line between `head`
        and a closing line. The shared shape behind grid rows, dict
        tables, matrix rows, and DataFrameLite values."""
        one = head + ", ".join(items) + tail
        if len(one) <= _WRAP:
            self.lines.append(one)
            return
        self.lines.append(head)
        for item in items:
            self.lines.append(f"{ind}{item},")
        self.lines.append(close_ind + tail)

    # ---------- entry dispatch ----------

    def _emit_entry(self, entry: dict) -> None:
        op, nid = entry["op"], entry["nid"]
        kw = entry["kwargs"]
        if op == "new_chart":
            self._emit_chart(nid, kw)
        elif op == "new_leaf":
            self._emit_leaf(nid, kw)
        elif op == "new_layout":
            self._emit_layout(nid, kw)
        elif op == "new_facet_grid":
            self._emit_facet(nid, kw)
        elif op == "_inset_add":
            pass    # already emitted at the inset chart's create event
        else:
            self._emit_call(nid, op, entry["args"], kw)

    # ---------- create events ----------

    def _emit_chart(self, nid: int, kw: dict) -> None:
        self.chart_info[nid] = kw
        name = self._name(nid, "c")
        inset = nid in self.insets
        parts = []
        skip = set()
        if inset:
            host_nid, rect = self.insets[nid]
            prefix = f"{name} = {self.var[host_nid]}.inset"
            parts.append(self._fmt(tuple(rect)))
            # Drop data_width / data_height only when `inset()` would
            # re-derive the journaled value from the rect. After `fit()`
            # it wouldn't — host and inset scale with independent
            # rounding — so the dims go through explicitly (`inset()`
            # accepts them as overrides).
            host = self.chart_info[host_nid]
            for k, frac in (("data_width", rect[2]),
                            ("data_height", rect[3])):
                derived = max(1, int(round(host.get(k, _SIZESPEC[k]) * frac)))
                if _same(derived, kw.get(k)):
                    skip.add(k)
        else:
            prefix = f"{name} = pt.chart"
        if kw.get("data") is not None:
            ref = self._fmt(kw["data"])
            parts.append(f"data={ref}" if inset else ref)
        if kw.get("mapping"):
            m = self._fmt_aes(kw["mapping"])
            parts.append(f"mapping={m}" if inset else m)
        for k, v in kw.items():
            if k in ("data", "mapping") or k in skip:
                continue
            if (not inset and k in ("data_width", "data_height")
                    and _same(v, _SIZESPEC[k])):
                continue
            if k == "margin" and _same(v, _MARGIN_FLOOR):
                continue
            parts.append(f"{k}={self._fmt(v)}")
        self._blank()
        self.lines.append(_join(prefix, parts))

    def _emit_leaf(self, nid: int, kw: dict) -> None:
        if kw["leaf_kind"] == "diagram":
            raise ValueError(
                "to_python: diagram leaves (pt.layout_diagram output) embed "
                "a pre-rendered SVG and have no source form."
            )
        from .legend import legend
        unknown = [k for k in kw
                   if k.startswith("legend_") and k not in _LEGEND_KWARGS
                   and k not in ("legend_sources", "legend_names_pairs")]
        if unknown:
            raise ValueError(
                f"to_python: legend journal keys {unknown} have no emitter "
                f"— add them to _LEGEND_KWARGS."
            )
        name = self._name(nid, "leg")
        parts = [self.var[s] for s in kw["legend_sources"]]
        pairs = kw["legend_names_pairs"]
        if pairs:
            items = ", ".join(f"{self._fmt(k)}: {self._fmt(v)}"
                              for k, v in pairs)
            parts.append(f"names={{{items}}}")
        ref = legend()      # journal-side default for every legend key
        for jk, pk in _LEGEND_KWARGS.items():
            v = kw[jk]
            if _same(getattr(ref, f"_{jk}"), v):
                continue
            parts.append(f"{pk}={self._fmt(v)}")
        self._blank()
        self.lines.append(_join(f"{name} = pt.legend", parts))

    def _emit_layout(self, nid: int, kw: dict) -> None:
        name = self._name(nid, "g")
        kind = kw["layout_kind"]
        children = [self.var[c] if c is not None else "None"
                    for c in kw["children"]]
        self._blank()
        if kind == "grid":
            rows, cols = kw["grid_rows"], kw["grid_cols"]
            cells = [children[r * cols:(r + 1) * cols] for r in range(rows)]
            rows_src = ["[" + ", ".join(row) + "]" for row in cells]
            self._block(f"{name} = pt.grid([", rows_src, "])")
        else:
            joiner = " | " if kind == "h" else " / "
            self.lines.append(f"{name} = {joiner.join(children)}")

    def _emit_facet(self, nid: int, kw: dict) -> None:
        from .facet import facet
        name = self._name(nid, "fg")
        self.facet_nids.add(nid)
        parts = [self._fmt(kw["data"])]
        # Journal keys mirror `pt.facet`'s parameters exactly, so the
        # signature drives the drop decisions — a future kwarg is
        # covered (or fails loudly at exec) instead of silently vanishing.
        rest = {k: v for k, v in kw.items() if k not in ("data", "chart_opts")}
        rest = _drop_signature_defaults(facet, rest)
        parts += [f"{k}={self._fmt(v)}" for k, v in rest.items()]
        parts += [f"{k}={self._fmt(v)}" for k, v in kw["chart_opts"].items()]
        self._blank()
        self.lines.append(_join(f"{name} = pt.facet", parts))

    # ---------- method events ----------

    def _emit_call(self, nid: int, op: str, args: list, kw: dict) -> None:
        from .chart import _FRAME_METHODS, Chart, Layout
        target = self.var[nid]

        if nid in self.chart_info:                  # chart node
            spec = op_to_artist(op)
            if spec is not None:
                self._emit_artist(target, nid, op, spec, args, kw)
                return
            if op not in _FRAME_METHODS and not op.startswith("attach_"):
                raise ValueError(
                    f"to_python: op {op!r} does not resolve to a registered "
                    f"artist or frame method. Extension artists register on "
                    f"import — run `import plotlet.extensions.{op}` first."
                )
            method = getattr(Chart, op, None)
        elif nid in self.facet_nids:
            # A FacetGrid records and replays calls verbatim — nothing
            # re-fills a dropped default, so emit the journal exactly.
            method = None
        else:
            # Layout / legend-leaf node.
            method = getattr(Layout, op, None) or getattr(Chart, op, None)

        kw = _drop_signature_defaults(method, kw)
        parts = [self._fmt(a) for a in args]
        parts += [f"{k}={self._fmt(v)}" for k, v in kw.items()]
        self.lines.append(_join(f"{target}.{op}", parts))

    def _emit_artist(self, target, nid, op, spec, args, kw) -> None:
        """Emit an artist call, minimized against chart-level inheritance
        when re-recording the minimized call provably reproduces `kw`."""
        from .chart import _inherit_chart_aes
        info = self.chart_info[nid]
        cmap = info.get("mapping", {}) or {}
        cbare = {k: v for k, v in info.items() if k not in _CHART_STRUCTURAL}
        cdata = info.get("data")
        known = getattr(spec.record, "__kwarg_names__", None)

        def ok(k):
            return known is None or k in known

        A = kw.get("mapping", {}) or {}
        L = {k: v for k, v in kw.items() if k not in ("mapping", "data")}
        data_ref = kw.get("data")

        def simulate(a_emit, l_emit, data_emit, inherit):
            """What the recorder would store for this emitted call —
            computed by the recorder's own inheritance helper, so the
            check can't drift from the real recorder."""
            kwargs = dict(l_emit)
            if data_emit is not None:
                kwargs["data"] = data_emit
            return _inherit_chart_aes(dict(a_emit), kwargs, args,
                                      cmap, cbare, cdata, known, inherit)

        # Minimal candidate: drop mapping entries and literals the chart
        # would re-inject, and the data ref when injection re-adds it.
        a_min = {k: v for k, v in A.items()
                 if not (ok(k) and k in cmap and _same(cmap[k], v))}
        l_min = {k: v for k, v in L.items()
                 if not (ok(k) and k not in cmap
                         and k in cbare and _same(cbare[k], v))}
        recorded = _canon(kw)
        candidates = [(a_min, l_min, None, True),
                      (a_min, l_min, data_ref, True),
                      (A, L, data_ref, False)]
        for a_emit, l_emit, data_emit, inherit in candidates:
            sim = simulate(a_emit, l_emit, data_emit, inherit)
            if (_canon(sim) == recorded if recorded is not None
                    else sim == kw):
                break
        else:
            raise AssertionError(
                f"to_python: could not invert recording for op {op!r} — "
                f"please report this journal."
            )

        parts = [self._fmt(a) for a in args]
        if a_emit:
            parts.append(self._fmt_aes(a_emit))
        parts += [f"{k}={self._fmt(v)}" for k, v in l_emit.items()]
        if data_emit is not None:
            parts.append(f"data={self._fmt(data_emit)}")
        if not inherit:
            parts.append("inherit_aes=False")
        self.lines.append(_join(f"{target}.{op}", parts))

    # ---------- values ----------

    def _fmt_aes(self, m: dict) -> str:
        return "aes(" + ", ".join(f"{k}={self._fmt(v)}"
                                  for k, v in m.items()) + ")"

    def _fmt(self, v) -> str:
        if isinstance(v, dict):
            if "$node" in v and len(v) == 1:
                return self.var[v["$node"]]
            if "$data" in v and len(v) == 1:
                return self.data_var[v["$data"]]
            if "$aes" in v and len(v) == 1:
                return self._fmt_aes(v["$aes"])
            if "$coord" in v:
                return self._fmt_coord(v)
            if "$sectors" in v and len(v) == 1:
                return self._fmt_sectors(v["$sectors"])
            return "{" + ", ".join(f"{self._fmt(k)}: {self._fmt(x)}"
                                   for k, x in v.items()) + "}"
        if isinstance(v, tuple):
            inner = ", ".join(self._fmt(x) for x in v)
            return f"({inner},)" if len(v) == 1 else f"({inner})"
        if isinstance(v, list):
            return "[" + ", ".join(self._fmt(x) for x in v) + "]"
        if isinstance(v, set):
            if not v:
                return "set()"
            return "{" + ", ".join(sorted(self._fmt(x) for x in v)) + "}"
        if isinstance(v, np.generic):
            # Styling kwargs aren't normalized at the recorder boundary,
            # so numpy scalars reach the journal. The generated script
            # imports no numpy — lower to the Python scalar (repr would
            # emit `np.float64(2.5)` and NameError at exec).
            return self._fmt(v.item())
        if isinstance(v, (datetime.date, datetime.datetime)):
            self.imports.add("import datetime")
            return repr(v)      # repr is `datetime.date(2024, 1, 5)` form
        if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
            return f'float("{v}")'   # nan / inf / -inf have no literal form
        return repr(v)

    def _fmt_coord(self, env: dict) -> str:
        from .._coord_registry import resolve_coord
        name = env["$coord"]
        cls = resolve_coord(name)
        try:
            defaults = {
                k: p.default
                for k, p in inspect.signature(cls.__init__).parameters.items()
                if p.default is not inspect.Parameter.empty
            }
        except (TypeError, ValueError):
            defaults = {}
        parts = [f"{k}={self._fmt(v)}" for k, v in env["kwargs"].items()
                 if not (k in defaults and _same(defaults[k], v))]
        import plotlet      # local on purpose: module-level is circular
        prefix = f"pt.{name}" if hasattr(plotlet, name) else name
        return prefix + "(" + ", ".join(parts) + ")"

    def _fmt_sectors(self, d: dict) -> str:
        from ..sectors import Sectors
        s = Sectors._from_dict(d)
        parts = []
        # The dataclass declaration is the roster — a new field shows up
        # here without a hand-kept mirror of its name and default.
        for f in dataclasses.fields(Sectors):
            v = getattr(s, f.name)
            if f.default is not dataclasses.MISSING and _same(f.default, v):
                continue
            parts.append(f"{f.name}={self._fmt(v)}")
        return "pt.Sectors(" + ", ".join(parts) + ")"

    # ---------- data section ----------

    def _emit_table(self, did: str, table) -> None:
        name = self._pyname(did)
        self.data_var[did] = name
        if isinstance(table, np.ndarray):
            table = table.tolist()
        if isinstance(table, DataFrameLite):
            self.imports.add("from plotlet.utils import DataFrameLite")
            self.lines.append(f"{name} = DataFrameLite(")
            self.lines.append(f"    columns={self._fmt(table.columns)},")
            self.lines.append(f"    index={self._fmt(table.index)},")
            self._emit_rows("values", table.values)
            self.lines.append(")")
            return
        if isinstance(table, dict):
            self._block(f"{name} = {{",
                        [f"{self._fmt(k)}: {self._fmt(v)}"
                         for k, v in table.items()],
                        "}")
            return
        # Matrix as nested lists.
        self._block(f"{name} = [", [self._fmt(row) for row in table], "]")

    def _emit_rows(self, key: str, rows: list) -> None:
        self._block(f"    {key}=[", [self._fmt(row) for row in rows], "],",
                    ind="        ", close_ind="    ")


def _drop_signature_defaults(method, kw: dict) -> dict:
    """Drop kwargs the method would record identically on its own —
    i.e. whose value equals the parameter default. Safe by construction:
    re-recording fills the same value back in."""
    if method is None or not kw:
        return kw
    try:
        params = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return kw
    return {k: v for k, v in kw.items()
            if not (k in params
                    and params[k].default is not inspect.Parameter.empty
                    and _same(params[k].default, v))}


def _join(prefix: str, parts: list[str]) -> str:
    """`prefix(part, part, ...)`, wrapped with aligned continuation
    lines when too long."""
    one = prefix + "(" + ", ".join(parts) + ")"
    if len(one) <= _WRAP:
        return one
    ind = " " * (len(prefix) + 1)
    return prefix + "(" + (",\n" + ind).join(parts) + ")"
