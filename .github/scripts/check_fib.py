"""Run hello.py and verify its output is the first 10 Fibonacci numbers.

Tolerant comparison: ignores blank lines, trailing whitespace, and
mixed CRLF/LF endings. Dumps full diagnostics on mismatch so the next
CI run reveals the failure mode without re-deploy.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXPECTED = ["0", "1", "1", "2", "3", "5", "8", "13", "21", "34"]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_fib.py <hello.py>", file=sys.stderr)
        return 2
    script = Path(sys.argv[1]).resolve()
    if not script.exists():
        print(f"FAIL: {script} does not exist")
        return 1

    print(f"=== running {script} ===")
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    print(f"return code: {proc.returncode}")
    print("=== stdout (repr) ===")
    print(repr(proc.stdout))
    print("=== stderr ===")
    print(proc.stderr)
    print("=== stdout (rendered) ===")
    print(proc.stdout)
    print("=== expected ===")
    print("\n".join(EXPECTED))

    if proc.returncode != 0:
        print(f"FAIL: hello.py exited non-zero ({proc.returncode})")
        return 1

    actual = [
        line.strip()
        for line in proc.stdout.splitlines()
        if line.strip()
    ]
    if actual != EXPECTED:
        print(f"FAIL: actual={actual}\n      expected={EXPECTED}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
