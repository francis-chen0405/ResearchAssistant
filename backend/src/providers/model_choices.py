"""Compatibility import for :mod:`researchassistant.providers.model_choices`."""

import sys

from researchassistant.providers import model_choices as _implementation

sys.modules[__name__] = _implementation
