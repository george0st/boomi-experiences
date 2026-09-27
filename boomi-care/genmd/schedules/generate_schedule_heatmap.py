#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_schedule_heatmap.py
=============================

Generates a standalone production HTML page ("Variant E" - hourly grid /
heatmap of scheduled Boomi processes) from two real Boomi exports:

  1) JSON export of process schedules (ProcessSchedules), e.g. process_schedules_*.json
  2) CSV export of component metadata (ComponentMetadata), e.g. component_metadata_*.csv
     -- NOTE: despite the .csv extension, each line of this file is a Python
     dict literal (single quotes, True/False), not a standard comma-separated
     CSV with columns. The script parses it with ast.literal_eval.

The output is a single self-contained `.html` file with the data baked in
(no external dependencies, no CDN, works even opened directly from disk via
file://).

Decisions confirmed by the user (Jiri Steuer, Dr. Max) for this specific
data set - see the info box in the header of the generated page:
  - Time zone: the input JSON schedules have no timezone field. The user
    confirmed that all times are in UTC and should be displayed as-is
    (no shift).
  - Day-of-week numbering: the `daysOfWeek` field in the JSON uses the
    native Quartz/Boomi convention (1=Sunday ... 7=Saturday). The script
    remaps it to the ISO convention (1=Monday ... 7=Sunday) used by the
    page's data model (`daysOfWeek` in the `processes` array).

Usage:
    python3 generate_schedule_heatmap.py \
        --json process_schedules.json \
        --csv component_metadata.csv \
        --out schedule-heatmap.html

Without arguments the script falls back to default file names in the
current directory.
"""

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration of decisions confirmed by the user for this data set
# ---------------------------------------------------------------------------

# Quartz/Boomi (1=Sun..7=Sat) -> ISO (1=Mon..7=Sun)
QUARTZ_TO_ISO = {1: 7, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}

TIMEZONE_LABEL = "UTC"
TIMEZONE_NOTE = (
    "The input data (process_schedules) does not include a timezone field "
    "on any schedule. When asked, the user confirmed that all times should "
    "be displayed as UTC, unchanged."
)
DOW_CONVENTION_NOTE = (
    "The daysOfWeek field in the JSON export uses the native Quartz/Boomi "
    "numbering (1=Sunday .. 7=Saturday) - confirmed by the user. The script "
    "remaps it to the ISO numbering (1=Monday .. 7=Sunday) used by the "
    "page's data model."
)

ENV_CLASSIFICATION_FILTER = "PROD"

DAY_NAMES_ISO = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # index 0 => ISO day 1


# ---------------------------------------------------------------------------
# Low-level parser for cron-like fields (minutes / hours / daysOfWeek)
# ---------------------------------------------------------------------------

def parse_numeric_field(expr, lo, hi):
    """Expands a cron-like field (e.g. '0-59/4', '00', '5,10,15', '*') into a
    sorted set of integers within [lo, hi]."""
    if expr is None:
        return set(range(lo, hi + 1))
    expr = str(expr).strip()
    if expr == "":
        return set(range(lo, hi + 1))

    out = set()
    for part in expr.split(","):
        part = part.strip()
        if part == "":
            continue
        if part == "*":
            out.update(range(lo, hi + 1))
            continue
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
            if base == "*":
                start, end = lo, hi
            elif "-" in base:
                start, end = (int(x) for x in base.split("-", 1))
            else:
                start, end = int(base), hi
            out.update(range(start, end + 1, step))
            continue
        if "-" in part:
            start, end = (int(x) for x in part.split("-", 1))
            out.update(range(start, end + 1))
            continue
        out.add(int(part))
    return {v for v in out if lo <= v <= hi}


def parse_days_of_week(expr):
    """Returns (iso_days: set[1..7], was_wildcard: bool)."""
    if expr is None:
        return set(range(1, 8)), True
    expr = str(expr).strip()
    if expr == "" or expr == "*":
        return set(range(1, 8)), True
    iso_days = set()
    for part in expr.split(","):
        part = part.strip()
        if part == "":
            continue
        q = int(part)
        iso_days.add(QUARTZ_TO_ISO.get(q, q))
    if not iso_days:
        return set(range(1, 8)), True
    return iso_days, False


# ---------------------------------------------------------------------------
# Generating a human-readable schedule description (schedText)
# ---------------------------------------------------------------------------

def format_hhmm(t):
    return f"{t // 60:02d}:{t % 60:02d}"


def days_label(days_iso_sorted):
    s = set(days_iso_sorted)
    if s == set(range(1, 8)):
        return None  # full week -> no prefix, just "Daily"
    days_sorted = sorted(s)
    ranges = []
    start = prev = days_sorted[0]
    for d in days_sorted[1:]:
        if d == prev + 1:
            prev = d
        else:
            ranges.append((start, prev))
            start = prev = d
    ranges.append((start, prev))
    parts = []
    for a, b in ranges:
        if a == b:
            parts.append(DAY_NAMES_ISO[a - 1])
        else:
            parts.append(f"{DAY_NAMES_ISO[a - 1]}–{DAY_NAMES_ISO[b - 1]}")
    return ", ".join(parts)


def describe_time_pattern(times_sorted):
    if len(times_sorted) == 1:
        return f"at {format_hhmm(times_sorted[0])}"

    by_hour = {}
    for t in times_sorted:
        h, m = divmod(t, 60)
        by_hour.setdefault(h, []).append(m)
    hours_sorted = sorted(by_hour)
    minute_sets = [tuple(sorted(v)) for v in by_hour.values()]
    uniform = len(set(minute_sets)) == 1
    contiguous = hours_sorted == list(range(hours_sorted[0], hours_sorted[-1] + 1))

    if uniform:
        mins = minute_sets[0]
        if len(mins) == 1:
            timepart = f"every hour at :{mins[0]:02d}"
        else:
            diffs = sorted({mins[i + 1] - mins[i] for i in range(len(mins) - 1)})
            if len(diffs) == 1 and mins[0] + diffs[0] * (len(mins) - 1) == mins[-1]:
                step = diffs[0]
                off = mins[0]
                timepart = f"every {step} min" + (f" (offset :{off:02d})" if off else "")
            else:
                timepart = "at :" + ", :".join(f"{m:02d}" for m in mins)

        if contiguous and hours_sorted[0] == 0 and hours_sorted[-1] == 23:
            return timepart
        elif contiguous:
            return f"{timepart}, {hours_sorted[0]:02d}:00–{hours_sorted[-1]:02d}:59"
        else:
            hrs = ", ".join(f"{h:02d}h" for h in hours_sorted)
            return f"{timepart} ({hrs})"
    else:
        if len(times_sorted) <= 6:
            return "at " + ", ".join(format_hhmm(t) for t in times_sorted)
        head = ", ".join(format_hhmm(t) for t in times_sorted[:6])
        return f"at {head} and {len(times_sorted) - 6} more"


def build_schedtext(times, days_iso):
    times_sorted = sorted(set(times))
    dlabel = days_label(sorted(set(days_iso)))
    tpart = describe_time_pattern(times_sorted)
    prefix = dlabel if dlabel is not None else "Daily"
    return f"{prefix}, {tpart}"


# ---------------------------------------------------------------------------
# Loading inputs
# ---------------------------------------------------------------------------

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_component_metadata_csv(path):
    """The file contains a Python dict literal on every line (not a regular
    CSV)."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(ast.literal_eval(line))
            except Exception as ex:
                print(f"WARN: could not parse line {i} in {path}: {ex}", file=sys.stderr)
    return {r["componentId"]: r for r in rows if "componentId" in r}


# ---------------------------------------------------------------------------
# ETL: JSON + CSV -> processes[]
# ---------------------------------------------------------------------------

def build_processes(schedule_data, component_map):
    processes = []
    warnings = []
    edge_cases = []  # daysOfMonth/months exceptions, if any
    envs_used = []
    next_id = 1

    items = schedule_data.get("itms", schedule_data.get("items", []))

    for env in items:
        env_name = env.get("envName", "?")
        env_class = env.get("envClassification", "")
        if env_class != ENV_CLASSIFICATION_FILTER:
            continue
        envs_used.append(env_name)

        for detail in env.get("detail", []):
            process_id = detail.get("processId")
            atom_id = detail.get("atomId")
            schedule_rows = detail.get("Schedule", [])
            if not schedule_rows:
                continue
            # ProcessScheduleStatus flag. Older exports may not include it -
            # treat those as enabled (matches prior behaviour before this
            # field existed).
            enabled = bool(detail.get("enabled", True))

            meta = component_map.get(process_id)
            if meta is None:
                warnings.append(
                    f"processId {process_id} not found in CSV component "
                    f"metadata - process will be skipped."
                )
                continue
            process_name = meta.get("name", process_id)
            folder_name = meta.get("folderName") or ""

            # group Schedule rows by (ISO daysOfWeek) set
            groups = {}  # key: frozenset(iso_days) -> list of (minutes_set, hours_set)
            for sch in schedule_rows:
                iso_days, _wildcard = parse_days_of_week(sch.get("daysOfWeek"))
                minutes = parse_numeric_field(sch.get("minutes"), 0, 59)
                hours = parse_numeric_field(sch.get("hours"), 0, 23)
                dom = sch.get("daysOfMonth")
                months = sch.get("months")
                if dom not in (None, "*", "1-31/1") or months not in (None, "*"):
                    edge_cases.append({
                        "process": process_name,
                        "atom": env_name,
                        "daysOfMonth": dom,
                        "months": months,
                    })
                key = frozenset(iso_days)
                groups.setdefault(key, []).append((minutes, hours))

            multi_group = len(groups) > 1
            for iso_days_fs, entries in groups.items():
                times = set()
                for minutes, hours in entries:
                    for h in hours:
                        for m in minutes:
                            times.add(h * 60 + m)
                if not times:
                    continue
                iso_days_sorted = sorted(iso_days_fs)
                name = process_name
                if multi_group:
                    suffix = days_label(iso_days_sorted) or "Daily"
                    name = f"{process_name} ({suffix})"

                processes.append({
                    "id": next_id,
                    "name": name,
                    "group": folder_name,
                    "atom": env_name,
                    "daysOfWeek": iso_days_sorted,
                    "times": sorted(times),
                    "schedText": build_schedtext(times, iso_days_sorted),
                    "enabled": enabled,
                })
                next_id += 1

    return processes, warnings, edge_cases, sorted(set(envs_used))


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Boomi – Scheduled Process Heatmap (PROD)</title>
<style>
__CSS__
</style>
</head>
<body class="compact">
<header class="page-header">
  <h1>Scheduled Process Heatmap</h1>
  <p class="meta">
    Generated: <strong>__GENERATED_AT__</strong>
    &middot; Time zone: <strong>__TZ_LABEL__</strong>
    &middot; Environment: <strong>PROD</strong> (__ENV_LIST__)
    &middot; <strong>__PROCESS_COUNT__/__DISABLED_COUNT__ processes</strong> (__SCHEDULE_COUNT__ total entries)
  </p>
</header>

<section class="grid-section">
  <div class="grid-main">
    <div class="grid-wrap">
      <canvas id="heat"></canvas>
      <div id="tooltip" class="tooltip hidden"></div>
    </div>
    <div class="grid-sidebar">
      <div class="day-switch" id="daySwitch" role="group" aria-label="Day of week selector"></div>
      <div class="scale-switch">
        <label class="switch-label">
          <input type="checkbox" id="colorToggle" checked>
          <span>Heat scale</span>
        </label>
        <div class="legend" id="legend">
          <span class="legend-label" id="legendMin">0</span>
          <div class="legend-bar" id="legendBar"></div>
          <span class="legend-label" id="legendMax">0</span>
        </div>
      </div>
      <label class="switch-label">
        <input type="checkbox" id="showDisabledToggle">
        <span>Show disabled processes</span>
      </label>
      <div class="scrubber-row">
        <div class="chip-group" id="quickChips"></div>
        <div class="time-control">
          <button type="button" id="stepMinus" class="step-btn" aria-label="One minute earlier">&minus;</button>
          <input type="time" id="timeInput" step="60">
          <button type="button" id="stepPlus" class="step-btn" aria-label="One minute later">&plus;</button>
          <button type="button" id="clearSelection" class="clear-btn">Clear selection</button>
        </div>
        <label class="switch-label compact-label">
          <input type="checkbox" id="timeMatchOnly" checked>
          <span>Time-match only</span>
        </label>
      </div>
    </div>
  </div>
</section>

<section class="table-section">
  <div class="table-toolbar">
    <input type="search" id="searchBox" placeholder="Search process, group, atom, schedule&hellip;" aria-label="Table search">
    <label class="switch-label">
      <input type="checkbox" id="compactToggle" checked>
      <span>Compact table</span>
    </label>
    <span class="row-count" id="rowCount"></span>
  </div>
  <div class="table-scroll">
    <table id="procTable">
      <thead>
        <tr>
          <th data-key="enabled" class="enabled-col" title="Enabled">On</th>
          <th data-key="name">Process</th>
          <th data-key="group">Group</th>
          <th data-key="atom">Atom / Runtime</th>
          <th data-key="schedText">Schedule</th>
          <th data-key="firstTime">Run times</th>
        </tr>
      </thead>
      <tbody id="procTableBody"></tbody>
    </table>
  </div>
</section>

__EDGE_CASE_SECTION__

<footer class="page-footer">
  <details class="assumptions">
    <summary>Data notes and processing assumptions</summary>
    <ul>
      <li>Density of scheduled integration process runs over time, by minute, for a selected day of the week.</li>
      <li>__TZ_NOTE__</li>
      <li>__DOW_NOTE__</li>
      <li>Only environments classified as PROD are included; other classifications (e.g. TEST) are excluded from the view.</li>
      <li>__ENABLED_NOTE__</li>
      __EDGE_CASE_NOTE__
    </ul>
  </details>
</footer>

<script>
const PROCESSES = __PROCESSES_JSON__;
const EDGE_CASES = __EDGE_CASES_JSON__;
__JS__
</script>
</body>
</html>
"""

CSS_TEMPLATE = r"""
:root {
  --bg: #f7f8fa;
  --surface: #ffffff;
  --border: #e2e5ea;
  --text: #1a2130;
  --text-muted: #5b6472;
  --accent: #1e3a8a;
  --accent-bg: #eef2ff;
  --today-dot: #d03b3b;
  --radius: 10px;
  font-size: 14px;
}
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
body { padding: 12px 20px 16px; max-width: 1280px; margin: 0 auto; }

.page-header h1 { margin: 0 0 4px; font-size: 20px; letter-spacing: -0.01em; }
.page-header .meta { margin: 0 0 6px; color: var(--text-muted); font-size: 12.5px; }
.page-header .meta strong { color: var(--text); }
details.assumptions {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 5px 12px; margin-bottom: 8px; font-size: 12.5px; color: var(--text-muted);
}
details.assumptions summary { cursor: pointer; color: var(--text); font-weight: 600; padding: 3px 0; }
details.assumptions ul { margin: 6px 0 4px; padding-left: 20px; }
details.assumptions li { margin-bottom: 3px; }

.day-btn {
  border: 1px solid var(--border); background: var(--surface); color: var(--text);
  padding: 6px 10px; border-radius: 8px; font-size: 12.5px; cursor: pointer; position: relative;
  font-weight: 600; transition: background .1s, color .1s;
}
.day-btn:hover { background: var(--accent-bg); }
.day-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.day-btn .today-dot {
  position: absolute; top: -4px; right: -4px; width: 8px; height: 8px; border-radius: 50%;
  background: var(--today-dot); border: 1.5px solid var(--surface);
}
.switch-label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-muted); cursor: pointer; user-select: none; }
.switch-label input { cursor: pointer; }
.legend { display: flex; align-items: center; gap: 6px; }
.legend-bar { width: 120px; height: 12px; border-radius: 6px; border: 1px solid var(--border); }
.legend-label { font-size: 12px; color: var(--text-muted); min-width: 14px; text-align: center; }

section.grid-section {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 10px 14px; margin-bottom: 8px;
}
.grid-main { display: flex; align-items: flex-start; gap: 18px; flex-wrap: wrap; }
.grid-wrap { position: relative; overflow-x: auto; flex: 0 0 auto; }
.grid-sidebar {
  display: flex; flex-direction: column; gap: 12px; flex: 1 1 160px; min-width: 150px;
  padding-left: 16px; border-left: 1px solid var(--border); align-self: stretch; justify-content: flex-start;
}
.grid-sidebar .day-switch { display: flex; flex-wrap: wrap; gap: 6px; }
.grid-sidebar .scale-switch { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; }
#heat { display: block; cursor: crosshair; touch-action: none; }
.tooltip {
  position: fixed; pointer-events: none; background: #1a2130; color: #fff; font-size: 12.5px;
  padding: 6px 9px; border-radius: 6px; z-index: 50; box-shadow: 0 4px 14px rgba(0,0,0,.2);
  transform: translate(-50%, -130%); white-space: nowrap;
}
.tooltip.hidden { display: none; }

.scrubber-row {
  display: flex; flex-direction: column; align-items: flex-start; gap: 8px;
  margin-top: 4px; padding-top: 10px; border-top: 1px solid var(--border);
}
.chip-group { display: flex; gap: 6px; flex-wrap: wrap; }
.chip {
  border: 1px solid var(--border); background: var(--bg); color: var(--text);
  padding: 5px 10px; border-radius: 999px; font-size: 12px; cursor: pointer;
}
.chip:hover { background: var(--accent-bg); }
.chip.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.time-control { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.step-btn {
  width: 28px; height: 28px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg);
  font-size: 16px; cursor: pointer; line-height: 1;
}
.step-btn:hover { background: var(--accent-bg); }
#timeInput { border: 1px solid var(--border); border-radius: 6px; padding: 4px 8px; font-size: 13px; width: 110px; }
.clear-btn {
  border: 1px solid var(--border); background: var(--surface); border-radius: 6px; padding: 5px 10px;
  font-size: 12.5px; cursor: pointer; color: var(--text-muted);
}
.clear-btn:hover { color: var(--text); }
.compact-label { margin-left: 0; }

section.table-section {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 8px 14px; margin-bottom: 8px;
  display: flex; flex-direction: column; min-height: 0;
}
.table-toolbar { display: flex; align-items: center; gap: 14px; margin-bottom: 6px; flex-wrap: wrap; flex: 0 0 auto; }
#searchBox {
  flex: 1 1 240px; border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; font-size: 13px;
}
.row-count { font-size: 12.5px; color: var(--text-muted); margin-left: auto; }
.table-scroll { height: 300px; overflow-y: scroll; overflow-x: auto; }
table#procTable { width: 100%; border-collapse: collapse; font-size: 13.5px; table-layout: fixed; }
table#procTable th, table#procTable td {
  text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border); vertical-align: top;
  overflow-wrap: anywhere; word-break: break-word;
}
table#procTable th:nth-child(1), table#procTable td:nth-child(1) { width: 28px; padding-left: 6px; padding-right: 6px; }
table#procTable th:nth-child(2), table#procTable td:nth-child(2) { width: 24%; }
table#procTable th:nth-child(3), table#procTable td:nth-child(3) { width: 17%; }
table#procTable th:nth-child(4), table#procTable td:nth-child(4) { width: 13%; }
table#procTable th:nth-child(5), table#procTable td:nth-child(5) { width: 21%; }
table#procTable th:nth-child(6), table#procTable td:nth-child(6) { width: 22%; }
table#procTable .enabled-col, table#procTable td.enabled-cell { text-align: center; }
table#procTable thead th { position: sticky; top: 0; background: var(--surface); z-index: 2; box-shadow: 0 1px 0 var(--border); }
table#procTable th { color: var(--text-muted); font-weight: 600; cursor: pointer; white-space: normal; user-select: none; }
table#procTable th.sorted::after { content: " \25BE"; }
table#procTable th.sorted.desc::after { content: " \25B4"; }
table#procTable tbody tr:hover { background: var(--accent-bg); }
table#procTable tbody tr.now-match { background: #fff6e0; }
table#procTable tbody tr.disabled-row { color: var(--text-muted); }
table#procTable tbody tr.disabled-row .tag { opacity: 0.7; }
table#procTable td.times-cell { white-space: normal; color: var(--text-muted); }
.tag { display: inline-block; background: var(--accent-bg); color: var(--accent); border-radius: 999px; padding: 2px 8px; font-size: 11.5px; max-width: 100%; overflow-wrap: anywhere; }
body.compact table#procTable th, body.compact table#procTable td { padding: 2px 8px; font-size: 12px; }

.edge-cases { background: #fff6e0; border: 1px solid #f0d68a; border-radius: var(--radius); padding: 8px 14px; margin-bottom: 8px; font-size: 13px; }
.edge-cases h2 { margin: 0 0 6px; font-size: 14px; }
.edge-cases ul { margin: 6px 0 0; padding-left: 20px; }

.page-footer { margin-top: 8px; }
"""

JS_TEMPLATE = r"""
/* ---------------------------------------------------------------------
 * Color ramps (>=100 shades per band), built from pairs of color "stops"
 * ------------------------------------------------------------------- */
function buildGradientPalette(stops, n) {
  const out = new Array(n);
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    let a = stops[0], b = stops[stops.length - 1];
    for (let s = 0; s < stops.length - 1; s++) {
      if (t >= stops[s].t && t <= stops[s + 1].t) { a = stops[s]; b = stops[s + 1]; break; }
    }
    const span = (b.t - a.t) || 1;
    const f = (t - a.t) / span;
    const r = Math.round(a.rgb[0] + (b.rgb[0] - a.rgb[0]) * f);
    const g = Math.round(a.rgb[1] + (b.rgb[1] - a.rgb[1]) * f);
    const bl = Math.round(a.rgb[2] + (b.rgb[2] - a.rgb[2]) * f);
    out[i] = "rgb(" + r + "," + g + "," + bl + ")";
  }
  return out;
}

const PALETTE_SIZE = 128;
const HEAT_STOPS = [
  { t: 0,    rgb: [255, 255, 255] },
  { t: 0.35, rgb: [12, 163, 12] },
  { t: 0.7,  rgb: [250, 178, 25] },
  { t: 1,    rgb: [208, 59, 59] }
];
const SEQ_STOPS = [
  { t: 0,   rgb: [240, 247, 255] },
  { t: 0.5, rgb: [96, 165, 224] },
  { t: 1,   rgb: [13, 42, 94] }
];
const HEAT_PALETTE = buildGradientPalette(HEAT_STOPS, PALETTE_SIZE);
const SEQ_PALETTE = buildGradientPalette(SEQ_STOPS, PALETTE_SIZE);
const EMPTY_COLOR = "#f1f2f4";

function paletteColor(t, palette) {
  const i = Math.max(0, Math.min(PALETTE_SIZE - 1, Math.round(t * (PALETTE_SIZE - 1))));
  return palette[i];
}
function heatColor(t) { return paletteColor(t, HEAT_PALETTE); }
function rampColor(t) { return paletteColor(t, SEQ_PALETTE); }

function legendGradientCss(mode) {
  const stops = mode === "heat" ? HEAT_STOPS : SEQ_STOPS;
  const parts = stops.map(function (s) { return "rgb(" + s.rgb.join(",") + ") " + (s.t * 100) + "%"; });
  return "linear-gradient(to right, " + parts.join(", ") + ")";
}

/* ---------------------------------------------------------------------
 * Days of week (ISO 1=Mon .. 7=Sun) and "today" computed in the reader's
 * own browser
 * ------------------------------------------------------------------- */
const DAY_NAMES_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_NAMES_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function todayIsoDay() {
  const jsDay = new Date().getDay(); // 0=Sun..6=Sat
  return jsDay === 0 ? 7 : jsDay;
}

/* ---------------------------------------------------------------------
 * Density computation for the selected day
 * ------------------------------------------------------------------- */
function computeDayData(day) {
  const counts = new Int32Array(1440);
  const activeProcesses = [];
  for (let i = 0; i < PROCESSES.length; i++) {
    const p = PROCESSES[i];
    if (p.daysOfWeek.indexOf(day) === -1) continue;
    if (!p.enabled && !state.showDisabled) continue;
    activeProcesses.push(p);
    for (let j = 0; j < p.times.length; j++) counts[p.times[j]]++;
  }
  let max = 0;
  for (let i = 0; i < 1440; i++) if (counts[i] > max) max = counts[i];
  return { day: day, counts: counts, max: max, activeProcesses: activeProcesses };
}

/* ---------------------------------------------------------------------
 * Application state
 * ------------------------------------------------------------------- */
const state = {
  day: todayIsoDay(),
  colorMode: "heat",
  selectedMinute: null,
  search: "",
  timeMatchOnly: true,
  compact: true,
  showDisabled: false,
  sortKey: "firstTime",
  sortDir: "asc",
  dayData: null
};
state.dayData = computeDayData(state.day);

/* ---------------------------------------------------------------------
 * Canvas grid (chartE)
 * ------------------------------------------------------------------- */
const grid = { cols: 60, rows: 24, cellW: 16, cellH: 14, marginLeft: 32, marginTop: 16 };
const canvas = document.getElementById("heat");
canvas.width = grid.marginLeft + grid.cols * grid.cellW + 4;
canvas.height = grid.marginTop + grid.rows * grid.cellH + 4;
const ctx = canvas.getContext("2d");

function minuteToRC(minute) { return { row: Math.floor(minute / 60), col: minute % 60 }; }

const chartE = {
  draw: function () {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = "10px -apple-system, sans-serif";
    ctx.fillStyle = "#5b6472";
    ctx.textBaseline = "middle";
    for (let h = 0; h < grid.rows; h++) {
      ctx.fillText(String(h).padStart(2, "0"), 2, grid.marginTop + h * grid.cellH + grid.cellH / 2);
    }
    ctx.textBaseline = "alphabetic";
    for (let m = 0; m < grid.cols; m += 10) {
      ctx.fillText(":" + String(m).padStart(2, "0"), grid.marginLeft + m * grid.cellW, grid.marginTop - 5);
    }
    const dd = state.dayData;
    const palette = state.colorMode === "heat" ? "heat" : "blue";
    for (let h = 0; h < grid.rows; h++) {
      for (let m = 0; m < grid.cols; m++) {
        const idx = h * 60 + m;
        const c = dd.counts[idx];
        let color;
        if (c === 0) color = EMPTY_COLOR;
        else {
          const t = dd.max > 0 ? c / dd.max : 0;
          color = palette === "heat" ? heatColor(t) : rampColor(t);
        }
        ctx.fillStyle = color;
        ctx.fillRect(grid.marginLeft + m * grid.cellW, grid.marginTop + h * grid.cellH, grid.cellW - 1, grid.cellH - 1);
      }
    }
    if (state.selectedMinute != null) {
      const rc = minuteToRC(state.selectedMinute);
      ctx.strokeStyle = "#1a2130";
      ctx.lineWidth = 2;
      ctx.strokeRect(
        grid.marginLeft + rc.col * grid.cellW + 0.5,
        grid.marginTop + rc.row * grid.cellH + 0.5,
        grid.cellW - 2, grid.cellH - 2
      );
    }
  }
};

function coordsToMinute(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  const x = (clientX - rect.left) * scaleX;
  const y = (clientY - rect.top) * scaleY;
  const col = Math.floor((x - grid.marginLeft) / grid.cellW);
  const row = Math.floor((y - grid.marginTop) / grid.cellH);
  if (col < 0 || col >= grid.cols || row < 0 || row >= grid.rows) return null;
  return row * 60 + col;
}

const tooltip = document.getElementById("tooltip");
function showTooltip(clientX, clientY, minute) {
  const rc = minuteToRC(minute);
  const count = state.dayData.counts[minute];
  tooltip.textContent =
    String(rc.row).padStart(2, "0") + ":" + String(rc.col).padStart(2, "0") +
    " · " + count + (count === 1 ? " process" : " processes");
  tooltip.style.left = clientX + "px";
  tooltip.style.top = clientY + "px";
  tooltip.classList.remove("hidden");
}
function hideTooltip() { tooltip.classList.add("hidden"); }

let dragging = false;
canvas.addEventListener("mousedown", function (e) {
  const minute = coordsToMinute(e.clientX, e.clientY);
  if (minute == null) return;
  dragging = true;
  setSelectedMinute(minute);
  showTooltip(e.clientX, e.clientY, minute);
});
window.addEventListener("mousemove", function (e) {
  const minute = coordsToMinute(e.clientX, e.clientY);
  if (minute == null) { if (!dragging) hideTooltip(); return; }
  if (dragging) setSelectedMinute(minute);
  showTooltip(e.clientX, e.clientY, minute);
});
window.addEventListener("mouseup", function () { dragging = false; });
canvas.addEventListener("mouseleave", function () { if (!dragging) hideTooltip(); });

/* simple touch support */
canvas.addEventListener("touchstart", function (e) {
  const t = e.touches[0];
  const minute = coordsToMinute(t.clientX, t.clientY);
  if (minute == null) return;
  setSelectedMinute(minute);
  showTooltip(t.clientX, t.clientY, minute);
  e.preventDefault();
}, { passive: false });
canvas.addEventListener("touchmove", function (e) {
  const t = e.touches[0];
  const minute = coordsToMinute(t.clientX, t.clientY);
  if (minute == null) return;
  setSelectedMinute(minute);
  showTooltip(t.clientX, t.clientY, minute);
  e.preventDefault();
}, { passive: false });

/* ---------------------------------------------------------------------
 * Day switch
 * ------------------------------------------------------------------- */
const daySwitchEl = document.getElementById("daySwitch");
const today = todayIsoDay();
for (let d = 1; d <= 7; d++) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "day-btn";
  btn.dataset.day = String(d);
  btn.title = DAY_NAMES_FULL[d - 1];
  btn.textContent = DAY_NAMES_SHORT[d - 1];
  if (d === today) {
    const dot = document.createElement("span");
    dot.className = "today-dot";
    btn.appendChild(dot);
  }
  btn.addEventListener("click", function () { setDay(d); });
  daySwitchEl.appendChild(btn);
}
function refreshDayButtons() {
  const btns = daySwitchEl.querySelectorAll(".day-btn");
  btns.forEach(function (b) { b.classList.toggle("active", Number(b.dataset.day) === state.day); });
}

function setDay(d) {
  state.day = d;
  state.dayData = computeDayData(d);
  refreshDayButtons();
  refreshLegend();
  chartE.draw();
  renderTable();
}

/* recompute the current day's data (e.g. after the "show disabled
 * processes" toggle changes) without changing which day is selected */
function refreshDayData() {
  state.dayData = computeDayData(state.day);
  refreshLegend();
  chartE.draw();
  renderTable();
}

const showDisabledToggle = document.getElementById("showDisabledToggle");
showDisabledToggle.addEventListener("change", function () {
  state.showDisabled = showDisabledToggle.checked;
  refreshDayData();
});

/* ---------------------------------------------------------------------
 * Color scale toggle + legend
 * ------------------------------------------------------------------- */
const colorToggle = document.getElementById("colorToggle");
const legendBar = document.getElementById("legendBar");
const legendMax = document.getElementById("legendMax");
colorToggle.addEventListener("change", function () {
  state.colorMode = colorToggle.checked ? "heat" : "blue";
  refreshLegend();
  chartE.draw();
});
function refreshLegend() {
  legendBar.style.background = legendGradientCss(state.colorMode);
  legendMax.textContent = String(state.dayData.max);
}

/* ---------------------------------------------------------------------
 * Scrubber: minute selection, +/-, quick-jump chips, "time-match only"
 * ------------------------------------------------------------------- */
const timeInput = document.getElementById("timeInput");
const timeMatchOnly = document.getElementById("timeMatchOnly");
const clearSelectionBtn = document.getElementById("clearSelection");

function setSelectedMinute(minute) {
  state.selectedMinute = ((minute % 1440) + 1440) % 1440;
  const rc = minuteToRC(state.selectedMinute);
  timeInput.value = String(rc.row).padStart(2, "0") + ":" + String(rc.col).padStart(2, "0");
  chartE.draw();
  renderTable();
  refreshChipStates();
}
function clearSelectedMinute() {
  state.selectedMinute = null;
  timeInput.value = "";
  chartE.draw();
  renderTable();
  refreshChipStates();
}
clearSelectionBtn.addEventListener("click", clearSelectedMinute);

document.getElementById("stepMinus").addEventListener("click", function () {
  setSelectedMinute((state.selectedMinute == null ? 0 : state.selectedMinute) - 1);
});
document.getElementById("stepPlus").addEventListener("click", function () {
  setSelectedMinute((state.selectedMinute == null ? 0 : state.selectedMinute) + 1);
});
timeInput.addEventListener("change", function () {
  const v = timeInput.value;
  if (!v) { clearSelectedMinute(); return; }
  const parts = v.split(":");
  setSelectedMinute(parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10));
});
timeMatchOnly.addEventListener("change", function () {
  state.timeMatchOnly = timeMatchOnly.checked;
  renderTable();
});

const quickChips = document.getElementById("quickChips");
const CHIP_DEFS = [
  { key: "now", label: "Now" },
  { key: "peak", label: "Peak of day" }
];
CHIP_DEFS.forEach(function (chip) {
  const el = document.createElement("button");
  el.type = "button";
  el.className = "chip";
  el.dataset.key = chip.key;
  el.textContent = chip.label;
  el.addEventListener("click", function () {
    if (chip.key === "now") {
      const now = new Date();
      setDay(todayIsoDay());
      setSelectedMinute(now.getHours() * 60 + now.getMinutes());
    } else if (chip.key === "peak") {
      let bestIdx = 0, bestVal = -1;
      for (let i = 0; i < 1440; i++) if (state.dayData.counts[i] > bestVal) { bestVal = state.dayData.counts[i]; bestIdx = i; }
      setSelectedMinute(bestIdx);
    } else {
      const h = parseInt(chip.key.slice(0, 2), 10), m = parseInt(chip.key.slice(2), 10);
      setSelectedMinute(h * 60 + m);
    }
  });
  quickChips.appendChild(el);
});
function refreshChipStates() {
  const chips = quickChips.querySelectorAll(".chip");
  chips.forEach(function (c) {
    let match = false;
    if (state.selectedMinute != null) {
      const key = c.dataset.key;
      if (key !== "now" && key !== "peak") {
        const h = parseInt(key.slice(0, 2), 10), m = parseInt(key.slice(2), 10);
        match = (h * 60 + m) === state.selectedMinute;
      }
    }
    c.classList.toggle("active", match);
  });
}

/* ---------------------------------------------------------------------
 * Table: search, sorting, compact mode
 * ------------------------------------------------------------------- */
const searchBox = document.getElementById("searchBox");
const compactToggle = document.getElementById("compactToggle");
const rowCountEl = document.getElementById("rowCount");
const tableBody = document.getElementById("procTableBody");

searchBox.addEventListener("input", function () { state.search = searchBox.value.trim().toLowerCase(); renderTable(); });
compactToggle.addEventListener("change", function () {
  state.compact = compactToggle.checked;
  document.body.classList.toggle("compact", state.compact);
});

document.querySelectorAll("#procTable th[data-key]").forEach(function (th) {
  th.addEventListener("click", function () {
    const key = th.dataset.key;
    if (state.sortKey === key) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortKey = key;
      state.sortDir = "asc";
    }
    renderTable();
  });
});

function formatTimesList(times) {
  const strs = times.map(function (t) { return String(Math.floor(t / 60)).padStart(2, "0") + ":" + String(t % 60).padStart(2, "0"); });
  if (strs.length <= 6) return strs.join(", ");
  return strs.slice(0, 6).join(", ") + " and " + (strs.length - 6) + " more";
}

function renderTable() {
  let rows = state.dayData.activeProcesses.slice();

  if (state.search) {
    rows = rows.filter(function (p) {
      const hay = (p.name + " " + p.group + " " + p.atom + " " + p.schedText).toLowerCase();
      return hay.indexOf(state.search) !== -1;
    });
  }
  if (state.timeMatchOnly && state.selectedMinute != null) {
    rows = rows.filter(function (p) { return p.times.indexOf(state.selectedMinute) !== -1; });
  }

  rows = rows.map(function (p) { return Object.assign({ firstTime: p.times[0] }, p); });

  rows.sort(function (a, b) {
    let av = a[state.sortKey], bv = b[state.sortKey];
    if (typeof av === "string") av = av.toLowerCase();
    if (typeof bv === "string") bv = bv.toLowerCase();
    let cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return state.sortDir === "asc" ? cmp : -cmp;
  });

  document.querySelectorAll("#procTable th[data-key]").forEach(function (th) {
    th.classList.toggle("sorted", th.dataset.key === state.sortKey);
    th.classList.toggle("desc", th.dataset.key === state.sortKey && state.sortDir === "desc");
  });

  tableBody.innerHTML = "";
  const frag = document.createDocumentFragment();
  rows.forEach(function (p) {
    const tr = document.createElement("tr");
    if (state.selectedMinute != null && p.times.indexOf(state.selectedMinute) !== -1) {
      tr.classList.add("now-match");
    }
    if (!p.enabled) tr.classList.add("disabled-row");
    const tdEnabled = document.createElement("td"); tdEnabled.className = "enabled-cell";
    const enabledBox = document.createElement("input");
    enabledBox.type = "checkbox";
    enabledBox.checked = !!p.enabled;
    enabledBox.disabled = true;
    enabledBox.setAttribute("aria-label", p.enabled ? "Enabled" : "Disabled");
    tdEnabled.appendChild(enabledBox);
    const tdName = document.createElement("td"); tdName.textContent = p.name;
    const tdGroup = document.createElement("td");
    if (p.group) { const tag = document.createElement("span"); tag.className = "tag"; tag.textContent = p.group; tdGroup.appendChild(tag); }
    const tdAtom = document.createElement("td"); tdAtom.textContent = p.atom;
    const tdSched = document.createElement("td"); tdSched.textContent = p.schedText;
    const tdTimes = document.createElement("td"); tdTimes.className = "times-cell";
    tdTimes.textContent = formatTimesList(p.times);
    tdTimes.title = p.times.map(function (t) { return String(Math.floor(t / 60)).padStart(2, "0") + ":" + String(t % 60).padStart(2, "0"); }).join(", ");
    tr.appendChild(tdEnabled); tr.appendChild(tdName); tr.appendChild(tdGroup); tr.appendChild(tdAtom); tr.appendChild(tdSched); tr.appendChild(tdTimes);
    frag.appendChild(tr);
  });
  tableBody.appendChild(frag);
  rowCountEl.textContent = rows.length + " / " + state.dayData.activeProcesses.length + " processes for " + DAY_NAMES_FULL[state.day - 1];
}

/* ---------------------------------------------------------------------
 * Edge-case section (daysOfMonth/months), if any exist
 * ------------------------------------------------------------------- */
(function renderEdgeCases() {
  const box = document.getElementById("edgeCaseBox");
  if (!box || !EDGE_CASES.length) return;
  const ul = box.querySelector("ul");
  EDGE_CASES.forEach(function (ec) {
    const li = document.createElement("li");
    li.textContent = ec.process + " (" + ec.atom + ") – daysOfMonth=" + ec.daysOfMonth + ", months=" + ec.months;
    ul.appendChild(li);
  });
})();

/* ---------------------------------------------------------------------
 * Init
 * ------------------------------------------------------------------- */
document.body.classList.toggle("compact", state.compact);
refreshDayButtons();
refreshLegend();
chartE.draw();
renderTable();
"""


def render_html(processes, edge_cases, envs_used):
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    schedule_row_count = len(processes)
    schedule_count = sum(len(p["times"]) for p in processes)  # total distinct run-times across all processes

    disabled_count = sum(1 for p in processes if not p["enabled"])
    enabled_count = schedule_row_count - disabled_count
    if disabled_count:
        enabled_note = (
            f"Each process carries an <code>enabled</code> flag from "
            f"ProcessScheduleStatus &ndash; {enabled_count} enabled and "
            f"{disabled_count} disabled schedules were found. Disabled "
            f"processes are hidden from the grid and table by default; use "
            f"the \"Show disabled processes\" toggle next to the heatmap to "
            f"include them (shown with an unchecked box in the first table "
            f"column)."
        )
    else:
        enabled_note = (
            "Each process carries an <code>enabled</code> flag from "
            "ProcessScheduleStatus; no disabled schedules were found in "
            "this export, so the \"Show disabled processes\" toggle has no "
            "effect here."
        )

    if edge_cases:
        edge_note = (
            "<li><strong>Note:</strong> schedules with a day-of-month "
            "(daysOfMonth) or month (months) restriction were found &ndash; "
            "these processes are listed separately below; the grid/table "
            "view may not be accurate for them, since the page's data model "
            "only accounts for daysOfWeek.</li>"
        )
        edge_section = (
            '<section class="edge-cases" id="edgeCaseBox">'
            "<h2>Processes with a day-of-month / month restriction (cannot be shown accurately in the heatmap)</h2>"
            "<ul></ul></section>"
        )
    else:
        edge_note = "<li>No schedules with a day-of-month or month restriction were found in the input data.</li>"
        edge_section = ""

    html = HTML_TEMPLATE
    html = html.replace("__CSS__", CSS_TEMPLATE)
    html = html.replace("__JS__", JS_TEMPLATE)
    html = html.replace("__PROCESSES_JSON__", json.dumps(processes, ensure_ascii=False))
    html = html.replace("__EDGE_CASES_JSON__", json.dumps(edge_cases, ensure_ascii=False))
    html = html.replace("__GENERATED_AT__", generated_at)
    html = html.replace("__TZ_LABEL__", TIMEZONE_LABEL)
    html = html.replace("__ENV_LIST__", ", ".join(envs_used))
    html = html.replace("__PROCESS_COUNT__", str(schedule_row_count))
    html = html.replace("__SCHEDULE_COUNT__", f"{schedule_count:,}")
    html = html.replace("__DISABLED_COUNT__", f"{disabled_count:,}")
    html = html.replace("__TZ_NOTE__", TIMEZONE_NOTE)
    html = html.replace("__DOW_NOTE__", DOW_CONVENTION_NOTE)
    html = html.replace("__ENABLED_NOTE__", enabled_note)
    html = html.replace("__EDGE_CASE_NOTE__", edge_note)
    html = html.replace("__EDGE_CASE_SECTION__", edge_section)
    return html


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default="process_schedules.json", help="Path to the ProcessSchedules JSON export")
    parser.add_argument("--csv", default="component_metadata.csv", help="Path to the component metadata file")
    parser.add_argument("--out", default="schedule-heatmap.html", help="Path to the output HTML file")
    args = parser.parse_args()

    json_path = Path(args.json)
    csv_path = Path(args.csv)
    if not json_path.exists():
        sys.exit(f"ERROR: input JSON file not found: {json_path}")
    if not csv_path.exists():
        sys.exit(f"ERROR: input CSV (component metadata) file not found: {csv_path}")

    schedule_data = load_json(json_path)
    component_map = load_component_metadata_csv(csv_path)

    processes, warnings, edge_cases, envs_used = build_processes(schedule_data, component_map)

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    if not processes:
        sys.exit("ERROR: no processes remained after ETL processing - check the input data.")

    html = render_html(processes, edge_cases, envs_used)

    out_path = Path(args.out)
    out_path.write_text(html, encoding="utf-8")

    print(f"OK: generated {len(processes)} process entries from environments: {', '.join(envs_used)}")
    print(f"OK: output written to {out_path.resolve()}")
    if edge_cases:
        print(f"NOTE: {len(edge_cases)} schedules have a day-of-month/month restriction - see the section in the HTML.")


if __name__ == "__main__":
    main()
