"""Compatibility import for :mod:`researchassistant.providers.acquisition`."""

import sys

from researchassistant.providers import acquisition as _implementation

sys.modules[__name__] = _implementation
