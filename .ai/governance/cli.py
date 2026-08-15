"""
Entry point for governo CLI.

Usage:
    python .ai/governance/cli.py <command> [args]

Or use the wrapper script:
    .ai/governance/governo.sh audit
"""

import sys
from pathlib import Path

# Ensure the governance package is importable
_GOV_DIR = Path(__file__).resolve().parent  # .ai/governance/
sys.path.insert(0, str(_GOV_DIR.parent))    # .ai/

# Import the governo module directly
sys.path.insert(0, str(_GOV_DIR))

# When imported as 'governance.governo', we need the parent (.ai) on the path
# and the governance dir to be treated as a package
from governance.governo import main

if __name__ == "__main__":
    sys.exit(main())
