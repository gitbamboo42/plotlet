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
chrome. Both default to True for user calls; heatmap clustering passes
both False so existing baselines stay byte-identical. Typical usage
shows one or the other — drawing both a divider line *and* the
inter-sector gap reads as redundant clutter.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sectors:
    """Immutable, ordered partition of an axis.

    Exactly one of ``lengths`` or ``members`` is set, picked by the
    construction shape. ``kind`` is derived.

    ``gap`` is the inter-sector pixel pad. For categorical sectors it
    becomes the ``_CategoryScale`` ``split_gap``. ``None`` means "use the
    spec default" (``defaults.category_split_gap``).

    ``divider`` toggles the boundary divider lines; ``label`` toggles
    the sector-name labels. Both default True; both False is the heatmap-
    clustering case (sectors drive layout only, no visible chrome).
    """
    names:   tuple
    lengths: tuple | None = None   # continuous
    members: tuple | None = None   # categorical (tuple of tuples of cat labels)
    divider: bool = True
    label:   bool = True
    gap:     float | None = None   # px gap between sectors; None = spec default

    @property
    def kind(self) -> str:
        return "continuous" if self.lengths is not None else "categorical"

    @classmethod
    def coerce(cls, spec, *, name_col=None, length_col="length",
               divider=True, label=True, gap=None):
        """Build a Sectors from a Sectors / dict / DataFrame-like.

        Disambiguation by spec shape:

        - ``dict`` with numeric values → continuous (lengths).
        - ``dict`` with list/tuple values → categorical (members).
        - DataFrame → continuous; ``name_col`` and ``length_col``
          identify the columns.
        - Existing ``Sectors`` → returned as-is (kwargs ignored).
        """
        if isinstance(spec, cls):
            return spec
        if isinstance(spec, dict):
            vals = list(spec.values())
            if vals and all(isinstance(v, (list, tuple)) for v in vals):
                return cls(
                    names=tuple(str(k) for k in spec.keys()),
                    members=tuple(tuple(str(m) for m in v) for v in vals),
                    divider=divider, label=label, gap=gap,
                )
            return cls(
                names=tuple(str(k) for k in spec.keys()),
                lengths=tuple(float(v) for v in vals),
                divider=divider, label=label, gap=gap,
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
                divider=divider, label=label, gap=gap,
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
        ``name`` (the global-coordinate left edge of ``name``).

        For categorical sectors: cumulative band-count of sectors before
        ``name`` — useful for split-index computations.
        """
        i = self._index(name)
        if self.kind == "continuous":
            return float(sum(self.lengths[:i]))
        return float(sum(len(self.members[j]) for j in range(i)))

    def center(self, name) -> float:
        """Continuous: global-coordinate midpoint of ``name``.
        Categorical: midpoint band index (returns a float)."""
        i = self._index(name)
        if self.kind == "continuous":
            return float(sum(self.lengths[:i]) + self.lengths[i] / 2)
        before = sum(len(self.members[j]) for j in range(i))
        return float(before + len(self.members[i]) / 2 - 0.5)

    def total(self) -> float:
        """Continuous: sum of lengths. Categorical: total category count."""
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
