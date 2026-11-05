#!/usr/bin/env python3
"""Convenience runner for release artifact builder."""
import subprocess
import sys
from pathlib import Path

RELEASE_SCRIPT = Path(__file__).resolve().parent.parent / "release" / "build-production-artifact.py"

if __name__ == "__main__":
    result = subprocess.run([sys.executable, str(RELEASE_SCRIPT)])
    sys.exit(result.returncode)
