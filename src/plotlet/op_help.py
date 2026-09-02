"""`pt.op_help` — per-op reference for journal authors, as a string.

A journal entry's op is the Python method name verbatim, and its kwargs
are that method's kwargs (see `skills/json.md`), so every op's
reference — parameter list plus docstring — already exists on the
Python side. This module serves it keyed by the op string: no chart
object, no interactive session, and the text is returned rather than
printed. That is the shape a service needs: an MCP server that lets a
model author journal JSON exposes `op_help` as its doc-lookup tool,
and the model pulls an op's kwarg vocabulary on demand instead of
guessing it.

Everything is derived live — artist entries from the registry
(extensions included, once imported) and parameter lists from the same
functions that validate the op at replay — so the reference cannot
drift from what a render accepts.
"""
from __future__ import annotations

import inspect
import textwrap

from .record.chart import Chart, Layout, _FRAME_DOCS, chart as _chart_factory
from .record.facet import facet as _facet_factory
from .record.legend import legend as _legend_factory
from .registry import artist_table, get_artist

# Journal op → its `_record_*` handler in render/_resolution.py, whose
# explicit signature is the op's validated parameter list (see
# `_replay`'s docstring). Only the ops dispatched through
# `Chart.__getattr__`; the rest are real Chart methods, inspected
# directly.
_FRAME_HANDLERS = {
    "title": "_record_text_field", "subtitle": "_record_text_field",
    "caption": "_record_text_field", "xlabel": "_record_text_field",
    "ylabel": "_record_text_field",
    "xlim": "_record_lim", "ylim": "_record_lim",
    "xscale": "_record_scale", "yscale": "_record_scale",
    "xticks": "_record_ticks", "yticks": "_record_ticks",
    "x_expand": "_record_expand", "y_expand": "_record_expand",
    "spines": "_record_spines", "gridlines": "_record_gridlines",
    "clip": "_record_clip", "facecolor": "_record_facecolor",
    "aspect": "_record_aspect", "coordinate": "_record_coordinate",
    "sectors": "_record_sectors",
}

# Ops that are real methods on Chart / Layout — served straight off the
# method (signature minus `self`, plus its docstring). Explicit lists,
# not dir() scans: only recordable ops belong here.
_CHART_METHOD_OPS = ("legend", "theme", "spec", "attach_left",
                     "attach_right", "attach_above", "attach_below")
_LAYOUT_OPS = ("share_x", "share_y", "align_x", "align_y", "gap",
               "heights", "title", "theme", "spec", "coordinate",
               "sectors")

_NODE_OPS = ("new_chart", "new_layout", "new_leaf", "new_facet_grid",
             "_inset_add")

# Leading params that belong to the dispatcher, not the caller: `self`
# on methods; `state` and the op-binding args on `_record_*` handlers.
_BINDING_PARAMS = {"self", "state", "key", "axis", "from_default"}

_UNSET_NOTE = ("UNSET marks a kwarg with no fixed default — omit the key "
               "unless setting a value.")


def _sig(fn, *, drop_var_kw: bool = False) -> inspect.Signature:
    params = list(inspect.signature(fn).parameters.values())
    while params and params[0].name in _BINDING_PARAMS:
        params.pop(0)
    if drop_var_kw:
        params = [p for p in params
                  if p.kind is not inspect.Parameter.VAR_KEYWORD]
    # Drop annotations: `from __future__ import annotations` turns them
    # into quoted strings, and a journal caller passes JSON values —
    # the prose carries the types.
    params = [p.replace(annotation=inspect.Parameter.empty) for p in params]
    return inspect.Signature(params)


def _sig_block(op: str, fn, *, drop_var_kw: bool = False) -> str:
    """The op's parameter list, wrapped, plus the UNSET note when the
    sentinel appears in it."""
    text = textwrap.fill(f"{op}{_sig(fn, drop_var_kw=drop_var_kw)}",
                         width=76, initial_indent="  ",
                         subsequent_indent="      ")
    if "UNSET" in text:
        text += "\n  " + _UNSET_NOTE
    return text


def _doc(obj) -> str:
    return inspect.cleandoc(obj.__doc__ or "")


def _fill(text: str) -> str:
    return textwrap.fill(text, width=76)


def _artist_notes(op: str, spec) -> str:
    if spec.data_input == "table":
        return (
            'Journal form — one entry targeting a chart nid:\n'
            '  {"op": "' + op + '", "nid": N, "kwargs": {...}}\n'
            '- A column reference belongs inside the "aes" kwarg: '
            'aes(x="col", ...)\n'
            '  in the examples below is {"aes": {"x": "col", ...}} in '
            'the entry.\n'
            '  The same name as a bare top-level kwarg is a literal value '
            '(a color, a\n'
            '  number, a vector of values) — never a column name.\n'
            '- Omit "aes" and "data" to inherit the chart\'s '
            '(journal-lite); a\n'
            '  present "aes" is complete. pt.to_json spells both out '
            'explicitly.\n'
            '  Tables sit in the blob\'s data section, referenced as '
            '{"data":\n'
            '  {"$data": "d1"}}.\n'
            '- Omit a kwarg to get its default.'
        )
    if spec.data_input == "matrix":
        return (
            'Journal form — one entry targeting a chart nid:\n'
            '  {"op": "' + op + '", "nid": N, '
            '"args": [{"$data": "d1"}], "kwargs": {...}}\n'
            '- This artist reads a matrix, not a table: the first '
            'positional arg is a\n'
            '  {"$data": id} reference into the data section (nested row '
            'lists).\n'
            '- Omit a kwarg to get its default.'
        )
    return (
        'Journal form — one entry targeting a chart nid:\n'
        '  {"op": "' + op + '", "nid": N, "args": [...], "kwargs": {...}}\n'
        '- This artist reads no table — args / kwargs are plain settings, '
        'passed as\n'
        '  JSON values.\n'
        '- Omit a kwarg to get its default.'
    )


def _artist_section(op: str, spec) -> str:
    origin = next((r["origin"] for r in artist_table()
                   if r["name"] == spec.name), "user")
    mod = inspect.getmodule(spec.record)
    doc = inspect.cleandoc((mod.__doc__ if mod is not None else None) or "")
    return "\n\n".join([
        f"{op} — artist op on a chart node [{origin}]",
        _sig_block(op, spec.record),
        _artist_notes(op, spec),
        doc,
    ])


def _chart_section(op: str) -> str:
    method = getattr(Chart, op, None)
    if method is not None:
        # legend / theme / spec / attach_* — real methods that shadow
        # `__getattr__`; their own docstrings are the reference.
        return "\n\n".join([
            f"{op} — op on a chart node",
            _sig_block(op, method),
            _doc(method),
        ])
    # Lazy on purpose: the parameter lists live on the render half's
    # `_record_*` handlers, and the render half loads on demand (the
    # recording half must not pull it in — docs/ARCHITECTURE.md).
    from .render import _resolution
    handler = getattr(_resolution, _FRAME_HANDLERS[op])
    return "\n\n".join([
        f"{op} — frame op on a chart node",
        _sig_block(op, handler),
        _fill(_FRAME_DOCS[op]),
    ])


def _layout_section(op: str) -> str:
    method = getattr(Layout, op)
    return "\n\n".join([
        f"{op} — op on a layout node",
        _sig_block(op, method),
        _doc(method),
    ])


def _node_section(op: str) -> str:
    if op == "new_chart":
        return "\n\n".join([
            "new_chart — creates a chart node",
            _sig_block("new_chart", Chart.__init__, drop_var_kw=True),
            'Every kwarg is optional. "data" is {"$data": id} into the '
            "blob's data\n"
            'section (or None); "aes" is the chart-level column '
            "mapping and x / y /\n"
            "fill / color / group / linestyle / palette are literal "
            "aesthetic defaults —\n"
            "what an artist entry without its own \"aes\" inherits "
            "(journal-lite;\n"
            "pt.to_json writes every entry out explicitly instead). "
            "data_width /\n"
            "data_height (pixels) and margin default sensibly when "
            "omitted; pt.to_json\n"
            "always writes them. Frame state (title, xlim, gridlines, "
            "...) is never a\n"
            "new_chart kwarg — each is its own entry targeting this nid.",
        ])
    if op == "new_layout":
        return (
            "new_layout — creates a composition node\n\n"
            "Kwargs:\n"
            '  layout_kind   "h" | "v" | "grid"\n'
            "  children      list of child nids — bare ints, None for an "
            "empty grid\n"
            '                cell; not {"$node": ...} envelopes\n'
            '  grid_rows, grid_cols   grid shape ("grid" only)\n\n'
            "Each child's new_* entry comes before this one. Layout state "
            "(share_x,\n"
            "gap, title, ...) is separate entries targeting this nid; "
            "root_nid points\n"
            "here for a multi-panel figure."
        )
    if op == "new_leaf":
        return "\n\n".join([
            "new_leaf — creates a non-data leaf (usually a legend panel)",
            'Kwargs: leaf_kind ("legend" or "diagram"), canvas_width, '
            "canvas_height,\n"
            "margin — plus, for a legend, the pt.legend(...) state:\n"
            "  legend_sources      bare chart nids to harvest entries "
            "from ([] =\n"
            "                      every leaf in the parent layout)\n"
            '  legend_names_pairs  [[{"$node": nid}, header], ...] '
            "section-header\n"
            "                      overrides (null header hides it)\n"
            "  legend_group_by_chart, legend_valign, legend_ncols, "
            "legend_reverse,\n"
            "  legend_manual (the entries= list), legend_user_width, "
            "legend_user_height,\n"
            "  legend_gap\n"
            "Place the leaf as a layout child. See "
            "examples/json/07_annotated_heatmap.json.",
            "The knobs mean what pt.legend's parameters mean:",
            _doc(_legend_factory),
        ])
    if op == "new_facet_grid":
        return "\n\n".join([
            "new_facet_grid — creates a facet-recorder node",
            'Kwargs: data ({"$data": id}), by, row, col, col_wrap, '
            "share_x, share_y,\n"
            "chart_opts (dict of pt.chart kwargs applied to every "
            "panel). Artist and\n"
            "frame entries then target this nid and apply to every "
            "panel; a mapped\n"
            'aes rides in such an entry\'s args as an {"$aes": {...}} '
            "envelope. The\n"
            "node expands to a grid of charts when the journal lowers "
            "to the IR.",
            _doc(_facet_factory),
        ])
    # _inset_add
    return "\n\n".join([
        "_inset_add — binds an already-created chart as an inset",
        "Synthesized by to_journal from chart.inset(...); kwargs: rect "
        "([x, y, w, h]\n"
        "in axes-fraction units of the host's data area, origin "
        "bottom-left) and\n"
        "inset_nid (bare int — the inset chart's new_chart entry comes "
        "first).",
        _doc(Chart.inset),
    ])


def _artist_index_lines() -> list[str]:
    lines = []
    for row in artist_table():
        spec = get_artist(row["name"])
        mod = inspect.getmodule(spec.record)
        first = ((mod.__doc__ if mod is not None else None) or "")
        first = first.strip().splitlines()[0] if first.strip() else ""
        lines.append(f"  add_{row['name']:<18} {first} [{row['origin']}]")
    return lines


def _op_list(names) -> str:
    return textwrap.fill(", ".join(names), width=76,
                         initial_indent="  ", subsequent_indent="  ")


def _index() -> str:
    frame_ops = list(_FRAME_DOCS) + ["attach_left", "attach_right",
                                     "attach_above", "attach_below"]
    return "\n".join([
        "plotlet journal op vocabulary — op_help(op) returns one op's "
        "reference.",
        'Blob format and authoring rules: pt.skill("json").',
        "",
        "Node-creating ops (every other op targets an existing nid):",
        "  new_chart       a data chart (data, aes, sizing, "
        "aesthetic defaults)",
        '  new_layout      a composition — "h" / "v" / "grid"; '
        "children = bare nids",
        "  new_leaf        a legend (or diagram) leaf",
        "  new_facet_grid  a facet recorder — expands to a grid of "
        "charts at render",
        "  _inset_add      bind a chart as an inset of another",
        "",
        "Frame ops on a chart nid:",
        _op_list(frame_ops),
        "",
        "Ops on a layout nid:",
        _op_list(_LAYOUT_OPS),
        "",
        "Artist ops on a chart nid:",
        *_artist_index_lines(),
        "  (an extension artist registers on import — "
        "import plotlet.extensions.<name>)",
    ])


def _all_ops() -> list[str]:
    return (list(_NODE_OPS) + list(_FRAME_DOCS) + list(_CHART_METHOD_OPS)
            + list(_LAYOUT_OPS)
            + [f"add_{r['name']}" for r in artist_table()])


def op_help(op: str | None = None) -> str:
    """Return the reference for one journal op — or, with no argument,
    the index of every op currently registered.

    `op` is the op name exactly as a journal entry carries it:
    `"add_bar"`, `"title"`, `"share_x"`, `"new_chart"`, ... The
    reference is the op's parameter list (derived from the same
    function that validates it at replay) plus its docstring — for an
    artist, the same text `help(c.add_bar)` shows, prefixed with how
    the entry is spelled in a journal. An op that exists on both chart
    and layout nodes (`title`, `theme`, `spec`, `coordinate`,
    `sectors`) returns both sections.

    Returns the text (never prints); raises ValueError for an unknown
    op, naming the closest matches. Built for services that can't run
    `help()`: an MCP server exposing journal authoring backs its
    doc-lookup tool with this one call. See `pt.skill("json")`.
    """
    if op is None:
        return _index()
    sections = []
    if op.startswith("add_"):
        spec = get_artist(op[4:])
        if spec is not None:
            sections.append(_artist_section(op, spec))
    if op in _NODE_OPS:
        sections.append(_node_section(op))
    if op in _FRAME_DOCS or op in _CHART_METHOD_OPS:
        sections.append(_chart_section(op))
    if op in _LAYOUT_OPS:
        sections.append(_layout_section(op))
    if not sections:
        import difflib
        close = difflib.get_close_matches(op, _all_ops(), n=3)
        hint = f" Closest: {', '.join(close)}." if close else ""
        raise ValueError(
            f"op_help: unknown op {op!r}.{hint} op_help() lists the "
            "vocabulary; an extension artist's op only exists once its "
            "module is imported (import plotlet.extensions.<name>)."
        )
    return "\n\n".join(sections)
