"""Compatibility import for :mod:`researchassistant.agents.v2_source_selection`."""

import sys

from researchassistant.agents import v2_source_selection as _implementation

sys.modules[__name__] = _implementation
