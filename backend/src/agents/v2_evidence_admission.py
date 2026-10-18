"""Compatibility import for :mod:`researchassistant.agents.v2_evidence_admission`."""

import sys

from researchassistant.agents import v2_evidence_admission as _implementation

sys.modules[__name__] = _implementation
