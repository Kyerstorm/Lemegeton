"""Run every Custom Roles offline test and print a summary.

    .venv/Scripts/python.exe tests/custom_roles/run_all.py          # Windows
    .venv/bin/python tests/custom_roles/run_all.py                  # Linux/macOS

Add -v to see every PASS line. Exit code is 0 only if everything passed.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = sorted(HERE.glob("test_*.py"))


def main() -> int:
    verbose = "-v" in sys.argv
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # test labels contain emoji
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    failed_files = []
    for test in TESTS:
        proc = subprocess.run(
            [sys.executable, str(test)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
        )
        lines = (proc.stdout + proc.stderr).splitlines()
        summary = next((l for l in reversed(lines) if l.endswith(" passed")), "no summary (crashed?)")
        print(f"{'OK  ' if proc.returncode == 0 else 'FAIL'} {test.name:32} {summary}")
        shown = [l for l in lines if l.startswith("FAIL ") or l.startswith("REFUSING")
                 or (verbose and l.startswith("PASS "))]
        if proc.returncode != 0 and not shown:
            shown = lines[-25:]  # a crash: show the traceback
        for line in shown:
            print("     " + line)
        if proc.returncode != 0:
            failed_files.append(test.name)
    print()
    print("All Custom Roles tests passed." if not failed_files else f"Failed: {', '.join(failed_files)}")
    return 1 if failed_files else 0


if __name__ == "__main__":
    sys.exit(main())
