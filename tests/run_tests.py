"""Run the self-contained suite with a project-local temporary directory."""

from pathlib import Path
import tempfile
import unittest


def main():
    root = Path(__file__).resolve().parents[1]
    parent = root / ".work" / "test-runs"
    parent.mkdir(parents=True, exist_ok=True)
    previous = tempfile.tempdir
    try:
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            tempfile.tempdir = folder
            suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_*.py")
            result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        tempfile.tempdir = previous
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
