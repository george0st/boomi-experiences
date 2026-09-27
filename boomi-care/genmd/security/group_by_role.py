import csv
import os
import re
import argparse
from datetime import date, datetime
from collections import defaultdict


def parse_args():
    today = date.today().strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(
        description="Group users by role from a CSV/TXT file."
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Path to the input file (CSV/TXT with header: userId,firstName,lastName,roles)"
    )
    parser.add_argument(
        "-o", "--output",
        default=f"users_roles_groupby_role {today}",
        help="Output file path/name WITHOUT extension (default: users_roles_groupby_role <date>)"
    )
    parser.add_argument(
        "-t", "--toc",
        choices=["tag", "generated"],
        default="generated",
        help="Table of Contents mode: 'tag' inserts [[_TOC_]], 'generated' builds TOC from headings (default: generated)"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["txt", "md"],
        default="txt",
        help="Output format: txt (CSV-style) or md (Markdown). Default: txt"
    )
    return parser.parse_args()


def load_and_group(input_path):
    """Load input file and return users grouped by role."""
    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        users = list(reader)

    role_map = defaultdict(list)
    for user in users:
        roles = [r.strip() for r in user["roles"].split(",")]
        for role in roles:
            if role:
                role_map[role].append({
                    "userId":    user["userId"].strip(),
                    "firstName": user["firstName"].strip(),
                    "lastName":  user["lastName"].strip(),
                })
    return role_map


def write_txt(role_map, output_path):
    """Write grouped data as CSV-style TXT."""
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["role", "userId", "firstName", "lastName"])
        for role in sorted(role_map.keys()):
            members = role_map[role]
            writer.writerow([f"# {role} — {len(members)} user(s)"])
            for m in members:
                writer.writerow([role, m["userId"], m["firstName"], m["lastName"]])
            writer.writerow([])


def write_md(role_map, output_path, input_path, toc_mode):
    """Write grouped data as Markdown."""
    total_roles = len(role_map)
    total_users = len({u["userId"] for members in role_map.values() for u in members})
    input_filename = os.path.basename(input_path)
    sorted_roles = sorted(role_map.keys())

    def esc(text):
        return text.replace("_", r"\_")

    def anchor(role):
        slug = role.lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s]+", "-", slug)
        return slug

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Users grouped by Role\n\n")
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"**Source file:** `{input_filename}`  \n")
        f.write(f"**Generated:** {generated_at}  \n")
        f.write(f"**Total users:** {total_users}  \n")
        f.write(f"**Total roles:** {total_roles}\n\n")

        if toc_mode == "tag":
            f.write("[[_TOC_]]\n\n")
            for role in sorted_roles:
                members = role_map[role]
                f.write(f"## `{role}`\n\n")
                f.write(f"**Total users: {len(members)}**\n\n")
                f.write("| userId | firstName | lastName |\n")
                f.write("|--------|-----------|----------|\n")
                for m in members:
                    f.write(f"| {esc(m['userId'])} | {esc(m['firstName'])} | {esc(m['lastName'])} |\n")
                f.write("\n")
        else:
            f.write("## Table of Contents\n\n")
            for role in sorted_roles:
                f.write(f"- [`{role}`](#`{anchor(role)}`)\n")
            f.write("\n")
            for role in sorted_roles:
                members = role_map[role]
                f.write(f"## `{role}`\n\n")
                f.write(f"**Total users: {len(members)}**\n\n")
                f.write("| userId | firstName | lastName |\n")
                f.write("|--------|-----------|----------|\n")
                for m in members:
                    f.write(f"| {esc(m['userId'])} | {esc(m['firstName'])} | {esc(m['lastName'])} |\n")
                f.write("\n")


def main():
    args = parse_args()
    input_path = args.input
    output_path = f"{args.output}.{args.format}"

    print(f"Loading input:  {input_path}")
    role_map = load_and_group(input_path)

    print(f"Writing output: {output_path}  (format: {args.format})")
    if args.format == "txt":
        write_txt(role_map, output_path)
    else:
        write_md(role_map, output_path, input_path, args.toc)

    total_users = len({u["userId"] for members in role_map.values() for u in members})
    print(f"Done. Total roles found: {len(role_map)} | Total users found: {total_users}")


if __name__ == "__main__":
    main()
