"""Compatibility import for :mod:`researchassistant.agents.analyst`."""

import sys

from researchassistant.agents import analyst as _implementation

sys.modules[__name__] = _implementation
