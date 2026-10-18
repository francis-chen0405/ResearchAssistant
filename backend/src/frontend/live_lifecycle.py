"""Compatibility import for :mod:`researchassistant.api.live_lifecycle`."""

import sys

from researchassistant.api import live_lifecycle as _implementation

sys.modules[__name__] = _implementation
