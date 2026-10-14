"""Compatibility import for :mod:`researchassistant.agents.v2_discovery`."""

import sys

from researchassistant.agents import v2_discovery as _implementation

sys.modules[__name__] = _implementation
