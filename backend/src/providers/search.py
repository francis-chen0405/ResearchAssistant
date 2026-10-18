"""Compatibility import for :mod:`researchassistant.providers.search`."""

import sys

from researchassistant.providers import search as _implementation

sys.modules[__name__] = _implementation
