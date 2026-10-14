"""Compatibility import for :mod:`researchassistant.providers.openalex_neighborhood`."""

import sys

from researchassistant.providers import openalex_neighborhood as _implementation

sys.modules[__name__] = _implementation
