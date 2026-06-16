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

``gap`` is in **pixels** for both kinds. Categorical: routed to
``_CategoryScale.split_gap`` — the scale knows panel width and reserves
the px slots between groups. Continuous: routed to
``_SectoredLinearScale.gap_px`` via ``_AxisDescriptor.sector_gap_px`` —
the scale runs a piecewise mapping that reserves the px slots between
sectors. The ``Sectors`` value itself stays gap-agnostic in its
``offset`` / ``total`` / ``center`` semantics (those return positions in
the no-gap data domain ``[0, sum(lengths)]``). All gap awareness lives
in the scale.

Pass ``divider`` as a dict (``{"linestyle": "dotted", "color": "#bbb",
"linewidth": 0.5}``) to switch the divider on *and* override its style,
mirroring the ``c.spines(left={...})`` shape. Unset keys fall back to
``spec.json:sectors``. The dict form normalizes ``linestyle`` → SVG
``dasharray`` via ``draw.linestyles.resolve_linestyle`` and accepts
``linewidth``/``width`` interchangeably.
"""
from __future__ import annotations

from dataclasses import dataclass

from .draw.linestyles import resolve_linestyle


def _parse_divider(spec):
    """Return ``(on, style_overrides)`` from a ``divider=`` value.

    Accepts ``bool`` (current behavior) or ``dict`` (style overrides). The
    dict form turns the divider on and supplies per-call color/width/dash
    overrides for the chrome renderer."""
    if isinstance(spec, dict):
        out = {}
        if "color" in spec:
            out["color"] = spec["color"]
        if "linewidth" in spec:
            out["width"] = float(spec["linewidth"])
        elif "width" in spec:
            out["width"] = float(spec["width"])
        if "dasharray" in spec:
            out["dasharray"] = spec["dasharray"]
        elif "linestyle" in spec:
            out["dasharray"] = resolve_linestyle(spec["linestyle"])
        return True, out
    return bool(spec), None


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

    ``divider_style`` carries per-instance overrides for the divider's
    color / width / dasharray. ``None`` falls back to ``spec.json:sectors``.
    Set via the dict form of ``divider=`` on ``c.sectors(...)``.
    """
    names:   tuple
    lengths: tuple | None = None   # continuous
    members: tuple | None = None   # categorical (tuple of tuples of cat labels)
    divider: bool = True
    label:   bool = True
    gap:     float | None = None   # px gap between sectors; None = spec default
    divider_style: dict | None = None   # {color, width, dasharray} overrides

    @property
    def kind(self) -> str:
        return "continuous" if self.lengths is not None else "categorical"

    @classmethod
    def coerce(cls, spec, *, name_col=None, length_col="length",
               divider=True, label=True, gap=None, divider_style=None):
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
                    divider_style=divider_style,
                )
            return cls(
                names=tuple(str(k) for k in spec.keys()),
                lengths=tuple(float(v) for v in vals),
                divider=divider, label=label, gap=gap,
                divider_style=divider_style,
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
                divider_style=divider_style,
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
