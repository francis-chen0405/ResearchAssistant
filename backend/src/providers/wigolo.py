"""Compatibility import for :mod:`researchassistant.providers.wigolo`."""

import sys

from researchassistant.providers import wigolo as _implementation

sys.modules[__name__] = _implementation
