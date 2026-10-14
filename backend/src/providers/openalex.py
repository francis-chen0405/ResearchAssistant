"""Compatibility import for :mod:`researchassistant.providers.openalex`."""

import sys

from researchassistant.providers import openalex as _implementation

sys.modules[__name__] = _implementation
