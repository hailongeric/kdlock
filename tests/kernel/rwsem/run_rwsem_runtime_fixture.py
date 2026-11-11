#!/usr/bin/env python3
"""VM-only ordinary rwsem reader/writer mechanism fixture."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_runtime_fixture import main
if __name__ == "__main__":
    raise SystemExit(main(family="rwsem"))
