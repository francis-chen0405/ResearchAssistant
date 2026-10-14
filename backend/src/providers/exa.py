"""Compatibility import for :mod:`researchassistant.providers.exa`."""

import sys

from researchassistant.providers import exa as _implementation

sys.modules[__name__] = _implementation
