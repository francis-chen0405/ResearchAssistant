"""Compatibility import for :mod:`researchassistant.agents.reviewer`."""

import sys

from researchassistant.agents import reviewer as _implementation

sys.modules[__name__] = _implementation
