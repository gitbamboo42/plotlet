"""Visual spec — loaded from bundled spec.json. Internal.

The spec is the locked visual contract: colors, fonts, sizes, default alphas,
legend dimensions. Submodules read from here to avoid hardcoding literals.
"""
import json
from pathlib import Path

_HERE = Path(__file__).parent
SPEC = json.loads((_HERE / "spec.json").read_text())

# Convenience handles to subsections — used by other modules.
_TAB10 = SPEC["colors"]["tab10"]
_COLOR_NAMES = SPEC["colors"]["named"]
_DASH = SPEC["linestyles"]
_D = SPEC["defaults"]
_FRAME = SPEC["frame"]
_GRIDSPEC = SPEC["grid"]
_FONTSPEC = SPEC["font"]
_LEGSPEC = SPEC["legend"]
_SIZESPEC = SPEC["size"]
_LAYOUTSPEC = SPEC["layout"]
