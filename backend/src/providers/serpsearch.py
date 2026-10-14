"""Compatibility import for :mod:`researchassistant.providers.serpsearch`."""

import sys

from researchassistant.providers import serpsearch as _implementation

sys.modules[__name__] = _implementation
