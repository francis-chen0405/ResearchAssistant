"""Compatibility import for :mod:`researchassistant.api.live_progress`."""

import sys

from researchassistant.api import live_progress as _implementation

sys.modules[__name__] = _implementation
