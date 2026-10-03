"""Compatibility import for :mod:`researchassistant.contracts.models`."""

import sys

from researchassistant.contracts import models as _implementation

sys.modules[__name__] = _implementation
