"""Coordinate scales: linear, log, category, symlog, power, time.

Each scale is a callable: `scale(data_value) -> pixel_position`. Each also
exposes `.ticks(n)` for axis tick generation. `_CategoryScale` returns the
band *center* for a category, with `.bandwidth` giving the band width — bar
artists subtract `bandwidth/2` to get the rect's left edge.

`_TimeScale` accepts `datetime.date` / `datetime.datetime` (or epoch-seconds
floats) on the data side; ticks come back as datetime objects at sensible
calendar boundaries (year, month, day, hour, minute, second) and the scale
exposes `format_tick` so the caller can render labels at the matching
resolution.
"""
import datetime
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
    works on both signs.
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

    The forward map is
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
    """Categorical scale — equally-spaced bands with padding `p` on each
    end (inner band gap and outer margin both = `p` * band width).

    Returns the *center* of the band for each category. Bar artists fetch
    `.bandwidth` and subtract half to get the rect's left edge.
    """

    def __init__(self, cats, r0, r1, padding, splits=None, gap=0.0, groups=None):
        self.cats = list(cats)
        self.r0, self.r1 = r0, r1
        self.padding = padding
        n = len(self.cats) or 1
        # Two ways to declare splits, kept separate so neither path penalises
        # the other:
        # - `splits=` is the low-level form: explicit band indices. Stable
        #   across reorders by external callers, used by tests / hand-rolled
        #   scales.
        # - `groups=` is the cat->group dict form: the scale walks `cats` in
        #   final order and inserts a boundary wherever the group label
        #   changes. Lets the heatmap stay agnostic about the eventual axis
        #   order — gaps land in the right place even when a peer artist
        #   (e.g. dendrogram) drives the order through `axis_order`.
        # `groups=` wins when both are passed.
        if groups:
            derived, prev = [], None
            for i, c in enumerate(self.cats):
                g = groups.get(c)
                if i > 0 and g != prev:
                    derived.append(i)
                prev = g
            self.splits = derived
        else:
            self.splits = sorted({b for b in splits if 0 < b < n}) if splits else []
        self.gap = float(gap) if self.splits else 0.0
        total = (r1 - r0) - self.gap * len(self.splits)
        self.step = total / (n + padding)
        self.bandwidth = self.step * (1 - padding)
        self._center = self.r0 + padding * self.step + self.bandwidth / 2

    def _gap_before(self, i):
        """Accumulated split-gap px sitting to the left of band `i`."""
        if not self.splits:
            return 0.0
        return self.gap * sum(1 for b in self.splits if b <= i)

    def __call__(self, cat):
        try:
            i = self.cats.index(cat)
        except ValueError:
            return float("nan")
        return self._center + i * self.step + self._gap_before(i)

    def ticks(self, n=None):
        return list(self.cats)


# ---------------------------------------------------------------------------
# Time scale
# ---------------------------------------------------------------------------
# Internal representation is POSIX seconds (UTC). Inputs may be
# `datetime.datetime` (tz-aware or naive — naive is treated as UTC so the
# output stays byte-identical across machines), `datetime.date` (treated as
# UTC midnight), or a raw float (interpreted as already-converted seconds).

_UTC = datetime.timezone.utc

_TICK_UNITS = [
    # (unit name, approx seconds, "nice" multipliers used to step)
    ("year",   365.25 * 86400, [1, 2, 5, 10, 20, 50, 100]),
    ("month",  30.0 * 86400,   [1, 2, 3, 6]),
    ("day",    86400,          [1, 2, 5, 10, 15]),
    ("hour",   3600,           [1, 2, 3, 6, 12]),
    ("minute", 60,             [1, 2, 5, 10, 15, 30]),
    ("second", 1,              [1, 2, 5, 10, 15, 30]),
]


def _to_epoch(v):
    """Datetime / date → POSIX seconds (UTC). Floats pass through."""
    if isinstance(v, datetime.datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=_UTC)
        return v.timestamp()
    if isinstance(v, datetime.date):
        return datetime.datetime.combine(v, datetime.time.min, tzinfo=_UTC).timestamp()
    return float(v)


def _from_epoch(s):
    """POSIX seconds (UTC) → tz-aware `datetime`."""
    return datetime.datetime.fromtimestamp(s, tz=_UTC)


def _coerce_time_lim(lim):
    """Coerce a `(lo, hi)` xlim/ylim pair to epoch seconds for a temporal
    axis. Accepts None (passes through), datetime/date endpoints, or raw
    floats (assumed already-converted)."""
    if lim is None:
        return None
    return (_to_epoch(lim[0]), _to_epoch(lim[1]))


def _pick_time_unit(span_seconds, n):
    """Pick (unit_name, step_in_unit) so the axis gets roughly `n` ticks.

    Strategy: enumerate every (unit × allowed_multiplier) the table permits,
    sort by step duration, then take the smallest step whose duration is
    >= target. That way a 12-month span lands on '3 months', not '1 year'."""
    target_step = max(span_seconds / max(n, 1), 1e-9)
    candidates = []
    for unit, secs, multipliers in _TICK_UNITS:
        for m in multipliers:
            candidates.append((m * secs, unit, m))
    candidates.sort()
    for size, unit, m in candidates:
        if size >= target_step:
            return unit, m
    return candidates[-1][1], candidates[-1][2]


def _step_year(dt, n):
    return dt.replace(year=dt.year + n)


def _step_month(dt, n):
    total = (dt.year * 12 + (dt.month - 1)) + n
    return dt.replace(year=total // 12, month=(total % 12) + 1)


def _floor_to_unit(dt, unit, step):
    """Snap `dt` down to the nearest multiple of (unit × step) on the
    calendar. The 'multiple' is taken relative to a natural origin:
    year 1 for years/months, dt's own date for finer units."""
    if unit == "year":
        return datetime.datetime(dt.year - (dt.year - 1) % step, 1, 1, tzinfo=_UTC)
    if unit == "month":
        idx = (dt.year * 12 + (dt.month - 1))
        idx -= idx % step
        return datetime.datetime(idx // 12, (idx % 12) + 1, 1, tzinfo=_UTC)
    if unit == "day":
        return datetime.datetime(dt.year, dt.month, dt.day, tzinfo=_UTC)
    if unit == "hour":
        return datetime.datetime(dt.year, dt.month, dt.day,
                                  (dt.hour // step) * step, tzinfo=_UTC)
    if unit == "minute":
        return datetime.datetime(dt.year, dt.month, dt.day, dt.hour,
                                  (dt.minute // step) * step, tzinfo=_UTC)
    return datetime.datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute,
                              (dt.second // step) * step, tzinfo=_UTC)


def _advance(dt, unit, step):
    if unit == "year":   return _step_year(dt, step)
    if unit == "month":  return _step_month(dt, step)
    if unit == "day":    return dt + datetime.timedelta(days=step)
    if unit == "hour":   return dt + datetime.timedelta(hours=step)
    if unit == "minute": return dt + datetime.timedelta(minutes=step)
    return dt + datetime.timedelta(seconds=step)


# strftime pattern for tick labels at each tick-unit resolution.
_FMT_FOR_UNIT = {
    "year":   "%Y",
    "month":  "%Y-%m",
    "day":    "%Y-%m-%d",
    "hour":   "%Y-%m-%d %H:%M",
    "minute": "%H:%M",
    "second": "%H:%M:%S",
}


class _TimeScale:
    """Time axis on POSIX seconds. Accepts datetime / date / float inputs;
    `.ticks(n)` returns calendar-aligned datetimes; `.format_tick` formats
    them at the resolution the tick spacing implies."""

    def __init__(self, d0, d1, r0, r1):
        self.d0 = float(d0)
        self.d1 = float(d1)
        self.r0, self.r1 = r0, r1
        span = max(self.d1 - self.d0, 1.0)
        self._unit, self._step = _pick_time_unit(span, 8)
        self._fmt_pattern = _FMT_FOR_UNIT[self._unit]

    def __call__(self, v):
        s = _to_epoch(v)
        if self.d1 == self.d0:
            return self.r0
        return self.r0 + (s - self.d0) * (self.r1 - self.r0) / (self.d1 - self.d0)

    def ticks(self, n=8):
        if self.d1 <= self.d0:
            return [_from_epoch(self.d0)]
        span = self.d1 - self.d0
        unit, step = _pick_time_unit(span, n)
        self._unit, self._step = unit, step
        self._fmt_pattern = _FMT_FOR_UNIT[unit]
        start = _floor_to_unit(_from_epoch(self.d0), unit, step)
        end = _from_epoch(self.d1)
        out = []
        t = start
        # Break *before* appending past `end` so the tick list stays
        # bounded by the domain — otherwise the first tick past d1 lands
        # in tick-label space past the data area's right/bottom edge.
        for _ in range(1000):
            if t > end:
                break
            if t.timestamp() >= self.d0:
                out.append(t)
            t = _advance(t, unit, step)
        return out

    def format_tick(self, t):
        if isinstance(t, (datetime.date, datetime.datetime)):
            if not isinstance(t, datetime.datetime):
                t = datetime.datetime.combine(t, datetime.time.min, tzinfo=_UTC)
            return t.strftime(self._fmt_pattern)
        return _fmt_tick(t)


# ---------------------------------------------------------------------------
# Tick formatting
# ---------------------------------------------------------------------------

def _fmt_tick(t):
    """Format a tick value: 'g' for typical values, scientific for extremes."""
    if isinstance(t, str):
        return t
    if isinstance(t, datetime.datetime):
        return t.strftime("%Y-%m-%d %H:%M")
    if isinstance(t, datetime.date):
        return t.strftime("%Y-%m-%d")
    if t == 0:
        return "0"
    a = abs(t)
    if a >= 1e4 or a < 1e-3:
        return f"{t:.0e}".replace("e+0", "e").replace("e-0", "e-").replace("e+", "e")
    return f"{t:g}"
