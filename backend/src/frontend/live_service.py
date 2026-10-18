"""Compatibility import for :mod:`researchassistant.api.live_service`."""

import sys

from researchassistant.api import live_service as _implementation

sys.modules[__name__] = _implementation
