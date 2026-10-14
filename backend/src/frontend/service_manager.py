"""Compatibility import for :mod:`researchassistant.api.service_manager`."""

import sys

from researchassistant.api import service_manager as _implementation

sys.modules[__name__] = _implementation
