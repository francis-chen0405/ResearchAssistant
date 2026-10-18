"""Compatibility import for :mod:`researchassistant.providers.firecrawl`."""

import sys

from researchassistant.providers import firecrawl as _implementation

sys.modules[__name__] = _implementation
