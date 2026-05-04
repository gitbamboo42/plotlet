"""Coordinate scales: linear, log, category.

Each scale is a callable: `scale(data_value) -> pixel_position`. Each also
exposes `.ticks(n)` for axis tick generation. `_CategoryScale` returns the
band *center* for a category, with `.bandwidth` giving the band width — bar
artists subtract `bandwidth/2` to get the rect's left edge.
"""
import math


# ---------------------------------------------------------------------------
# Nice-numbers algorithm (1/2/5 × 10ⁿ)
# ---------------------------------------------------------------------------

def _nice_step(span, n):
    if span <= 0:
        return 1
    step = span / n
    mag = 10 ** math.floor(math.log10(step))
    err = step / mag
    if err < 1.5: return 1 * mag
    if err < 3:   return 2 * mag
    if err < 7:   return 5 * mag
    return 10 * mag


def _nice_ticks(lo, hi, n=8):
    if lo == hi:
        return [lo]
    step = _nice_step(hi - lo, n)
    eps = abs(step) * 1e-9
    start = math.ceil(lo / step - 1e-9) * step
    out, t = [], start
    while t <= hi + eps:
        out.append(round(t, 10))
        t += step
    return out


def _nice_domain(lo, hi, n=8):
    if lo == hi:
        return (lo - 0.5, hi + 0.5)
    step = _nice_step(hi - lo, n)
    return (math.floor(lo / step) * step, math.ceil(hi / step) * step)


# ---------------------------------------------------------------------------
# Scale classes
# ---------------------------------------------------------------------------

class _LinearScale:
    def __init__(self, d0, d1, r0, r1):
        self.d0, self.d1, self.r0, self.r1 = d0, d1, r0, r1

    def __call__(self, v):
        if self.d1 == self.d0:
            return self.r0
        return self.r0 + (v - self.d0) * (self.r1 - self.r0) / (self.d1 - self.d0)

    def ticks(self, n=8):
        return _nice_ticks(self.d0, self.d1, n)


class _LogScale:
    def __init__(self, d0, d1, r0, r1):
        if d0 <= 0 or d1 <= 0:
            raise ValueError("log scale needs strictly positive domain")
        self.d0, self.d1 = d0, d1
        self.l0, self.l1 = math.log10(d0), math.log10(d1)
        self.r0, self.r1 = r0, r1

    def __call__(self, v):
        if v <= 0:
            return float("nan")
        return self.r0 + (math.log10(v) - self.l0) * (self.r1 - self.r0) / (self.l1 - self.l0)

    def ticks(self, n=8):
        a, b = math.floor(self.l0), math.ceil(self.l1)
        return [10 ** k for k in range(int(a), int(b) + 1) if self.d0 <= 10 ** k <= self.d1]


class _CategoryScale:
    """Categorical scale — mirrors d3.scaleBand().padding(p) (inner = outer = p).

    Returns the *center* of the band for each category. Bar artists fetch
    `.bandwidth` and subtract half to get the rect's left edge.
    """

    def __init__(self, cats, r0, r1, padding):
        self.cats = list(cats)
        self.r0, self.r1 = r0, r1
        self.padding = padding
        n = len(self.cats) or 1
        total = r1 - r0
        self.step = total / (n + padding)
        self.bandwidth = self.step * (1 - padding)
        self._center = self.r0 + padding * self.step + self.bandwidth / 2

    def __call__(self, cat):
        try:
            i = self.cats.index(cat)
        except ValueError:
            return float("nan")
        return self._center + i * self.step

    def ticks(self, n=None):
        return list(self.cats)


# ---------------------------------------------------------------------------
# Tick formatting
# ---------------------------------------------------------------------------

def _fmt_tick(t):
    """Format a tick value: 'g' for typical values, scientific for extremes."""
    if isinstance(t, str):
        return t
    if t == 0:
        return "0"
    a = abs(t)
    if a >= 1e4 or a < 1e-3:
        return f"{t:.0e}".replace("e+0", "e").replace("e-0", "e-").replace("e+", "e")
    return f"{t:g}"
