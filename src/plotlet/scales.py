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


class _PowerScale:
    """Power-transform scale: `t(x) = sign(x) * |x|**exponent`.

    `exponent < 1` (typical 0.5 for square-root) compresses large values
    and spreads small ones — useful for count data, areas, intensities.
    Negative inputs are mapped through `sign * |x|**exponent` so the scale
    works on both signs (matches d3 `scalePow`).
    """

    def __init__(self, d0, d1, r0, r1, exponent=0.5):
        if exponent <= 0:
            raise ValueError("power scale exponent must be > 0")
        self.exponent = float(exponent)
        self.d0, self.d1 = d0, d1
        self.r0, self.r1 = r0, r1
        self.t0 = self._fwd(d0)
        self.t1 = self._fwd(d1)

    def _fwd(self, x):
        if x >= 0:
            return x ** self.exponent
        return -((-x) ** self.exponent)

    def __call__(self, v):
        t = self._fwd(v)
        if self.t1 == self.t0:
            return self.r0
        return self.r0 + (t - self.t0) * (self.r1 - self.r0) / (self.t1 - self.t0)

    def ticks(self, n=8):
        """Ticks chosen via the linear nice-numbers algorithm on the data
        domain — the algorithm picks human-readable values (0, 25, 100, …)
        that happen to lie at non-uniform pixel positions on a sqrt axis."""
        return _nice_ticks(self.d0, self.d1, n)


class _SymlogScale:
    """Symmetric log: linear inside [-linthresh, +linthresh], log outside.

    Mirrors matplotlib's `symlog` semantics. The forward map is
    `t(x) = sign(x) * (linthresh + log10(|x|/linthresh) * linthresh)` for
    `|x| > linthresh`, and `x` itself inside the linear region. Useful for
    fold-change axes (volcano / MA plots) where both signs matter and the
    range spans several orders of magnitude.
    """

    def __init__(self, d0, d1, r0, r1, linthresh=1.0):
        if linthresh <= 0:
            raise ValueError("symlog linthresh must be > 0")
        self.linthresh = float(linthresh)
        self.d0, self.d1 = d0, d1
        self.r0, self.r1 = r0, r1
        self.t0 = self._fwd(d0)
        self.t1 = self._fwd(d1)

    def _fwd(self, x):
        a = abs(x)
        if a <= self.linthresh:
            return float(x)
        sign = 1.0 if x > 0 else -1.0
        return sign * (self.linthresh + math.log10(a / self.linthresh) * self.linthresh)

    def __call__(self, v):
        t = self._fwd(v)
        if self.t1 == self.t0:
            return self.r0
        return self.r0 + (t - self.t0) * (self.r1 - self.r0) / (self.t1 - self.t0)

    def ticks(self, n=8):
        """Ticks at decade boundaries on both sides plus 0 (and ±linthresh
        if outside the decade grid). Filtered to the domain."""
        thr = self.linthresh
        out = set([0.0])
        # Positive side decades: linthresh, 10*linthresh, 100*linthresh, ...
        if self.d1 > thr:
            k = 0
            while True:
                v = thr * 10 ** k
                if v > self.d1:
                    break
                out.add(v)
                k += 1
        # Negative side mirrors.
        if self.d0 < -thr:
            k = 0
            while True:
                v = -thr * 10 ** k
                if v < self.d0:
                    break
                out.add(v)
                k += 1
        ticks = sorted(t for t in out if self.d0 <= t <= self.d1)
        return ticks


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
