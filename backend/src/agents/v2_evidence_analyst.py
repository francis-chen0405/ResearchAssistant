"""Compatibility import for :mod:`researchassistant.agents.v2_evidence_analyst`."""

import sys

from researchassistant.agents import v2_evidence_analyst as _implementation

sys.modules[__name__] = _implementation
