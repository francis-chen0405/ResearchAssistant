"""Compatibility import for :mod:`researchassistant.providers.crossref`."""

import sys

from researchassistant.providers import crossref as _implementation

sys.modules[__name__] = _implementation
