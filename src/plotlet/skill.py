"""AI onboarding guides, shipped inside the package.

`pt.skill()` prints the users guide so an AI assistant can read it
straight from the installed package — no repo clone, no copy-paste.
"""

from pathlib import Path

_GUIDES = {
    "user": "users.md",
    "developer": "developers.md",
    "json": "json.md",
}


def skill(which="user"):
    """Print an AI onboarding guide for plotlet.

    Parameters
    ----------
    which : str
        ``"user"`` (default) — for AI assistants *writing plotlet code*:
        mental model, script style, sizing, where the shipped examples
        live, machine-readable debugging.
        ``"developer"`` — for AI assistants *working on plotlet itself*:
        architecture, policies, test workflow (assumes a repo clone).
        ``"json"`` — for AI assistants and tools *authoring a plot as a
        JSON journal* (no code execution): the blob format, its rules,
        and where the shipped JSON examples live.

    Typical use: tell your AI assistant "run ``pt.skill()`` and follow
    it" at the start of a session, or "save the output of ``pt.skill()``
    as a persistent skill" to make it stick across sessions.
    """
    try:
        name = _GUIDES[which]
    except KeyError:
        options = ", ".join(repr(k) for k in _GUIDES)
        raise ValueError(f"unknown guide {which!r}; expected one of {options}") from None
    print((Path(__file__).parent / "skills" / name).read_text(encoding="utf-8"))
