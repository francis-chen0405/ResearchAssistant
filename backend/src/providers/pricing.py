"""Compatibility import for :mod:`researchassistant.providers.pricing`."""

import sys

from researchassistant.providers import pricing as _implementation

sys.modules[__name__] = _implementation
