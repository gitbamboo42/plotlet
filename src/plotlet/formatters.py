"""Named tick formatters and unicode super/subscript helpers.

Pass a formatter name to `xticks(format=...)` / `yticks(format=...)`:

    c.yticks(format="money")      # "$1.3M", "$250K", "$500"
    c.yticks(format="si")         # "1.3M", "250K", "500"
    c.yticks(format="percent")    # "50%" (value in [0, 1])
    c.yticks(format="scientific") # "1.25e+06"
    c.yticks(format="comma")      # "1,250,000"
    c.yticks(format="power10")    # "10⁵", "2×10⁻³"

Python format specs still work as a fallback for the ~60% of cases they
cover (`"{:.2f}"`, `"{:,}"`, `"{:.0%}"`); the named set fills the gap
for K/M compaction and currency, which Python's spec can't express.

Users add their own via `pt.register_formatter("kilos", fn)`. Names are
plain strings, so anything using `format=<name>` round-trips through
`pt.to_json` / `pt.from_json` with no callable-serialization required.

Math-ish text (exponents, chemical formulas) rides on unicode
super/subscript characters, which the bundled fonts fully cover —
`superscript()` / `subscript()` convert plain strings so callers don't
have to hunt for codepoints (`"kg·m" + pt.superscript("-2")`). This is
deliberate: with text-as-paths there is no markup layer to pass
`<tspan>`-style baseline shifts through, and the unicode glyphs carry
their own optically-corrected shapes.
"""
from __future__ import annotations

import math
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


# --- Unicode super/subscripts -------------------------------------------------

# Superscript 1/2/3 are the Latin-1 codepoints (U+00B9/00B2/00B3) — the
# U+207x slots for them are unassigned in Unicode and render as tofu.
_SUPERSCRIPTS = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³",
    "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷",
    "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "−": "⁻",
    "=": "⁼", "(": "⁽", ")": "⁾",
    "i": "ⁱ", "n": "ⁿ",
}

_SUBSCRIPTS = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃",
    "4": "₄", "5": "₅", "6": "₆", "7": "₇",
    "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "−": "₋",
    "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "o": "ₒ", "x": "ₓ",
    "h": "ₕ", "k": "ₖ", "l": "ₗ", "m": "ₘ",
    "n": "ₙ", "p": "ₚ", "s": "ₛ", "t": "ₜ",
}


def _convert(s, table, kind):
    out = []
    for ch in str(s):
        if ch not in table:
            raise ValueError(
                f"{kind}({s!r}) — no unicode {kind} for {ch!r}. "
                f"Supported: {''.join(sorted(set(table) - {chr(0x2212)}))}"
            )
        out.append(table[ch])
    return "".join(out)


def superscript(s) -> str:
    """`"−2"` → `"⁻²"` — unicode superscript form of a plain string.

    Covers digits, `+ - = ( )`, and `i n`; anything else raises. Use for
    exponents in labels: `c.ylabel("flux (kg·m" + pt.superscript("-2") + ")")`.
    """
    return _convert(s, _SUPERSCRIPTS, "superscript")


def subscript(s) -> str:
    """`"2"` → `"₂"` — unicode subscript form of a plain string.

    Covers digits, `+ - = ( )`, and `a e h k l m n o p s t x`; anything
    else raises. Use for formulas: `"H" + pt.subscript("2") + "O"`.
    """
    return _convert(s, _SUBSCRIPTS, "subscript")


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


def _power10(v):
    """Power-of-ten tick text: `100000` → `"10⁵"`, `0.002` → `"2×10⁻³"`.

    The natural log-axis format (`c.xticks(format="power10")`). Decade
    values render as a bare power; anything else as `mantissa×10ⁿ` with
    the mantissa in [1, 10). Zero stays `"0"` so a symlog-style axis
    doesn't explode."""
    if v == 0:
        return "0"
    sign = "-" if v < 0 else ""
    a = abs(v)
    exp = math.floor(math.log10(a) + 0.5)          # nearest decade first
    if math.isclose(a, 10.0 ** exp, rel_tol=1e-9):
        return f"{sign}10{superscript(str(exp))}"
    exp = math.floor(math.log10(a))
    mant = a / 10.0 ** exp
    return f"{sign}{mant:g}×10{superscript(str(exp))}"


register_formatter("money", _money)
register_formatter("si", _si)
register_formatter("scientific", _scientific)
register_formatter("percent", _percent)
register_formatter("comma", _comma)
register_formatter("power10", _power10)
