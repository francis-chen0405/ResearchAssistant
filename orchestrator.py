"""Compatibility import for :mod:`researchassistant.research.orchestrator`."""

import sys

from researchassistant.research import orchestrator as _implementation

sys.modules[__name__] = _implementation
