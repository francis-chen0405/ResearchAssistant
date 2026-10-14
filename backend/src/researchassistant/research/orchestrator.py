"""Compatibility alias for the isolated historical execution owner."""

import sys

from researchassistant.research import historical_execution as _implementation

sys.modules[__name__] = _implementation
