"""Compatibility import for :mod:`researchassistant.providers.llm`."""

import sys

from researchassistant.providers import llm as _implementation

sys.modules[__name__] = _implementation
