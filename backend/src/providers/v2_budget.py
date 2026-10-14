"""Compatibility import for :mod:`researchassistant.providers.v2_budget`."""

import sys

from researchassistant.providers import v2_budget as _implementation

sys.modules[__name__] = _implementation
