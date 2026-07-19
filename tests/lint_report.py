"""Render `tests/lint_report.html` — one row per flagged baseline
fixture using `figure_lint` (edge_clip + exhaustive pairwise overlap).
Hits are warnings, not errors: the report flags candidates for human
review, not test failures.

    python tests/lint_report.py            # writes + opens
    python tests/lint_report.py --no-open  # writes only
"""
from __future__ import annotations
import html
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import plotlet as pt
from plotlet.lint import lint  # noqa: E402

# Every baseline suite exposes a `PLOTS` registry; discover them by scanning
# rather than hand-listing. Skip the modules that re-export a collected
# `PLOTS` from test_journal_roundtrip (they would double-count every chart).
_SKIP = {"test_journal_roundtrip", "test_ir", "test_ir_resolved"}
MODULES = sorted(p.stem for p in HERE.glob("test_*.py") if p.stem not in _SKIP)


def _materialize(c):
    return c._materialize() if hasattr(c, "_materialize") else c


def _diagram_svg(fixture_fn) -> tuple[str, str]:
    """Returns ('ok', svg) or ('error', message)."""
    try:
        chart = _materialize(fixture_fn())
        combined = chart | pt.layout_diagram(chart)
        return "ok", combined.to_svg()
    except Exception as e:
        return "error", f"{type(e).__name__}: {e}"


def main():
    rows = []
    for mod_name in MODULES:
        try:
            mod = __import__(mod_name)
        except Exception:
            continue
        for name, fn in getattr(mod, "PLOTS", {}).items():
            try:
                warnings = lint(fn())
            except Exception as e:
                warnings = []
                err = f"{type(e).__name__}: {e}"
            else:
                err = None
            if not warnings and not err:
                continue
            status, payload = _diagram_svg(fn)
            rows.append({
                "module": mod_name,
                "name": name,
                "warnings": [str(w) for w in warnings],
                "diagram_status": status,
                "diagram_payload": payload,
                "build_error": err,
            })

    rows.sort(key=lambda r: -len(r["warnings"]))

    tally: dict[str, int] = {}
    for r in rows:
        for w in r["warnings"]:
            check = w.split(":", 1)[0]
            tally[check] = tally.get(check, 0) + 1
    tally_html = ", ".join(f"<b>{k}</b>={v}" for k, v in sorted(tally.items()))

    parts = ["""<!doctype html><html><head><meta charset="utf-8">
<title>plotlet figure_lint report</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif;
         max-width: 1500px; margin: 1em auto; padding: 0 1em;
         color: #222; }
  h1 { font-size: 1.4em; margin-bottom: 0.2em; }
  .summary { color: #666; margin-bottom: 1em; }
  .note { color: #888; font-size: 0.9em; margin-bottom: 1em;
          font-style: italic; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #ddd; padding: 0.6em 0.8em;
           vertical-align: top; }
  th { background: #f5f5f5; text-align: left; font-weight: 600; }
  td.fixture { width: 12em; font-size: 0.9em; }
  td.fixture .mod { color: #888; }
  td.fixture .count { font-weight: 600; color: #d97706; }
  td.figure { background: #fafafa; max-width: 900px; }
  td.figure svg { max-width: 100%; height: auto;
                  border: 1px solid #ddd; background: white; }
  td.figure .error { color: #888; font-family: monospace; }
  td.warnings { font-family: ui-monospace, Menlo, monospace;
                font-size: 0.78em; white-space: pre-wrap;
                word-break: break-word; max-width: 450px;
                background: #fffbeb; }
  td.warnings .err { color: #888; font-style: italic; }
</style></head><body>
"""]
    parts.append("<h1>plotlet figure_lint report</h1>")
    parts.append(f'<div class="summary">'
                 f'{len(rows)} fixtures flagged · {tally_html}</div>')
    parts.append('<div class="note">Warnings — not errors. These flag '
                 'candidate layout issues for human review; the figures '
                 'render fine and may be intentional.</div>')
    parts.append('<table><tr><th>Fixture</th><th>chart | layout_diagram</th>'
                 '<th>Warnings</th></tr>')
    for r in rows:
        parts.append("<tr>")
        parts.append(
            f'<td class="fixture">'
            f'<div class="mod">{html.escape(r["module"])}</div>'
            f'<div><b>{html.escape(r["name"])}</b></div>'
            f'<div class="count">{len(r["warnings"])} warnings</div>'
            "</td>"
        )
        if r["diagram_status"] == "ok":
            parts.append(f'<td class="figure">{r["diagram_payload"]}</td>')
        else:
            parts.append(
                f'<td class="figure"><div class="error">'
                f'{html.escape(r["diagram_payload"])}</div></td>'
            )
        warn_text = "\n".join(html.escape(w) for w in r["warnings"])
        if r["build_error"]:
            warn_text = (f'<span class="err">lint failed: '
                         f'{html.escape(r["build_error"])}</span>\n' + warn_text)
        parts.append(f'<td class="warnings">{warn_text}</td>')
        parts.append("</tr>")
    parts.append("</table></body></html>")

    out = HERE / "lint_report.html"
    out.write_text("".join(parts))
    print(f"wrote {out} — {len(rows)} fixtures, "
          f"{sum(tally.values())} total warnings")
    if "--no-open" not in sys.argv:
        webbrowser.open(f"file://{out}")


if __name__ == "__main__":
    main()
