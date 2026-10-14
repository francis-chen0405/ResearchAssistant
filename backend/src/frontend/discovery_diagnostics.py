"""Compatibility import for :mod:`researchassistant.api.discovery_diagnostics`."""

import sys

from researchassistant.api import discovery_diagnostics as _implementation

sys.modules[__name__] = _implementation
