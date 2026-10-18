"""Compatibility import for :mod:`researchassistant.api.profile_preflight`."""

import sys

from researchassistant.api import profile_preflight as _implementation

sys.modules[__name__] = _implementation
