"""Pytest config — makes the mneme package importable from tests/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
