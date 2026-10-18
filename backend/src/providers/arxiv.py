"""Compatibility import for :mod:`researchassistant.providers.arxiv`."""

import sys

from researchassistant.providers import arxiv as _implementation

sys.modules[__name__] = _implementation
