"""Compatibility import for :mod:`researchassistant.providers.v2_factory`."""

import sys

from researchassistant.providers import v2_factory as _implementation

sys.modules[__name__] = _implementation
