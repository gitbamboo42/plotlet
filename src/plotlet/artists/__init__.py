"""Built-in artist registrations.

Hybrid layout: one file per distinct plot type, plus category files that
group mirror pairs or shared-machinery siblings — consolidation only
where the related artists share enough structure to earn it.

Single-artist files (one plot type each):
  scatter, line, bar, hist, imshow, heatmap, dendrogram, errorbar
  boxplot, violin, swarm, strip
  pointplot, ecdf, rug, density_1d, regression, kde_2d, hexbin
  freqpoly, contour, ridge, qq

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
from . import heatmap      # noqa: F401
from . import dendrogram   # noqa: F401
from . import errorbar     # noqa: F401
from . import boxplot      # noqa: F401
from . import violin       # noqa: F401
from . import swarm        # noqa: F401
from . import strip        # noqa: F401
from . import pointplot    # noqa: F401
from . import ecdf         # noqa: F401
from . import rug          # noqa: F401
from . import density_1d   # noqa: F401
from . import regression   # noqa: F401
from . import kde_2d       # noqa: F401
from . import hexbin       # noqa: F401
from . import freqpoly     # noqa: F401
from . import contour      # noqa: F401
from . import ridge        # noqa: F401
from . import qq           # noqa: F401

# Category files
from . import references   # noqa: F401
from . import fills        # noqa: F401
from . import shapes       # noqa: F401
from . import text         # noqa: F401
