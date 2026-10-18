"""Compatibility import for :mod:`researchassistant.api.live_history`."""

import sys

from researchassistant.api import live_history as _implementation

sys.modules[__name__] = _implementation
