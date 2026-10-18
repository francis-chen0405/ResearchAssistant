"""Compatibility import for :mod:`researchassistant.agents.v2_acquisition`."""

import sys

from researchassistant.agents import v2_acquisition as _implementation

sys.modules[__name__] = _implementation
