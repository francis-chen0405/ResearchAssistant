"""Compatibility import for :mod:`researchassistant.providers.discovery_transport`."""

import sys

from researchassistant.providers import discovery_transport as _implementation

sys.modules[__name__] = _implementation
