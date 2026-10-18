"""Compatibility import for :mod:`researchassistant.api.streamlit_app`."""

import sys

from researchassistant.api import streamlit_app as _implementation

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
