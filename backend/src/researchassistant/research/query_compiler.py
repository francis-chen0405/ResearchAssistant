"""Compatibility alias for neutral deterministic discovery validation."""

import sys

from researchassistant.contracts import query_compiler as _implementation

sys.modules[__name__] = _implementation
