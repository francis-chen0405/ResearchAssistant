"""Compatibility import for :mod:`researchassistant.api.provider_connections`."""

import sys

from researchassistant.api import provider_connections as _implementation

sys.modules[__name__] = _implementation
