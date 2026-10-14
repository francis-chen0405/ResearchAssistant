"""Compatibility import for :mod:`researchassistant.agents.v2_coverage`."""

import sys

from researchassistant.agents import v2_coverage as _implementation

sys.modules[__name__] = _implementation
