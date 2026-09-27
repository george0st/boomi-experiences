#!/usr/bin/env python3
"""
Convert users_roles CSV file to a Markdown file with a formatted table.
The last column (roles) is kept as a single cell with no surrounding quotes.
Usage: python convert_to_markdown.py <input_file> [output_file]
"""

import sys
import os
from datetime import datetime


def csv_to_markdown(input_path: str, output_path: str) -> None:
    rows = []

    with open(input_path, encoding="utf-8") as f:
        raw_lines = [line.rstrip("\n") for line in f if line.strip()]

    # Parse header
    headers = [h.strip() for h in raw_lines[0].split(",")]
    num_cols = len(headers)

    for line in raw_lines[1:]:
        # Split only on the first (num_cols - 1) commas so the roles column
        # (which itself contains commas) is kept intact as one value.
        parts = line.split(",", num_cols - 1)
        cells = [p.strip().strip('"').replace("_", "\\_") for p in parts]
        # Pad if a row is shorter than expected
        cells += [""] * (num_cols - len(cells))
        rows.append(cells)

    # Build markdown
    lines = []

    base_name = os.path.basename(input_path)
    lines.append("# Users & Roles Report")
    lines.append("")
    lines.append(f"**Source file:** `{base_name}`  ")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append(f"**Total users:** {len(rows)}")
    lines.append("")

    # Column widths for neat alignment
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < num_cols:
                col_widths[i] = max(col_widths[i], len(cell))

    def fmt_row(cells):
        padded = [cells[i].ljust(col_widths[i]) for i in range(len(cells))]
        return "| " + " | ".join(padded) + " |"

    def separator_row():
        return "| " + " | ".join("-" * w for w in col_widths) + " |"

    lines.append(fmt_row(headers))
    lines.append(separator_row())
    for row in rows:
        lines.append(fmt_row(row))

    lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ Markdown file written to: {output_path}")
    print(f"   {len(rows)} users, {num_cols} columns")


def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_to_markdown.py <input_file> [output_file]")
        print("Example: python convert_to_markdown.py users_roles_2026-03-28.txt users_roles.md")
        sys.exit(1)

    input_path = sys.argv[1]

    if not os.path.isfile(input_path):
        print(f"❌ File not found: {input_path}")
        sys.exit(1)

    output_path = sys.argv[2] if len(sys.argv) >= 3 else os.path.splitext(input_path)[0] + ".md"

    csv_to_markdown(input_path, output_path)


if __name__ == "__main__":
    main()
