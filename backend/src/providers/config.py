"""Compatibility import for :mod:`researchassistant.providers.config`."""

import sys

from researchassistant.providers import config as _implementation

sys.modules[__name__] = _implementation
