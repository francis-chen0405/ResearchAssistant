"""Compatibility import for :mod:`researchassistant.api.api`."""

import sys

from researchassistant.api import api as _implementation

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
