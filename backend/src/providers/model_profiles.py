"""Compatibility import for :mod:`researchassistant.providers.model_profiles`."""

import sys

from researchassistant.providers import model_profiles as _implementation

sys.modules[__name__] = _implementation
