"""Compatibility import for :mod:`researchassistant.api.evidence_browser_app`."""

import sys

from researchassistant.api import evidence_browser_app as _implementation

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
