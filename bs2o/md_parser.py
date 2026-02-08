from __future__ import annotations

import html
import re
from pathlib import Path

from .models import Transaction

_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

_TABLE_RE = re.compile(r"<table[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_DATE_RE = re.compile(r"^(\d{2})([A-Za-z]{3})(\d{2})$")


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = value.replace("\xa0", " ")
    return " ".join(value.split())


def parse_date(value: str) -> str | None:
    text = _clean_text(value).upper()
    match = _DATE_RE.match(text)
    if not match:
        return None
    day = int(match.group(1))
    month_name = match.group(2)
    year = 2000 + int(match.group(3))
    month = _MONTHS.get(month_name)
    if not month:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_amount(value: str) -> float | None:
    text = _clean_text(value)
    if not text:
        return None
    text = text.replace(",", "")
    text = re.sub(r"[^0-9.-]", "", text)
    if not text:
        return None
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def parse_statement_markdown(md_path: Path, source_pdf: str | None = None) -> list[Transaction]:
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    records: list[Transaction] = []
    row_no = 0

    if source_pdf is None:
        source_pdf = f"{md_path.parent.name}.pdf"

    for table_match in _TABLE_RE.finditer(text):
        table_text = table_match.group(1)
        header_seen = False
        for row_match in _ROW_RE.finditer(table_text):
            row_no += 1
            cols = [_clean_text(c) for c in _CELL_RE.findall(row_match.group(1))]
            if len(cols) < 5:
                continue
            cols = cols[:5]

            normalized = [c.lower() for c in cols]
            if normalized == ["date", "details", "withdrawn", "paid in", "balance"]:
                header_seen = True
                continue
            if not header_seen:
                continue

            date_iso = parse_date(cols[0])
            if not date_iso:
                continue

            details = cols[1]
            withdrawn = parse_amount(cols[2])
            paid_in = parse_amount(cols[3])
            balance = parse_amount(cols[4])

            if withdrawn is None and paid_in is None and balance is None and not details:
                continue

            records.append(
                Transaction(
                    date_iso=date_iso,
                    details=details,
                    withdrawn=withdrawn,
                    paid_in=paid_in,
                    balance=balance,
                    source_pdf=source_pdf,
                    source_md=str(md_path),
                    source_row=row_no,
                )
            )

    records.sort(key=lambda r: (r.date_iso, r.source_md, r.source_row))
    return records


def parse_many_markdowns(md_files: list[Path]) -> list[Transaction]:
    records: list[Transaction] = []
    for md_file in md_files:
        records.extend(parse_statement_markdown(md_file))
    records.sort(key=lambda r: (r.date_iso, r.source_md, r.source_row))
    return records
