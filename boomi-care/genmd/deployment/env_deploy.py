#!/usr/bin/env python3
"""
env_deploy.py

Generates a Markdown (Azure DevOps wiki flavoured) report from three Boomi
platform export files:

    1. environment          -- list of Boomi environments
    2. deployed_package     -- list of package deployments per environment
    3. component_metadata   -- metadata for the components behind each package

The export files are NOT standard CSV: each line is a single Python dict
literal (Boomi's export format), with no header row. This script parses
them line by line with ast.literal_eval.

Output:
    A single Markdown file containing:
      1. An overview table of all environments (sorted alphabetically by
         name), with the number of deployed packages per component type
         (process, webservice, ...), linking to the detail section below.
      2. One detail table per environment, listing every deployed package
         (newest deployedDate first) joined with the matching
         component_metadata record (via componentId).

Usage:
    python env_deploy.py <environment_file> <deployed_package_file> \
                          <component_metadata_file> <output_md_file>
"""

import argparse
import ast
from collections import defaultdict
from datetime import datetime


def load_records(path):
    """Parse a Boomi export file where every non-empty line is a Python
    dict literal, e.g. {'@type': 'Environment', 'id': '...', ...}.

    Returns a list of dicts, in file order. Raises ValueError with the
    offending line number if a line cannot be parsed.
    """
    records = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            # tolerate an accidental trailing comma at end of line
            candidate = line[:-1].strip() if line.endswith(",") else line
            try:
                record = ast.literal_eval(candidate)
            except (ValueError, SyntaxError) as exc:
                raise ValueError(
                    f"{path}:{lineno}: could not parse line as a Python literal: {exc}"
                ) from exc
            if isinstance(record, dict):
                records.append(record)
    return records


def parse_iso_date(value):
    """Parse a Boomi ISO-8601 UTC timestamp ('YYYY-MM-DDTHH:MM:SSZ').
    Returns a datetime, or None if value is missing/unparsable."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return None


def sort_key_deployed_date(value):
    """Sort key so packages with the newest deployedDate come first.
    Missing/unparsable dates sort last (oldest)."""
    dt = parse_iso_date(value)
    return dt or datetime.min


def format_date_short(value):
    """Human readable rendering of an ISO date string WITHOUT the trailing
    'UTC' marker, for the compact detail tables. Falls back to the raw
    value if it cannot be parsed."""
    dt = parse_iso_date(value)
    if dt is None:
        return value or ""
    return dt.strftime("%Y-%m-%d %H:%M")


def md_escape(value):
    """Escape characters that would break a Markdown table cell."""
    if value is None:
        return ""
    text = str(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def html_escape(text):
    """Escape characters that would break raw HTML embedded in a table
    cell (used for the <span title="..."> tooltips)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def html_attr_escape(text):
    """Escape characters for safe use inside an HTML attribute value."""
    return html_escape(text).replace('"', "&quot;")


def bold_red(value):
    """Render a value bold and red, for the totals row of a table."""
    return f'<span style="color:red"><strong>{value}</strong></span>'


def person_with_tooltip(value):
    """Render a 'deployedBy'/'modifiedBy' value as just the part before
    '@' with the full value available as a hover tooltip."""
    if not value:
        return ""
    text = str(value)
    display = text.split("@", 1)[0]
    # keep the markdown table itself intact, then wrap in the tooltip span
    display_safe = html_escape(md_escape(display))
    full_safe = html_attr_escape(text)
    return f'<span title="{full_safe}">{display_safe}</span>'


def order_classifications(classifications):
    """Order classification groups with PROD first, then TEST, then any
    other classification values encountered (alphabetically)."""
    priority = ["PROD", "TEST"]
    ordered = [c for c in priority if c in classifications]
    ordered += sorted(c for c in classifications if c not in priority)
    return ordered


def pluralize(word):
    """Very small English pluralizer, good enough for the component type
    names actually seen in Boomi exports ('process' -> 'processes',
    'webservice' -> 'webservices')."""
    return word + "es" if word.endswith("s") else word + "s"


def parse_env_type(name):
    """Extract the 'env type' token from a Boomi environment name of the
    form '<number>-<env type>_<notice>', e.g.:
        '01-AZURE_DEV'      -> 'AZURE'
        '01-ROU_DC_DEV'     -> 'ROU'
        '03-AZURE_PROD_INTERNAL' -> 'AZURE'
    Falls back to the whole name (minus the leading '<number>-') when the
    pattern doesn't match, and to 'UNKNOWN' when the name is empty."""
    if not name:
        return "UNKNOWN"
    rest = name.split("-", 1)[1] if "-" in name else name
    env_type = rest.split("_", 1)[0]
    return env_type or "UNKNOWN"


def discover_component_types(packages):
    """Distinct componentType values found in the deployed packages, with
    the well-known 'process' / 'webservice' types first (if present),
    followed by any other types encountered, alphabetically."""
    preferred = ["process", "webservice"]
    seen = sorted({p.get("componentType") or "unknown" for p in packages})
    ordered = [t for t in preferred if t in seen]
    ordered += [t for t in seen if t not in preferred]
    return ordered


def build_report(environments, packages, components):
    comp_by_id = {c.get("componentId"): c for c in components}

    component_types = discover_component_types(packages)

    packages_by_env = defaultdict(list)
    counts_by_env_type = defaultdict(lambda: defaultdict(int))
    for p in packages:
        env_id = p.get("environmentId")
        ctype = p.get("componentType") or "unknown"
        packages_by_env[env_id].append(p)
        counts_by_env_type[env_id][ctype] += 1

    # Requirement 4: environments sorted alphabetically by name.
    sorted_envs = sorted(environments, key=lambda e: (e.get("name") or "").lower())

    # Internal links use explicit HTML anchors (<a id="...">) rather than
    # relying on auto-generated heading anchors: Azure DevOps wiki's own
    # heading-slug algorithm is inconsistent/undocumented and produced
    # dead links in the previous version of this report. Explicit anchors
    # with simple, guaranteed-safe ids are the reliable fix.
    overview_anchor = "overview"
    env_anchors = {
        env.get("id"): f"env-{idx}" for idx, env in enumerate(sorted_envs, start=1)
    }

    # Classification groups (PROD first, then TEST, then anything else),
    # shared by the section 1 summary table and the section 2 subsections.
    classifications_present = {env.get("classification") or "UNKNOWN" for env in sorted_envs}
    ordered_classifications = order_classifications(classifications_present)
    envs_by_classification = {
        classification: [
            env for env in sorted_envs
            if (env.get("classification") or "UNKNOWN") == classification
        ]
        for classification in ordered_classifications
    }

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("# Boomi Environment Deployment Report")
    lines.append("")
    lines.append(
        f"*Generated: {generated_at} — from {len(environments)} environment(s), "
        f"{len(packages)} deployed package(s) and "
        f"{len(components)} component metadata record(s).*"
    )
    lines.append("")
    lines.append("[[_TOC_]]")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ---------------------------------------------------------------
    # 1. Overview table
    # ---------------------------------------------------------------
    lines.append(f'<a id="{overview_anchor}"></a>')
    lines.append("")
    lines.append("## 1. Overview by environment")
    lines.append("")

    # ---- 1.1 Summary by classification (environment count + type sums) ----
    lines.append("### 1.1 Environment summary")
    lines.append("")

    # -- 1.1a. By classification only --
    plain_stats_header = ["Environment type", "Environment amount"] + [
        pluralize(t).capitalize() for t in component_types
    ]
    lines.append("| " + " | ".join(f"**{h}**" for h in plain_stats_header) + " |")
    lines.append("|" + "|".join(["---"] * len(plain_stats_header)) + "|")

    grand_type_sums = defaultdict(int)
    grand_env_count = 0
    for classification in ordered_classifications:
        group_envs = envs_by_classification[classification]
        grand_env_count += len(group_envs)
        type_sums = defaultdict(int)
        for env in group_envs:
            env_counts = counts_by_env_type.get(env.get("id"), {})
            for t in component_types:
                type_sums[t] += env_counts.get(t, 0)
                grand_type_sums[t] += env_counts.get(t, 0)
        cells = [md_escape(classification), f"{len(group_envs)}x"]
        cells += [str(type_sums[t]) for t in component_types]
        lines.append("| " + " | ".join(cells) + " |")

    # totals row
    plain_totals_cells = [bold_red("Summary"), bold_red(f"{grand_env_count}x")]
    plain_totals_cells += [bold_red(grand_type_sums[t]) for t in component_types]
    lines.append("| " + " | ".join(plain_totals_cells) + " |")

    lines.append("")

    # -- 1.1b. By classification AND env location --
    stats_header = ["Environment type", "Environment location", "Environment amount"] + [
        pluralize(t).capitalize() for t in component_types
    ]
    lines.append("| " + " | ".join(f"**{h}**" for h in stats_header) + " |")
    lines.append("|" + "|".join(["---"] * len(stats_header)) + "|")

    for classification in ordered_classifications:
        group_envs = envs_by_classification[classification]

        # Further split each classification by "env type", parsed from the
        # environment name ('<number>-<env type>_<notice>', e.g.
        # '01-AZURE_DEV' -> 'AZURE', '01-ROU_DC_DEV' -> 'ROU'), so it's
        # visible how many PROD AZURE / PROD ROU / ... environments exist.
        env_types_in_group = sorted(
            {parse_env_type(env.get("name")) for env in group_envs},
            key=str.lower,
        )
        for env_type in env_types_in_group:
            subgroup = [
                env for env in group_envs
                if parse_env_type(env.get("name")) == env_type
            ]
            type_sums = defaultdict(int)
            for env in subgroup:
                env_counts = counts_by_env_type.get(env.get("id"), {})
                for t in component_types:
                    type_sums[t] += env_counts.get(t, 0)
            cells = [
                md_escape(classification),
                md_escape(env_type),
                f"{len(subgroup)}x",
            ]
            cells += [str(type_sums[t]) for t in component_types]
            lines.append("| " + " | ".join(cells) + " |")

    # totals row
    totals_cells = [bold_red("Summary"), "", bold_red(f"{grand_env_count}x")]
    totals_cells += [bold_red(grand_type_sums[t]) for t in component_types]
    lines.append("| " + " | ".join(totals_cells) + " |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # ---- 1.2 Full list of environments ----
    lines.append("### 1.2 Environments")
    lines.append("")
    header = ["Environment name", "Environment ID", "Classification"] + [
        t.capitalize() for t in component_types
    ]
    lines.append("| " + " | ".join(f"**{h}**" for h in header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    env_list_type_sums = defaultdict(int)
    for env in sorted_envs:
        env_id = env.get("id")
        env_name = env.get("name") or ""
        anchor = env_anchors[env_id]
        type_counts = counts_by_env_type.get(env_id, {})
        cells = [
            f"[{md_escape(env_name)}](#{anchor})",
            md_escape(env_id),
            md_escape(env.get("classification")),
        ]
        cells += [str(type_counts.get(t, 0)) for t in component_types]
        for t in component_types:
            env_list_type_sums[t] += type_counts.get(t, 0)
        lines.append("| " + " | ".join(cells) + " |")

    # totals row
    totals_cells = [bold_red("Summary"), "", ""]
    totals_cells += [bold_red(env_list_type_sums[t]) for t in component_types]
    lines.append("| " + " | ".join(totals_cells) + " |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # ---------------------------------------------------------------
    # 2. Per-environment detail tables
    # ---------------------------------------------------------------
    lines.append("## 2. Deployed packages by environment")
    lines.append("")

    # Final column order/names per requirements: the old "Component type"
    # (from deployed_package.componentType) survives renamed as "Type";
    # the old plain "Type" (from component_metadata.type) and "Package
    # version" columns are dropped entirely.
    detail_header = [
        "Folder",
        "Name",
        "Ver",
        "Type",
        "Deployed",
        "Deployed by",
        "Modified",
        "Modified by",
    ]

    # Section 2 is split into subsections by environment classification --
    # PROD first, then TEST, then any other value found (same grouping
    # used for the section 1 summary table above).
    for group_idx, classification in enumerate(ordered_classifications, start=1):
        group_envs = envs_by_classification[classification]

        lines.append(f"### 2.{group_idx} {classification}")
        lines.append("")

        for env_idx, env in enumerate(group_envs, start=1):
            env_id = env.get("id")
            env_name = env.get("name") or ""
            anchor = env_anchors[env_id]
            heading = f"2.{group_idx}.{env_idx} {env_name}"

            lines.append(f'<a id="{anchor}"></a>')
            lines.append("")
            lines.append(f"#### {heading}")
            lines.append("")

            type_counts = counts_by_env_type.get(env_id, {})
            type_count_text = "  ".join(
                f"**{t.capitalize()}:** {type_counts.get(t, 0)}" for t in component_types
            )
            lines.append(
                f"Environment ID: `{env_id}`  |  "
                f"Classification: {md_escape(env.get('classification'))}  |  "
                f"{type_count_text}"
            )
            lines.append("")

            env_packages = sorted(
                packages_by_env.get(env_id, []),
                key=lambda p: sort_key_deployed_date(p.get("deployedDate")),
                reverse=True,
            )

            if not env_packages:
                lines.append("_No deployed packages found for this environment._")
                lines.append("")
                lines.append("---")
                lines.append("")
                continue

            lines.append("<details>")
            lines.append(
                f"<summary>Show {len(env_packages)} deployed package"
                f"{'s' if len(env_packages) != 1 else ''} (click to expand)</summary>"
            )
            lines.append("")
            lines.append('<div style="font-size: 80%;">')
            lines.append("")
            lines.append("| " + " | ".join(f"**{h}**" for h in detail_header) + " |")
            lines.append("|" + "|".join(["---"] * len(detail_header)) + "|")

            for p in env_packages:
                comp = comp_by_id.get(p.get("componentId"), {})
                row = [
                    md_escape(comp.get("folderName")),
                    md_escape(comp.get("name")),
                    md_escape(p.get("componentVersion")),
                    md_escape(p.get("componentType")),
                    format_date_short(p.get("deployedDate")),
                    person_with_tooltip(p.get("deployedBy")),
                    format_date_short(comp.get("modifiedDate")),
                    person_with_tooltip(comp.get("modifiedBy")),
                ]
                lines.append("| " + " | ".join(row) + " |")

            lines.append("")
            lines.append("</div>")
            lines.append("")
            lines.append("</details>")
            lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Markdown deployment report from Boomi 'environment', "
            "'deployed_package' and 'component_metadata' export files."
        )
    )
    parser.add_argument("environment_file", help="Path to the environment export file")
    parser.add_argument(
        "deployed_package_file", help="Path to the deployed_package export file"
    )
    parser.add_argument(
        "component_metadata_file", help="Path to the component_metadata export file"
    )
    parser.add_argument("output_file", help="Path to the Markdown file to generate")
    args = parser.parse_args()

    environments = load_records(args.environment_file)
    packages = load_records(args.deployed_package_file)
    components = load_records(args.component_metadata_file)

    report = build_report(environments, packages, components)

    with open(args.output_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report written to: {args.output_file}")
    print(f"  environments:              {len(environments)}")
    print(f"  deployed packages:         {len(packages)}")
    print(f"  component metadata records: {len(components)}")


if __name__ == "__main__":
    main()
