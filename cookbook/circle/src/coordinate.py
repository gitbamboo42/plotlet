"""CircularCoordinate — maps (t, r) to pixel (x, y) on a ring.

  t in [0, 1]  — position around the ring, clockwise from 12 o'clock
  r in [0, 1]  — radial depth: 0 = inner edge, 1 = outer edge
"""
import math


class CircularCoordinate:
    """Ring-shaped coordinate: t around the ring, r along the radius.

    r_inner : inner ring radius as a fraction of the outer radius (default 0.30)
    gap     : padding between outer ring edge and canvas edge,
              as a fraction of half the canvas size (default 0.05)
    """

    def __init__(self, r_inner: float = 0.30, gap: float = 0.05):
        self.r_inner = r_inner
        self.gap     = gap

    def __call__(self, artist: dict, iw: float, ih: float):
        R  = min(iw, ih) / 2 * (1.0 - self.gap)
        ri = R * self.r_inner
        cx, cy = iw / 2, ih / 2

        def project(t: float, r: float):
            ang    = math.pi / 2 - 2 * math.pi * t
            radius = ri + r * (R - ri)
            return cx + radius * math.cos(ang), cy - radius * math.sin(ang)

        return project
