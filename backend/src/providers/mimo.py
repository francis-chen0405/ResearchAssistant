"""Compatibility import for :mod:`researchassistant.providers.mimo`."""

import sys

from researchassistant.providers import mimo as _implementation

sys.modules[__name__] = _implementation
