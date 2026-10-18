"""Compatibility import for :mod:`researchassistant.agents.v2_initial_planner`."""

import sys

from researchassistant.agents import v2_initial_planner as _implementation

sys.modules[__name__] = _implementation
