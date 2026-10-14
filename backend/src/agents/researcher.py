"""Compatibility import for :mod:`researchassistant.agents.researcher`."""

import sys

from researchassistant.agents import researcher as _implementation

sys.modules[__name__] = _implementation
