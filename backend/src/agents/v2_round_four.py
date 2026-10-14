"""Compatibility import for :mod:`researchassistant.agents.v2_round_four`."""

import sys

from researchassistant.agents import v2_round_four as _implementation

sys.modules[__name__] = _implementation
