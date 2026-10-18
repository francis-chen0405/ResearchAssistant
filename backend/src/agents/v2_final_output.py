"""Compatibility import for :mod:`researchassistant.agents.v2_final_output`."""

import sys

from researchassistant.agents import v2_final_output as _implementation

sys.modules[__name__] = _implementation
