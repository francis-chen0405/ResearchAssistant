"""Compatibility import for :mod:`researchassistant.storage.store`."""

import sys

from researchassistant.storage import store as _implementation

sys.modules[__name__] = _implementation
