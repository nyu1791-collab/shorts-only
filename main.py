"""Shorts-only command entry point; implementation lives in src/shorts_only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from shorts_only.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
