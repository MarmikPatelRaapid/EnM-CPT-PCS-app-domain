import sys
from pathlib import Path

# Ensure the project root is on sys.path so `import config` and `import src.*` both work
sys.path.insert(0, str(Path(__file__).parent))
