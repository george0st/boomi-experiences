#!/usr/bin/env python3
"""
fileclean.py - Remove files matching a name pattern that contain dates older than N days.

Usage:
    python fileclean.py <directory> <name_pattern> <older>

Example:
    python fileclean.py /var/data "user_roles*.csv" 3
    -> Deletes files like user_roles_2026-04-09.csv, user_roles_2026-04-08.csv, etc.
"""

import sys
import fnmatch
import re
import os
from datetime import date, timedelta


DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_args():
    if len(sys.argv) != 4:
        print("Usage: fileclean.py <directory> <name_pattern> <older>")
        print("Example: fileclean.py /var/data 'user_roles*.csv' 3")
        sys.exit(1)

    directory = sys.argv[1]

    if not os.path.isdir(directory):
        print(f"Error: directory does not exist or is not a directory: '{directory}'")
        sys.exit(1)

    name_pattern = sys.argv[2]

    try:
        older = int(sys.argv[3])
        if older < 0:
            raise ValueError
    except ValueError:
        print(f"Error: <older> must be a non-negative integer, got: '{sys.argv[3]}'")
        sys.exit(1)

    return directory, name_pattern, older


def find_dates_in_filename(filename: str) -> list[date]:
    """Extract all yyyy-mm-dd dates found in a filename."""
    matches = DATE_PATTERN.findall(filename)
    dates = []
    for match in matches:
        try:
            dates.append(date.fromisoformat(match))
        except ValueError:
            pass  # Skip invalid dates like 2026-13-99
    return dates


def main():
    directory, name_pattern, older = parse_args()

    today = date.today()
    cutoff = today - timedelta(days=older)

    print(f"Today        : {today}")
    print(f"Cutoff date  : {cutoff} (files with dates older than this will be removed)")
    print(f"Directory    : {directory}")
    print(f"Pattern      : {name_pattern}")
    print()

    try:
        all_entries = os.listdir(directory)
    except OSError as e:
        print(f"Error reading directory '{directory}': {e}")
        sys.exit(1)

    matched_files = sorted(
        os.path.join(directory, f)
        for f in all_entries
        if fnmatch.fnmatch(f, name_pattern) and os.path.isfile(os.path.join(directory, f))
    )

    if not matched_files:
        print("No files matched the pattern.")
        return

    removed, skipped = 0, 0

    for filepath in matched_files:
        filename = os.path.basename(filepath)
        file_dates = find_dates_in_filename(filename)

        if not file_dates:
            print(f"  SKIP (no date found)  : {filepath}")
            skipped += 1
            continue

        # A file is deleted if ALL dates found in its name are strictly before the cutoff
        if all(d < cutoff for d in file_dates):
            try:
                os.remove(filepath)
                print(f"  DELETED               : {filepath}  (dates: {[str(d) for d in file_dates]})")
                removed += 1
            except OSError as e:
                print(f"  ERROR deleting {filepath}: {e}")
        else:
            print(f"  KEEP (recent)         : {filepath}  (dates: {[str(d) for d in file_dates]})")
            skipped += 1

    print()
    print(f"Done. Removed: {removed} file(s), Kept/Skipped: {skipped} file(s).")


if __name__ == "__main__":
    main()
