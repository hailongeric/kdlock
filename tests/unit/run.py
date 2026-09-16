"""Run one selected Python unit driver; never implicitly run the inventory."""

import argparse
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unit import configure_paths

ROOT = Path(__file__).resolve().parent


def select(name):
    # Accept a group/path or a unique old basename for existing PY_TESTS uses.
    inventory = sorted(ROOT.glob("*/test_*.py"))
    if Path(name).name == name:
        matches = [path for path in inventory if path.name == name]
    else:
        matches = [path for path in inventory if path == (ROOT / name).resolve()]
    if len(matches) != 1:
        raise ValueError(f"expected one unit test for {name!r}; use --list")
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list without running")
    parser.add_argument("test", nargs="?", help="group/test_name.py or test_name.py")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="arguments for the test")
    args = parser.parse_args()
    if args.list or args.test is None:
        for path in sorted(ROOT.glob("*/test_*.py")):
            print(path.relative_to(ROOT))
        return
    try:
        path = select(args.test)
    except ValueError as error:
        parser.error(str(error))
    configure_paths()
    sys.argv = [str(path), *args.args]
    runpy.run_path(str(path), run_name="__main__")


if __name__ == "__main__":
    main()
