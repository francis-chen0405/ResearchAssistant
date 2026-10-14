"""Compatibility import for :mod:`researchassistant.agents.v2_deep_analysis`."""

import sys

from researchassistant.agents import v2_deep_analysis as _implementation

sys.modules[__name__] = _implementation
