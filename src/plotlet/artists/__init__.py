"""Built-in artist specs — registered at import time.

Each artist is now a single `ArtistSpec` that knows how to record itself,
contribute to autoscaling, and draw. This replaces the scattered hardcoded
branches in the old `_render`.
"""
# Importing every per-artist sub-module triggers its `add_artist(...)` call
# at import time, populating the global registry. `core` imports this package
# (not any individual sub-module) to load every built-in.
from . import line
from . import scatter
from . import bar
from . import hist
from . import fill_between
from . import area
from . import shapes
from . import references
from . import imshow
from . import dendrogram
from . import text
from . import errorbar
