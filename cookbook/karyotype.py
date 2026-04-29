"""Karyotype ideogram — placeholder.

This file will be filled in as the first cookbook example after the
scaffold-refactor step (`plotlet.measure_text`, `plotlet.text_path`,
public scale classes). It demonstrates the three-step recipe for a custom
artist:

  1. Record method calls into `Figure._calls`.
  2. Domain logic in `_render` for the new artist's axis extents.
  3. A draw branch / artist helper that emits SVG strings.

For chromosome ideograms specifically, the artist will draw:
  - Chromosome rectangles along a horizontal axis (genomic coordinates)
  - Banded coloring (G-bands from cytogenetic stains)
  - Optional gene/locus annotations

Tracked as the first stress test of the scaffold philosophy.
"""
