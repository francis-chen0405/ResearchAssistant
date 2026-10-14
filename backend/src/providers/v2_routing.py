"""Compatibility import for :mod:`researchassistant.providers.v2_routing`."""

import sys

from researchassistant.providers import v2_routing as _implementation

sys.modules[__name__] = _implementation
