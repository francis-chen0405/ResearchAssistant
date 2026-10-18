"""Compatibility import for :mod:`researchassistant.agents.opposingresearcher`."""

import sys

from researchassistant.agents import opposingresearcher as _implementation

sys.modules[__name__] = _implementation
