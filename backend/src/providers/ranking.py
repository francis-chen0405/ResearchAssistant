"""Compatibility import for :mod:`researchassistant.providers.ranking`."""

import sys

from researchassistant.providers import ranking as _implementation

sys.modules[__name__] = _implementation
