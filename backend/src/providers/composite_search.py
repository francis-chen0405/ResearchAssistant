"""Compatibility import for :mod:`researchassistant.providers.composite_search`."""

import sys

from researchassistant.providers import composite_search as _implementation

sys.modules[__name__] = _implementation
