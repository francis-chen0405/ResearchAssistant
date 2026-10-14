"""Compatibility import for :mod:`researchassistant.agents.v2_reviewer_ledger`."""

import sys

from researchassistant.agents import v2_reviewer_ledger as _implementation

sys.modules[__name__] = _implementation
