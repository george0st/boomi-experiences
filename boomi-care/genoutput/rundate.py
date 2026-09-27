#!/usr/bin/env python3
"""
rundate.py - Run a Python script with arguments, replacing <date> with the current date.

Usage:
    python rundate.py <script> [arg1] [arg2] ...

Example:
    python rundate.py abc.py myinput_<date> myoutput_<date>
    -> runs: python abc.py myinput_2026-04-12 myoutput_2026-04-12
"""

import sys
import subprocess
from datetime import date


def resolve_args(args: list[str]) -> list[str]:
    """Replace <date> placeholder with today's date in yyyy-mm-dd format."""
    today = date.today().strftime("%Y-%m-%d")
    return [arg.replace("<date>", today) for arg in args]


def main():
    if len(sys.argv) < 2:
        print("Usage: python rundate.py <script.py> [arg1] [arg2] ...")
        sys.exit(1)

    script = sys.argv[1]
    raw_args = sys.argv[2:]

    resolved_args = resolve_args(raw_args)

    command = [sys.executable, script] + resolved_args

    print(f"✅ Running: {' '.join(command)}")
    result = subprocess.run(command)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
