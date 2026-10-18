"""Compatibility import for :mod:`researchassistant.providers.clients`."""

import sys

from researchassistant.providers import clients as _implementation

sys.modules[__name__] = _implementation
