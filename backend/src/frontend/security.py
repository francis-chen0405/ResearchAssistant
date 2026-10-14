"""Compatibility import for :mod:`researchassistant.api.security`."""

import sys

from researchassistant.api import security as _implementation

sys.modules[__name__] = _implementation
