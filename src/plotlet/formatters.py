"""Named tick formatters.

Pass a formatter name to `xticks(format=...)` / `yticks(format=...)`:

    c.yticks(format="money")      # "$1.3M", "$250K", "$500"
    c.yticks(format="si")         # "1.3M", "250K", "500"
    c.yticks(format="percent")    # "50%" (value in [0, 1])
    c.yticks(format="scientific") # "1.25e+06"
    c.yticks(format="comma")      # "1,250,000"

Python format specs still work as a fallback for the ~60% of cases they
cover (`"{:.2f}"`, `"{:,}"`, `"{:.0%}"`); the named set fills the gap
for K/M compaction and currency, which Python's spec can't express.

Users add their own via `pt.register_formatter("kilos", fn)`. Names are
plain strings, so anything using `format=<name>` round-trips through
`pt.to_json` / `pt.from_json` with no callable-serialization required.
"""
from __future__ import annotations
from typing import Callable


_FORMATTERS: dict[str, Callable[[object], str]] = {}


def register_formatter(name: str, fn: Callable[[object], str]) -> None:
    """Register a named tick formatter. `fn(tick_value) -> str`."""
    _FORMATTERS[name] = fn


def get_formatter(name: str) -> Callable[[object], str] | None:
    """Look up a formatter by name, or None if not registered."""
    return _FORMATTERS.get(name)


def list_formatters() -> list[str]:
    """Names of all registered formatters, sorted."""
    return sorted(_FORMATTERS)


# --- Built-ins ---------------------------------------------------------------


def _money(v):
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1_000_000_000: return f"{sign}${a/1_000_000_000:.1f}B"
    if a >= 1_000_000:     return f"{sign}${a/1_000_000:.1f}M"
    if a >= 1_000:         return f"{sign}${a/1_000:.0f}K"
    return f"{sign}${a:.0f}"


def _si(v):
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1_000_000_000: return f"{sign}{a/1_000_000_000:.1f}B"
    if a >= 1_000_000:     return f"{sign}{a/1_000_000:.1f}M"
    if a >= 1_000:         return f"{sign}{a/1_000:.0f}K"
    return f"{sign}{a:.0f}"


def _scientific(v):
    return f"{v:.2e}"


def _percent(v):
    return f"{v*100:.0f}%"


def _comma(v):
    return f"{v:,}"


register_formatter("money", _money)
register_formatter("si", _si)
register_formatter("scientific", _scientific)
register_formatter("percent", _percent)
register_formatter("comma", _comma)
