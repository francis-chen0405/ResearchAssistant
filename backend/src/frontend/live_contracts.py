"""Compatibility import for :mod:`researchassistant.api.live_contracts`."""

import sys

from researchassistant.api import live_contracts as _implementation

sys.modules[__name__] = _implementation
