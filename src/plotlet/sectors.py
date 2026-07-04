"""Sectors — named partitions of an axis.

A panel can partition either axis into named regions via
``c.sectors(spec, axis="x" | "y")``. Sectors come in two kinds, picked from
the spec shape:

  - **Continuous** — values are numeric lengths. Each artist's value
    column (named via ``column=``) is offset into a single global
    coordinate so the standard linear ``x_scale`` / ``y_scale`` covers
    every sector.

        c.sectors({"warmup": 100, "training": 500, "cooldown": 50},
                  column="phase")

  - **Categorical** — values are lists of category labels. Sectors group
    the categorical axis members; the underlying category scale picks up
    the implied split positions and inserts visual gaps between groups.
    This is the structural unification of heatmap row/column clustering
    with continuous-axis partitioning.

        c.sectors({"groupA": ["c1", "c2"], "groupB": ["c3"]}, axis="x")

``divider`` and ``label`` independently toggle the two pieces of sector
chrome. Both default True; both False is the heatmap-clustering case.

``divider`` is a bool — visibility only. Wall *styling* lives on
``c.spines(walls={"color": ..., "width": ..., "linestyle": ...})`` so
there is one consistent API for outer-spine and wall styling.

``gap`` is in **pixels** for both kinds. Categorical: routed to
``_CategoryScale.split_gap`` — the scale knows panel width and reserves
the px slots between groups. Continuous: routed to
``_SectoredLinearScale.gap_px`` via ``_AxisDescriptor.sector_gap_px`` —
the scale runs a piecewise mapping that reserves the px slots between
sectors. The ``Sectors`` value itself stays gap-agnostic in its
``offset`` / ``total`` / ``center`` semantics (those return positions in
the no-gap data domain ``[0, sum(lengths)]``). All gap awareness lives
in the scale.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


class SectoredValue(float):
    """A scalar tagged with the index of the sector it belongs to.

    On a sectored axis, a position isn't a number — it's
    ``(sector, value)``. The framework's sector remap emits these so
    the scale can project each point unambiguously: two rows that
    resolve to the same global float but belong to different sectors
    land on different pixels (separated by ``gap_px``).

    Subclassing ``float`` keeps these transparent for downstream math
    (midpoints, widths, comparisons all work). Arithmetic between two
    ``SectoredValue``s degrades to plain ``float`` — fine, because
    derived quantities (e.g. an interval's midpoint) are interior
    points where boundary disambiguation doesn't apply."""

    __slots__ = ("sector_idx",)

    def __new__(cls, value, sector_idx):
        instance = super().__new__(cls, value)
        instance.sector_idx = sector_idx
        return instance


_UNSET = object()


@dataclass(frozen=True)
class Sectors:
    """Immutable, ordered partition of an axis.

    Exactly one of ``lengths`` or ``members`` is set, picked by the
    construction shape. ``kind`` is derived.

    ``gap`` is the inter-sector pixel pad. For categorical sectors it
    becomes the ``_CategoryScale`` ``split_gap``. ``None`` means "use the
    spec default" (``defaults.category_split_gap``).

    ``divider`` toggles the wall lines between sectors; ``label`` toggles
    the sector-name labels. Both False is the heatmap-clustering case
    (sectors drive layout only, no visible chrome). Wall *styling* lives
    on ``c.spines(walls={...})``.
    """
    names:    tuple
    lengths:  tuple | None = None   # continuous
    members:  tuple | None = None   # categorical (tuple of tuples of cat labels)
    divider:  bool = True
    label:    bool = True
    gap:      float | None = None   # px gap between sectors; None = spec default
    fontsize: float | None = None   # sector-label font size; None = spec default
    rotation: float | None = None   # sector-label rotation degrees; None = spec default

    @property
    def kind(self) -> str:
        return "continuous" if self.lengths is not None else "categorical"

    def _to_dict(self) -> dict:
        # Tuple-of-tuples for `members` round-trips through JSON as
        # list-of-lists; `_from_dict` re-tuples below to match the
        # dataclass declaration.
        return {"names": list(self.names),
                "lengths":  list(self.lengths)  if self.lengths  is not None else None,
                "members":  [list(g) for g in self.members] if self.members is not None else None,
                "divider":  self.divider,
                "label":    self.label,
                "gap":      self.gap,
                "fontsize": self.fontsize,
                "rotation": self.rotation}

    @classmethod
    def _from_dict(cls, d: dict) -> "Sectors":
        lengths = d.get("lengths")
        members = d.get("members")
        return cls(
            names=tuple(d["names"]),
            lengths=tuple(lengths) if lengths is not None else None,
            members=tuple(tuple(g) for g in members) if members is not None else None,
            divider=d.get("divider", True),
            label=d.get("label", True),
            gap=d.get("gap"),
            fontsize=d.get("fontsize"),
            rotation=d.get("rotation"),
        )

    @classmethod
    def coerce(cls, spec, *, name_col=None, length_col="length",
               divider=_UNSET, label=_UNSET, gap=_UNSET,
               fontsize=_UNSET, rotation=_UNSET):
        """Build a Sectors from a Sectors / dict / DataFrame-like.

        Disambiguation by spec shape:

        - ``dict`` with numeric values → continuous (lengths).
        - ``dict`` with list/tuple values → categorical (members).
        - DataFrame → continuous; ``name_col`` and ``length_col``
          identify the columns.
        - Existing ``Sectors`` → returned as-is, with ``divider`` /
          ``label`` / ``gap`` / ``fontsize`` / ``rotation`` overrides
          applied via ``dataclasses.replace`` when explicitly passed.
          Lets ``c.sectors(pt.Sectors(...), label=False)`` flip display
          flags without rebuilding the spec.
        """
        if isinstance(spec, cls):
            updates = {}
            if divider  is not _UNSET: updates["divider"]  = bool(divider)
            if label    is not _UNSET: updates["label"]    = bool(label)
            if gap      is not _UNSET: updates["gap"]      = gap
            if fontsize is not _UNSET: updates["fontsize"] = fontsize
            if rotation is not _UNSET: updates["rotation"] = rotation
            return replace(spec, **updates) if updates else spec
        d = True if divider  is _UNSET else bool(divider)
        l = True if label    is _UNSET else bool(label)
        g = None if gap      is _UNSET else gap
        f = None if fontsize is _UNSET else fontsize
        r = None if rotation is _UNSET else rotation
        if isinstance(spec, dict):
            vals = list(spec.values())
            if vals and all(isinstance(v, (list, tuple)) for v in vals):
                return cls(
                    names=tuple(str(k) for k in spec.keys()),
                    members=tuple(tuple(str(m) for m in v) for v in vals),
                    divider=d, label=l, gap=g, fontsize=f, rotation=r,
                )
            return cls(
                names=tuple(str(k) for k in spec.keys()),
                lengths=tuple(float(v) for v in vals),
                divider=d, label=l, gap=g, fontsize=f, rotation=r,
            )
        # DataFrame-like: column access via ``[col_name]``.
        if hasattr(spec, "columns") or (hasattr(spec, "__getitem__")
                                        and hasattr(spec, "keys")):
            if name_col is None:
                raise TypeError(
                    "Sectors.coerce: DataFrame input needs name_col "
                    "(pass column= to c.sectors)."
                )
            names = list(spec[name_col])
            lengths = list(spec[length_col])
            return cls(
                names=tuple(str(n) for n in names),
                lengths=tuple(float(L) for L in lengths),
                divider=d, label=l, gap=g, fontsize=f, rotation=r,
            )
        raise TypeError(
            f"Sectors: cannot interpret {type(spec).__name__} — "
            "pass a Sectors, dict, or DataFrame-like."
        )

    def __post_init__(self):
        if (self.lengths is None) == (self.members is None):
            raise ValueError(
                "Sectors: exactly one of lengths/members must be set"
            )
        sizes = self.lengths if self.lengths is not None else self.members
        if len(self.names) != len(sizes):
            raise ValueError(
                f"Sectors: names ({len(self.names)}) and "
                f"{'lengths' if self.lengths is not None else 'members'} "
                f"({len(sizes)}) length mismatch"
            )
        if len(self.names) != len(set(self.names)):
            raise ValueError("Sectors: names must be unique")
        if self.kind == "continuous":
            for L in self.lengths:
                if not (L > 0):
                    raise ValueError(f"Sectors: lengths must be > 0; got {L}")
        else:
            # Categorical: every member is a category label; flatten and
            # check uniqueness across all sectors.
            flat = [c for grp in self.members for c in grp]
            if len(flat) != len(set(flat)):
                raise ValueError(
                    "Sectors: categorical members must be unique across sectors"
                )
            for grp in self.members:
                if len(grp) == 0:
                    raise ValueError("Sectors: a sector cannot be empty")

    def _index(self, name):
        try:
            return self.names.index(name)
        except ValueError:
            raise KeyError(f"unknown sector: {name!r}") from None

    # ---------- continuous-only ---------------------------------------------

    def offset(self, name) -> float:
        """For continuous sectors: cumulative length of sectors before
        ``name`` (the data-coordinate left edge of ``name`` in the no-gap
        data domain ``[0, sum(lengths)]``). Gap rendering happens at the
        scale level, not in the data coords — see ``_SectoredLinearScale``.

        For categorical sectors: cumulative band-count of sectors before
        ``name`` — useful for split-index computations.
        """
        i = self._index(name)
        if self.kind == "continuous":
            return float(sum(self.lengths[:i]))
        return float(sum(len(self.members[j]) for j in range(i)))

    def center(self, name) -> float:
        """Continuous: data-coord midpoint of ``name``.
        Categorical: midpoint band index (returns a float)."""
        i = self._index(name)
        if self.kind == "continuous":
            return float(sum(self.lengths[:i]) + self.lengths[i] / 2)
        before = sum(len(self.members[j]) for j in range(i))
        return float(before + len(self.members[i]) / 2 - 0.5)

    def total(self) -> float:
        """Continuous: sum of lengths.
        Categorical: total category count."""
        if self.kind == "continuous":
            return float(sum(self.lengths))
        return float(sum(len(g) for g in self.members))

    def boundaries(self) -> list:
        """Continuous: cumulative positions ``[0, L1, L1+L2, ..., total]``.
        Categorical: cumulative cat counts at sector breaks (band indices
        where each new sector begins, including 0 and total)."""
        out = [0.0]
        cum = 0.0
        sizes = (self.lengths if self.kind == "continuous"
                 else tuple(len(g) for g in self.members))
        for s in sizes:
            cum += s
            out.append(float(cum))
        return out

    def expand_ticks(self, ticks, labels):
        """Replicate per-sector LOCAL tick positions across every sector.

        Each ``t`` in ``ticks`` lands at ``offset(name) + t`` in every
        sector whose length covers it (ticks past a sector's length are
        dropped). Labels travel with their tick value, repeated per
        sector. Continuous only — categorical sectors use the underlying
        category scale and don't need expansion.

        Emits ``SectoredValue`` (tagged with the owning sector's index)
        so right-boundary ticks (``t == length`` of sector i) and
        left-boundary ticks (``t == 0`` of sector i+1) land on their own
        sector's pixel edge even though they share the same global float.
        """
        if self.kind != "continuous":
            raise TypeError("Sectors.expand_ticks is continuous-only")
        n = min(len(ticks), len(labels))
        out_t, out_l = [], []
        for idx, (name, length) in enumerate(zip(self.names, self.lengths)):
            offset = self.offset(name)
            for t, l in zip(ticks[:n], labels[:n]):
                tv = float(t)
                if not (0.0 <= tv <= length):
                    continue
                out_t.append(SectoredValue(offset + tv, idx))
                out_l.append(l)
        return out_t, out_l

    # ---------- categorical-only --------------------------------------------

    def cats(self) -> tuple:
        """All categories flattened in sector order. Categorical only."""
        if self.kind != "categorical":
            raise TypeError("Sectors.cats() is categorical-only")
        return tuple(c for grp in self.members for c in grp)

    def split_indices(self) -> list:
        """Band indices where each new sector begins (excluding 0 and N).
        Maps directly to ``_CategoryScale.splits``. Categorical only."""
        if self.kind != "categorical":
            raise TypeError("Sectors.split_indices() is categorical-only")
        out, cum = [], 0
        for grp in self.members[:-1]:
            cum += len(grp)
            out.append(cum)
        return out

    def cat_to_group(self) -> dict:
        """``{cat: sector_name}`` mapping. Categorical only.

        Compatible with the existing ``_CategoryScale(groups=...)`` shape
        so the scale builder can consume sectors with one line of glue.
        """
        if self.kind != "categorical":
            raise TypeError("Sectors.cat_to_group() is categorical-only")
        return {c: name
                for name, grp in zip(self.names, self.members)
                for c in grp}
