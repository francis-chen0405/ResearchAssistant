"""Compatibility import for :mod:`researchassistant.agents.planner`."""

import sys

from researchassistant.agents import planner as _implementation

sys.modules[__name__] = _implementation
