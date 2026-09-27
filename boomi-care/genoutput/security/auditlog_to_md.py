#!/usr/bin/env python3
"""
auditlog_to_md.py
=================

Converts an audit-log CSV file (columns: userId, lastlogin, logins) into
a Markdown report compatible with Azure DevOps Wiki.

For every month in which at least one user was active, a calendar grid
is rendered. The exact format of that calendar is selectable via the
``--format`` flag:

* ``html`` (default) - HTML ``<table>`` with inline CSS, rendered
  directly inside the .md file. Single self-contained .md, nothing to
  upload as attachment.

* ``png`` / ``jpeg`` - each month is rendered as a raster image saved
  next to the .md inside an ``.attachments/`` folder (the Azure DevOps
  Wiki convention for attached files). The .md references each image
  with a relative path. Requires Pillow (``pip install Pillow``).

In every mode the calendar shows:
    - columns       = days of the month (real day count, 28/29/30/31)
    - rows          = users that were active in that month
    - green cell    = the user logged in at least once on that day
    - gray cell     = Saturday / Sunday with no login
    - white cell    = regular weekday with no login

The userId column shows only the *local part* of the e-mail (before
``@``). The full e-mail is preserved in the per-user ``<details>``
block below each calendar.

Usage
-----
    python auditlog_to_md.py <input.csv> [output.md] [--format html|png|jpeg]
"""

from __future__ import annotations

import argparse
import calendar
import csv
import sys
from collections import defaultdict
from datetime import date, datetime
from html import escape
from pathlib import Path


# ----------------------------------------------------------------------------
# Visual constants
# ----------------------------------------------------------------------------
COLOR_GREEN = "#22c55e"          # at least one login
COLOR_WEEKEND = "#d1d5db"        # weekend without login
COLOR_BORDER = "#94a3b8"
COLOR_HEADER_BG = "#f1f5f9"
COLOR_TEXT = "#0f172a"           # only used by the image renderer

# Filename prefix used for generated calendar images (png/jpeg modes).
# Each month produces "<IMAGE_PREFIX>_<YYYY>-<MM>.<ext>".
IMAGE_PREFIX = "audit_log"

# lastlogin in the main table is formatted compactly - only day + time
# (year/month are already in the section heading).
LASTLOGIN_FMT = "%d %H:%M:%S"   # e.g. "12 06:15:42"

# Inline CSS, compacted. No column widths are declared anywhere - the
# browser auto-sizes each column to fit its content, which is exactly
# the default behaviour (no table-layout:fixed, no <colgroup>).
TABLE_STYLE = (
    "border-collapse:collapse;"
    "font-family:Segoe UI,Arial,sans-serif;font-size:12px;margin:4px 0 10px 0"
)
_CELL_BORDER = f"border:1px solid {COLOR_BORDER}"
TD_DAY_BASE = _CELL_BORDER
TD_DAY_GREEN = f"{_CELL_BORDER};background:{COLOR_GREEN}"
TD_DAY_WEEKEND = f"{_CELL_BORDER};background:{COLOR_WEEKEND}"

_TH_DAY_BASE = (
    f"{_CELL_BORDER};padding:1px 4px;"
    "text-align:center;font-size:10px;font-weight:600"
)
TH_DAY = f"{_TH_DAY_BASE};background:{COLOR_HEADER_BG}"
TH_DAY_WEEKEND = f"{_TH_DAY_BASE};background:{COLOR_WEEKEND}"

TH_LABEL = (
    f"{_CELL_BORDER};padding:2px 6px;text-align:left;"
    f"background:{COLOR_HEADER_BG};font-weight:600"
)
TD_LABEL = f"{_CELL_BORDER};padding:2px 6px;white-space:nowrap"

# Full-width title row at the top of each calendar table (e.g. "2026.05").
TH_TITLE = (
    f"{_CELL_BORDER};padding:3px 6px;text-align:center;"
    f"background:{COLOR_HEADER_BG};font-weight:700"
)

# ---- Accounts-by-domain table (HTML so header + Summary rows can be tinted)
DOMAIN_TABLE_STYLE = (
    "border-collapse:collapse;"
    "font-family:Segoe UI,Arial,sans-serif;font-size:13px;margin:4px 0 10px 0"
)
# Header row cells - gray background, bold
DOMAIN_TH = (
    f"{_CELL_BORDER};padding:4px 10px;text-align:left;"
    f"background:{COLOR_HEADER_BG};font-weight:600;white-space:nowrap"
)
DOMAIN_TH_COUNT = (
    f"{_CELL_BORDER};padding:4px 10px;text-align:right;"
    f"background:{COLOR_HEADER_BG};font-weight:600"
)
# Body cells - plain
DOMAIN_TD = f"{_CELL_BORDER};padding:4px 10px;white-space:nowrap"
DOMAIN_TD_COUNT = f"{_CELL_BORDER};padding:4px 10px;text-align:right"
DOMAIN_TD_ACCOUNTS = f"{_CELL_BORDER};padding:4px 10px"
# Summary row cells - gray background, bold
DOMAIN_TD_SUMMARY = (
    f"{_CELL_BORDER};padding:4px 10px;"
    f"background:{COLOR_HEADER_BG};font-weight:700;white-space:nowrap"
)
DOMAIN_TD_SUMMARY_COUNT = (
    f"{_CELL_BORDER};padding:4px 10px;text-align:right;"
    f"background:{COLOR_HEADER_BG};font-weight:700"
)
DOMAIN_TD_SUMMARY_EMPTY = (
    f"{_CELL_BORDER};padding:4px 10px;"
    f"background:{COLOR_HEADER_BG}"
)

WEEKDAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


# ----------------------------------------------------------------------------
# Input parsing
# ----------------------------------------------------------------------------
def parse_iso(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp such as ``2026-05-14T07:16:56Z``."""
    ts = ts.strip()
    if ts.endswith("Z"):
        ts = ts[:-1]
    return datetime.fromisoformat(ts)


def parse_logins(logins_field: str) -> list[datetime]:
    """Turn the comma-separated ``logins`` field into a list of ``datetime``."""
    if not logins_field or not logins_field.strip():
        return []
    out: list[datetime] = []
    for part in logins_field.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(parse_iso(part))
        except ValueError:
            print(f"  ! skipping unparseable timestamp: {part!r}", file=sys.stderr)
    return out


def read_csv(path: Path) -> list[dict]:
    """Read the CSV and return a list of records with parsed login times."""
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"userId", "lastlogin", "logins"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"CSV is missing required columns: {', '.join(sorted(missing))}"
            )
        for row in reader:
            user_id = (row.get("userId") or "").strip()
            if not user_id:
                continue
            rows.append({
                "userId": user_id,
                "lastlogin_raw": (row.get("lastlogin") or "").strip(),
                "logins": parse_logins(row.get("logins") or ""),
            })
    return rows


# ----------------------------------------------------------------------------
# Aggregation by month
# ----------------------------------------------------------------------------
def group_by_month(
    rows: list[dict],
) -> dict[tuple[int, int], dict[str, list[datetime]]]:
    """Group login times into ``dict[(year, month)][userId] -> list[datetime]``.

    A user appears in a given month only when they had at least one
    login in that month. Any number of months in the input is handled.
    """
    months: dict[tuple[int, int], dict[str, list[datetime]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        for login in row["logins"]:
            months[(login.year, login.month)][row["userId"]].append(login)

    for ym in months:
        for uid in months[ym]:
            months[ym][uid].sort(reverse=True)

    return months


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def local_part(user_id: str) -> str:
    """Return the part of an e-mail before ``@``; passthrough if no ``@``."""
    if "@" in user_id:
        return user_id.split("@", 1)[0]
    return user_id


# ----------------------------------------------------------------------------
# Image renderer (used only when --format is png or jpeg)
#
# Pillow is imported lazily inside build_month_image() so that running
# the script with the default ``html`` format does not require Pillow
# to be installed at all.
# ----------------------------------------------------------------------------
# Pixel geometry for raster output. The userId and lastlogin column
# widths are computed dynamically inside build_month_image() based on
# the actual text content; only the rest is fixed.
IMG_DAY_W = 18
IMG_HEADER_H = 24       # day-number header strip
IMG_TITLE_H = 24        # full-width "YYYY.MM" title strip on top
IMG_ROW_H = 22
IMG_LABEL_PAD = 8       # left + right padding inside label cells (px)


def _find_font_paths() -> dict[str, str]:
    """Return paths to a regular and a bold TTF, searching common locations."""
    import PIL  # noqa: PLC0415
    pil_fonts_dir = Path(PIL.__file__).parent / "fonts"

    regular_candidates = [
        pil_fonts_dir / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    bold_candidates = [
        pil_fonts_dir / "DejaVuSans-Bold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]

    out: dict[str, str] = {}
    for p in regular_candidates:
        if p.exists():
            out["regular"] = str(p)
            break
    for p in bold_candidates:
        if p.exists():
            out["bold"] = str(p)
            break
    return out


def _get_font(size: int, bold: bool = False):
    """Return a PIL ImageFont at the requested size; falls back to default."""
    from PIL import ImageFont  # noqa: PLC0415
    paths = _find_font_paths()
    path = paths.get("bold" if bold else "regular") or paths.get("regular")
    if path:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            pass
    return ImageFont.load_default()


def _centered_text(draw, cx: float, cy: float, text: str, font, fill: str) -> None:
    """Draw ``text`` horizontally + vertically centred on (cx, cy)."""
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((cx - w / 2, cy - h / 2), text, fill=fill, font=font)


def build_month_image(
    year: int,
    month: int,
    sorted_users: list[tuple[str, list[datetime]]],
    output_path: Path,
    fmt: str,
) -> tuple[int, int]:
    """Render one month's calendar to ``output_path`` as PNG or JPEG.

    Pillow is imported here (lazy) so users running ``--format html``
    don't need it installed. Returns (width, height) of the saved image.
    """
    try:
        from PIL import Image, ImageDraw  # noqa: PLC0415
    except ImportError:
        print(
            "ERROR: Pillow is required for --format png/jpeg. "
            "Install it with: pip install Pillow",
            file=sys.stderr,
        )
        raise

    num_days = calendar.monthrange(year, month)[1]
    n_rows = len(sorted_users)

    # ---- Dynamic column widths -------------------------------------------
    # Measure the actual rendered width of the longest local-part (userId
    # column) and of the fixed-format lastlogin sample, using the 1x font
    # - the image is rendered at 2x and downscaled, so 1x measurements
    # match the final pixel widths.
    font_bold_1x = _get_font(11, bold=True)

    def _text_width(text: str) -> int:
        # Pillow 8+: FreeTypeFont.getbbox(); fall back to getlength().
        if hasattr(font_bold_1x, "getbbox"):
            left, _t, right, _b = font_bold_1x.getbbox(text)
            return int(right - left)
        return int(font_bold_1x.getlength(text))

    userid_w = max(
        _text_width("userId"),
        max(_text_width(local_part(uid)) for uid, _ in sorted_users),
    ) + IMG_LABEL_PAD * 2
    # The lastlogin format is always "DD HH:MM:SS" (11 chars). Use a
    # sample with widest digits and the column header.
    lastlogin_w = max(
        _text_width("lastlogin"),
        _text_width("00 00:00:00"),
    ) + IMG_LABEL_PAD * 2

    total_w = userid_w + lastlogin_w + IMG_DAY_W * num_days
    # Vertical layout: title strip (full-width "YYYY.MM"), then day-number
    # header strip, then n_rows data rows.
    header_y0 = IMG_TITLE_H
    data_y0 = IMG_TITLE_H + IMG_HEADER_H
    total_h = data_y0 + IMG_ROW_H * n_rows

    # 2x supersampling -> LANCZOS downscale gives crisp text without
    # needing a larger font size. Solid-colour rectangles dominate the
    # picture so PNG compression keeps the file small.
    scale = 2
    img = Image.new("RGB", (total_w * scale, total_h * scale), "#ffffff")
    draw = ImageDraw.Draw(img)

    font_regular = _get_font(11 * scale)
    font_bold = _get_font(11 * scale, bold=True)
    font_small = _get_font(10 * scale, bold=True)
    font_title = _get_font(13 * scale, bold=True)

    weekend_days = [
        d for d in range(1, num_days + 1)
        if date(year, month, d).weekday() >= 5
    ]
    grid_x0 = userid_w + lastlogin_w

    def s(v: float) -> int:
        return int(v * scale)

    def rect(x0, y0, x1, y1, fill):
        draw.rectangle([(s(x0), s(y0)), (s(x1) - 1, s(y1) - 1)], fill=fill)

    def line(x0, y0, x1, y1):
        # PIL silently clips coords outside the canvas. The right edge
        # is at logical x = total_w, which would map to pixel x =
        # total_w * scale - exactly one past the last valid index
        # (total_w * scale - 1), so the line would vanish. Same for the
        # bottom at y = total_h. Clamp to keep the line on the last
        # visible pixel.
        x0 = min(x0, total_w - 1)
        x1 = min(x1, total_w - 1)
        y0 = min(y0, total_h - 1)
        y1 = min(y1, total_h - 1)
        draw.line([(s(x0), s(y0)), (s(x1), s(y1))], fill=COLOR_BORDER, width=1)

    # Backgrounds
    # Title strip (full width, single merged cell)
    rect(0, 0, total_w, IMG_TITLE_H, COLOR_HEADER_BG)
    # Day-number header strip background
    rect(0, header_y0, total_w, data_y0, COLOR_HEADER_BG)
    # Weekend day-header columns
    for d in weekend_days:
        x = grid_x0 + (d - 1) * IMG_DAY_W
        rect(x, header_y0, x + IMG_DAY_W, data_y0, COLOR_WEEKEND)

    for i, (_uid, logins) in enumerate(sorted_users):
        y = data_y0 + i * IMG_ROW_H
        login_days = {dt.day for dt in logins}
        for d in range(1, num_days + 1):
            x = grid_x0 + (d - 1) * IMG_DAY_W
            if d in login_days:
                rect(x, y, x + IMG_DAY_W, y + IMG_ROW_H, COLOR_GREEN)
            elif d in weekend_days:
                rect(x, y, x + IMG_DAY_W, y + IMG_ROW_H, COLOR_WEEKEND)

    # Grid lines
    # Outer frame
    line(0, 0, total_w, 0)
    line(0, total_h, total_w, total_h)
    line(0, 0, 0, total_h)
    line(total_w, 0, total_w, total_h)
    # Title-strip bottom border (also top of day-header strip)
    line(0, header_y0, total_w, header_y0)
    # Day-header-strip bottom border (also top of data area)
    line(0, data_y0, total_w, data_y0)
    # Vertical column separators - start BELOW the title strip so the
    # title appears as one merged cell spanning all columns.
    line(userid_w, header_y0, userid_w, total_h)
    line(grid_x0, header_y0, grid_x0, total_h)
    for d in range(1, num_days + 1):
        x = grid_x0 + d * IMG_DAY_W
        line(x, header_y0, x, total_h)
    # Horizontal row separators
    for i in range(1, n_rows + 1):
        y = data_y0 + i * IMG_ROW_H
        line(0, y, total_w, y)

    # Title text - "YYYY.MM" centred across full width
    title_text = f"{year}.{month:02d}"
    _centered_text(
        draw, s(total_w / 2), s(IMG_TITLE_H / 2),
        title_text, font_title, COLOR_TEXT,
    )

    # Day-header text (column labels + day numbers)
    draw.text(
        (s(IMG_LABEL_PAD), s(header_y0 + 5)),
        "userId", fill=COLOR_TEXT, font=font_bold,
    )
    draw.text(
        (s(userid_w + IMG_LABEL_PAD), s(header_y0 + 5)),
        "lastlogin", fill=COLOR_TEXT, font=font_bold,
    )
    for d in range(1, num_days + 1):
        cx = grid_x0 + (d - 1) * IMG_DAY_W + IMG_DAY_W / 2
        cy = header_y0 + IMG_HEADER_H / 2
        _centered_text(
            draw, s(cx), s(cy), f"{d:02d}", font_small, COLOR_TEXT
        )

    # User rows
    for i, (uid, logins) in enumerate(sorted_users):
        y_text = data_y0 + i * IMG_ROW_H + 5
        display_uid = local_part(uid)
        last_str = logins[0].strftime(LASTLOGIN_FMT)
        draw.text(
            (s(IMG_LABEL_PAD), s(y_text)), display_uid,
            fill=COLOR_TEXT, font=font_bold,
        )
        draw.text(
            (s(userid_w + IMG_LABEL_PAD), s(y_text)), last_str,
            fill=COLOR_TEXT, font=font_regular,
        )

    # Downscale for crisp output
    img = img.resize((total_w, total_h), Image.LANCZOS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs = {"optimize": True} if fmt == "PNG" else {"quality": 90}
    img.save(output_path, fmt, **save_kwargs)
    return total_w, total_h


# ----------------------------------------------------------------------------
# Render a single month - split into two sections that are emitted in
# separate chapters of the final document (Monthly overview / Monthly
# detail).
# ----------------------------------------------------------------------------
def render_month_overview(
    year: int,
    month: int,
    users: dict[str, list[datetime]],
    *,
    fmt: str = "html",
    output_dir: Path | None = None,
    prefix: str = "",
) -> str:
    """Return the heading + stats + calendar grid for one month.

    ``prefix`` is prepended to the month heading (e.g. ``"1.1 "``) so
    the document hierarchy can carry a chapter.section numbering scheme.
    """
    num_days = calendar.monthrange(year, month)[1]

    sorted_users = sorted(
        users.items(),
        key=lambda kv: kv[0].lower(),
    )

    out: list[str] = []
    out.append(
        f"### {prefix}{year}.{month:02d} &mdash; "
        f"{MONTH_NAMES[month - 1]} {year}"
    )
    out.append("")
    out.append(
        f"*Active users this month: **{len(sorted_users)}** &middot; "
        f"days in month: **{num_days}***"
    )
    out.append("")

    if fmt == "html":
        out.extend(_render_calendar_html(year, month, num_days, sorted_users))
    else:
        if output_dir is None:
            raise ValueError("fmt 'png'/'jpeg' requires output_dir")
        out.extend(
            _render_calendar_image(year, month, sorted_users, fmt, output_dir)
        )

    return "\n".join(out)


def render_month_accounts(
    year: int,
    month: int,
    users: dict[str, list[datetime]],
    *,
    prefix: str = "",
) -> str:
    """Return an H4 heading + the accounts-by-domain Markdown table for one month."""
    sorted_users = sorted(
        users.items(),
        key=lambda kv: kv[0].lower(),
    )

    out: list[str] = []
    out.append(
        f"#### {prefix}{year}.{month:02d} &mdash; "
        f"{MONTH_NAMES[month - 1]} {year}"
    )
    out.append("")
    out.extend(_render_domain_stats(sorted_users))
    return "\n".join(out)


def render_month_logins(
    year: int,
    month: int,
    users: dict[str, list[datetime]],
    *,
    prefix: str = "",
) -> str:
    """Return an H4 heading + per-user collapsible <details> blocks for one month."""
    sorted_users = sorted(
        users.items(),
        key=lambda kv: kv[0].lower(),
    )

    out: list[str] = []
    out.append(
        f"#### {prefix}{year}.{month:02d} &mdash; "
        f"{MONTH_NAMES[month - 1]} {year}"
    )
    out.append("")
    out.extend(_render_user_details(year, month, sorted_users))
    return "\n".join(out)


def _render_calendar_html(
    year: int,
    month: int,
    num_days: int,
    sorted_users: list[tuple[str, list[datetime]]],
) -> list[str]:
    """Return the lines of the HTML <table> for one month's calendar."""
    out: list[str] = []
    out.append(f'<table style="{TABLE_STYLE}">')

    weekend_days = {
        d for d in range(1, num_days + 1)
        if date(year, month, d).weekday() >= 5
    }
    # 2 label columns (userId, lastlogin) + 1 column per day
    n_cols = 2 + num_days

    # Header rows: full-width title (YYYY.MM) + column-label row.
    header_parts = ["<thead>"]
    header_parts.append(
        f'<tr><th colspan="{n_cols}" style="{TH_TITLE}">'
        f'{year}.{month:02d}</th></tr>'
    )
    header_parts.append("<tr>")
    header_parts.append(f'<th style="{TH_LABEL}">userId</th>')
    header_parts.append(f'<th style="{TH_LABEL}">lastlogin</th>')
    for d in range(1, num_days + 1):
        style = TH_DAY_WEEKEND if d in weekend_days else TH_DAY
        header_parts.append(f'<th style="{style}">{d:02d}</th>')
    header_parts.append("</tr></thead>")
    out.append("".join(header_parts))

    out.append("<tbody>")
    for uid, logins in sorted_users:
        login_days = {dt.day for dt in logins}
        last_in_month = logins[0]  # already sorted desc
        display_uid = escape(local_part(uid))
        last_str = last_in_month.strftime(LASTLOGIN_FMT)

        row_parts = [
            "<tr>",
            f'<td style="{TD_LABEL}"><b>{display_uid}</b></td>',
            f'<td style="{TD_LABEL}">{last_str}</td>',
        ]
        for d in range(1, num_days + 1):
            if d in login_days:
                row_parts.append(f'<td style="{TD_DAY_GREEN}"></td>')
            elif d in weekend_days:
                row_parts.append(f'<td style="{TD_DAY_WEEKEND}"></td>')
            else:
                row_parts.append(f'<td style="{TD_DAY_BASE}"></td>')
        row_parts.append("</tr>")
        out.append("".join(row_parts))
    out.append("</tbody></table>")
    out.append("")
    return out


def _render_calendar_image(
    year: int,
    month: int,
    sorted_users: list[tuple[str, list[datetime]]],
    fmt: str,
    output_dir: Path,
) -> list[str]:
    """Render the calendar as PNG/JPEG and return Markdown lines referencing it."""
    ext = fmt.lower()
    image_name = f"{IMAGE_PREFIX}_{year}-{month:02d}.{ext}"
    image_path = output_dir / ".attachments" / image_name
    build_month_image(year, month, sorted_users, image_path, fmt.upper())
    alt = f"Audit log calendar for {year}.{month:02d}"
    return [f"![{alt}](.attachments/{image_name})", ""]


def _render_user_details(
    year: int,
    month: int,
    sorted_users: list[tuple[str, list[datetime]]],
) -> list[str]:
    """Return the per-user collapsible <details> blocks (no chapter intro)."""
    out: list[str] = []
    for uid, logins in sorted_users:
        safe_uid = escape(uid)
        count = len(logins)
        out.append("<details>")
        out.append(
            f"<summary><b>{safe_uid}</b> &mdash; "
            f"<i>{count} login{'s' if count != 1 else ''} in "
            f"{year}.{month:02d}</i></summary>"
        )
        out.append("")
        out.append("| # | Date | Time (UTC) | Weekday |")
        out.append("|---:|---|---|---|")
        for i, dt in enumerate(logins, 1):
            out.append(
                f"| {i} | {dt.strftime('%Y-%m-%d')} "
                f"| {dt.strftime('%H:%M:%S')} "
                f"| {WEEKDAY_NAMES[dt.weekday()]} |"
            )
        out.append("")
        out.append("</details>")
        out.append("")

    return out


def _render_domain_stats(
    sorted_users: list[tuple[str, list[datetime]]],
) -> list[str]:
    """Per-month breakdown of accounts grouped by e-mail domain.

    Rendered as an HTML <table> so that the header row and the trailing
    Summary row can have a gray background - markdown tables don't
    support per-row styling. Three columns: Domain, Count (right-aligned),
    Accounts (full userIds, comma-separated).
    """
    by_domain: dict[str, list[str]] = defaultdict(list)
    for uid, _ in sorted_users:
        if "@" in uid:
            _local, domain = uid.split("@", 1)
            key = f"@{domain}"
        else:
            key = "(no domain)"
        by_domain[key].append(uid)

    out: list[str] = []
    out.append(f'<table style="{DOMAIN_TABLE_STYLE}">')
    out.append(
        "<thead><tr>"
        f'<th style="{DOMAIN_TH}">Domain</th>'
        f'<th style="{DOMAIN_TH_COUNT}">Count</th>'
        f'<th style="{DOMAIN_TH}">Accounts</th>'
        "</tr></thead>"
    )
    out.append("<tbody>")
    for domain_key in sorted(by_domain.keys(), key=str.lower):
        accounts = sorted(by_domain[domain_key], key=str.lower)
        accounts_cell = ", ".join(escape(a) for a in accounts)
        out.append(
            "<tr>"
            f'<td style="{DOMAIN_TD}">{escape(domain_key)}</td>'
            f'<td style="{DOMAIN_TD_COUNT}">{len(accounts)}</td>'
            f'<td style="{DOMAIN_TD_ACCOUNTS}">{accounts_cell}</td>'
            "</tr>"
        )
    # Summary row - total across all domains.
    total = sum(len(v) for v in by_domain.values())
    out.append(
        "<tr>"
        f'<td style="{DOMAIN_TD_SUMMARY}">Summary</td>'
        f'<td style="{DOMAIN_TD_SUMMARY_COUNT}">{total}</td>'
        f'<td style="{DOMAIN_TD_SUMMARY_EMPTY}"></td>'
        "</tr>"
    )
    out.append("</tbody></table>")
    out.append("")
    return out


# ----------------------------------------------------------------------------
# Main orchestration
# ----------------------------------------------------------------------------
def build_markdown(
    rows: list[dict],
    *,
    fmt: str = "html",
    output_dir: Path | None = None,
) -> str:
    months = group_by_month(rows)
    sorted_months = sorted(months.keys(), reverse=True)  # newest first

    out: list[str] = []
    out.append("# Audit log &mdash; user login overview")
    out.append("")
    out.append(
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
        f"&middot; users in input: **{len(rows)}** "
        f"&middot; months with activity: **{len(sorted_months)}***"
    )
    out.append("")

    # Azure DevOps Wiki auto-generated table of contents.
    out.append("[[_TOC_]]")
    out.append("")
    out.append("---")
    out.append("")

    # ---- Chapter 1: Monthly overview (calendars only) --------------------
    out.append("## 1. Monthly overview")
    out.append("")
    for i, ym in enumerate(sorted_months, 1):
        out.append(render_month_overview(
            ym[0], ym[1], months[ym],
            fmt=fmt, output_dir=output_dir,
            prefix=f"1.{i} ",
        ))
        out.append("")

    out.append("---")
    out.append("")

    # ---- Chapter 2: Monthly detail ---------------------------------------
    # Re-organized so the same KIND of information is grouped together:
    # first all months' account/domain tables, then all months' per-user
    # collapsible login logs.
    out.append("## 2. Monthly detail")
    out.append("")

    # 2.1 Accounts by domain
    out.append("### 2.1 Accounts by domain")
    out.append("")
    for i, ym in enumerate(sorted_months, 1):
        out.append(render_month_accounts(
            ym[0], ym[1], months[ym],
            prefix=f"2.1.{i} ",
        ))
        out.append("")

    # 2.2 Login details
    out.append("### 2.2 Login details")
    out.append("")
    for i, ym in enumerate(sorted_months, 1):
        out.append(render_month_logins(
            ym[0], ym[1], months[ym],
            prefix=f"2.2.{i} ",
        ))
        out.append("")

    return "\n".join(out)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="auditlog_to_md.py",
        description=(
            "Convert an audit-log CSV (userId, lastlogin, logins) into a "
            "Markdown report for Azure DevOps Wiki."
        ),
    )
    parser.add_argument(
        "input",
        help="Path to the input CSV file",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Path to the output .md file (default: input filename with .md)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["html", "png", "jpeg"],
        default="html",
        help=(
            "How to render the calendar tables. 'html' (default) emits an "
            "HTML <table> inline in the .md; 'png' or 'jpeg' saves each "
            "calendar as an image in an .attachments/ folder next to the .md "
            "and references it from the markdown. Image modes require Pillow."
        ),
    )
    args = parser.parse_args(argv[1:])

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"ERROR: input file does not exist: {input_path}", file=sys.stderr)
        return 2

    output_path = (
        Path(args.output) if args.output else input_path.with_suffix(".md")
    )

    try:
        rows = read_csv(input_path)
    except Exception as exc:
        print(f"ERROR while reading CSV: {exc}", file=sys.stderr)
        return 3

    if not rows:
        print("WARNING: input contains no records.", file=sys.stderr)

    md = build_markdown(
        rows,
        fmt=args.format,
        output_dir=output_path.parent,
    )
    output_path.write_text(md, encoding="utf-8")

    md_kb = output_path.stat().st_size / 1024
    md_abs = output_path.resolve()
    print(f"OK: wrote {md_abs}  ({md_kb:.1f} KB)")
    print(f"    users in input: {len(rows)}")
    print(f"    format:         {args.format}")

    if args.format in ("png", "jpeg"):
        attachments_dir = (output_path.parent / ".attachments").resolve()
        imgs = sorted(
            attachments_dir.glob(f"{IMAGE_PREFIX}_*.{args.format}")
        )
        if imgs:
            total_kb = sum(p.stat().st_size for p in imgs) / 1024
            print(f"    images:         {len(imgs)} file(s), "
                  f"{total_kb:.1f} KB total in:")
            print(f"      {attachments_dir}")
            for p in imgs:
                kb = p.stat().st_size / 1024
                print(f"        - {p.name}  ({kb:.1f} KB)")
        else:
            print(f"    WARNING: no images found in {attachments_dir}",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
