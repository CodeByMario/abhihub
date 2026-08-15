"""
Root conftest for .ai/ tests — ensures the governance package is importable.
"""
import sys
from pathlib import Path

# Add .ai/ to sys.path so 'governance' package is importable
_AI_DIR = Path(__file__).resolve().parent  # .ai/
if str(_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_DIR))
