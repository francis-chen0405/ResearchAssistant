"""Compatibility alias for neutral deterministic discovery validation."""

import sys

from researchassistant.contracts import discovery_capabilities as _implementation

sys.modules[__name__] = _implementation
