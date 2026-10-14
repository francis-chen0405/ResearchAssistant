"""Compatibility import for :mod:`researchassistant.evidence.synthesizer`."""

import sys

from researchassistant.evidence import synthesizer as _implementation

sys.modules[__name__] = _implementation
