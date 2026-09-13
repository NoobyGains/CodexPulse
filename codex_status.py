#!/usr/bin/env python3
"""Run CodexPulse directly from a checkout; no pip install required."""
from codexpulse.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
