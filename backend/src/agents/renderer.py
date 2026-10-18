"""Compatibility import for :mod:`researchassistant.evidence.renderer`."""

import sys

from researchassistant.evidence import renderer as _implementation

sys.modules[__name__] = _implementation
