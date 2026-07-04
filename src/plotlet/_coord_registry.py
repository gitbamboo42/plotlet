"""Coord codec registry — a neutral home for the `class_name → class` map
that both `serialize.py` and `_journal.py` need for round-tripping coord
objects like `CircularCoordinate`.

Lives here rather than in either consumer so that removing one of them
later (e.g. retiring the JSON tree serializer once the journal covers
the same ground) doesn't leave the registry orphaned. The public API
`plotlet.register_coord_codec` re-exports from this module directly.
"""
from __future__ import annotations


# Populated by `register_coord_codec`; coord classes register themselves
# at their definition site (or serialize.py registers built-ins on module
# import, for the ones that ship with plotlet).
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


def resolve_coord(name: str) -> type:
    """Look up a coord class by registered name, importing the built-in
    coord module on first miss — built-ins register at their definition
    site, and nothing else guarantees that module has been imported when
    a `{"$coord": ...}` envelope arrives from JSON in a fresh process."""
    try:
        return _COORD_REGISTRY[name]
    except KeyError:
        pass
    from .render import coordinates  # noqa: F401 — registers built-ins
    try:
        return _COORD_REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown coordinate {name!r}. Registered coords: "
            f"{sorted(_COORD_REGISTRY)}. Custom coord classes must be "
            f"imported (and registered via `register_coord_codec`) before "
            f"a figure referencing them is decoded."
        ) from None
