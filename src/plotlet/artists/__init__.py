"""Built-in artist registrations.

Hybrid layout: one file per distinct plot type, plus category files that
group mirror pairs or shared-machinery siblings (matches ggplot2's
per-geom convention, with consolidation only where it earns its keep).

Single-artist files (one plot type each):
  scatter, line, bar, hist, imshow, dendrogram, errorbar

Category files (closely-related artists grouped):
  references — axhline, axvline, axhspan, axvspan, hlines, vlines
  fills      — fill_between, area
  shapes     — rect, polygon
  text       — text, annotate

Helpers used by 2+ artist files (`_xy_minmax`, the shared legend-entry
factories, `_step_coords` etc.) live in `_shared.py`.
"""

# Single-artist files
from . import scatter      # noqa: F401
from . import line         # noqa: F401
from . import bar          # noqa: F401
from . import hist         # noqa: F401
from . import imshow       # noqa: F401
from . import dendrogram   # noqa: F401
from . import errorbar     # noqa: F401

# Category files
from . import references   # noqa: F401
from . import fills        # noqa: F401
from . import shapes       # noqa: F401
from . import text         # noqa: F401
