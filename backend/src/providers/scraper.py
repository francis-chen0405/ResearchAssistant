"""Compatibility import for :mod:`researchassistant.providers.scraper`."""

import sys

from researchassistant.providers import scraper as _implementation

sys.modules[__name__] = _implementation
