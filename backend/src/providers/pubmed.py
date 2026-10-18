"""Compatibility import for :mod:`researchassistant.providers.pubmed`."""

import sys

from researchassistant.providers import pubmed as _implementation

sys.modules[__name__] = _implementation
