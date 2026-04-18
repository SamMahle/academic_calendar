import sys
from pathlib import Path

# Make the tests/ directory importable so test modules can do:
#   from data_helpers import classic_theme
sys.path.insert(0, str(Path(__file__).parent))
