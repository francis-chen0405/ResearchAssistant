"""Compatibility import for :mod:`researchassistant.agents.v2_adaptive_search`."""

import sys

from researchassistant.agents import v2_adaptive_search as _implementation

sys.modules[__name__] = _implementation
