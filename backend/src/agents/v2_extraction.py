"""Compatibility import for :mod:`researchassistant.agents.v2_extraction`."""

import sys

from researchassistant.agents import v2_extraction as _implementation

sys.modules[__name__] = _implementation
