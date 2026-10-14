"""Compatibility import for :mod:`researchassistant.agents.supportingresearcher`."""

import sys

from researchassistant.agents import supportingresearcher as _implementation

sys.modules[__name__] = _implementation
