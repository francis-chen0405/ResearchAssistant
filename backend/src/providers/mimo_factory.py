"""Compatibility import for :mod:`researchassistant.providers.mimo_factory`."""

import sys

from researchassistant.providers import mimo_factory as _implementation

sys.modules[__name__] = _implementation
