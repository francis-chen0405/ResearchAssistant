"""Compatibility import for :mod:`researchassistant.providers.normalization`."""

import sys

from researchassistant.providers import normalization as _implementation

sys.modules[__name__] = _implementation
