"""Compatibility entry point for the organized ResearchAssistant CLI."""

import sys

from researchassistant.runtime import cli as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
