from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .models import Transaction

CSV_COLUMNS = [
    "date_iso",
    "details",
    "withdrawn",
    "paid_in",
    "balance",
    "source_pdf",
    "source_md",
    "source_row",
]


def group_by_month(records: list[Transaction]) -> dict[str, list[Transaction]]:
    grouped: dict[str, list[Transaction]] = defaultdict(list)
    for record in records:
        grouped[record.month_key].append(record)
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def _amount(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _write_csv(path: Path, records: list[Transaction], utf8_bom: bool) -> None:
    encoding = "utf-8-sig" if utf8_bom else "utf-8"
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for r in records:
            writer.writerow(
                [
                    r.date_iso,
                    r.details,
                    _amount(r.withdrawn),
                    _amount(r.paid_in),
                    _amount(r.balance),
                    r.source_pdf,
                    r.source_md,
                    r.source_row,
                ]
            )


def export_csv_files(records: list[Transaction], export_dir: Path, utf8_bom: bool = False) -> dict[str, Path]:
    export_dir.mkdir(parents=True, exist_ok=True)
    monthly = group_by_month(records)
    outputs: dict[str, Path] = {}

    for month, month_records in monthly.items():
        path = export_dir / f"{month}.csv"
        _write_csv(path, month_records, utf8_bom=utf8_bom)
        outputs[month] = path

    all_path = export_dir / "all_transactions.csv"
    _write_csv(all_path, records, utf8_bom=utf8_bom)
    outputs["all"] = all_path
    return outputs


def export_excel(records: list[Transaction], export_dir: Path) -> Path:
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError("Excel export requires openpyxl. Install it and rerun with --excel.") from exc

    workbook = Workbook()
    default_sheet = workbook.active
    workbook.remove(default_sheet)

    for month, month_records in group_by_month(records).items():
        sheet = workbook.create_sheet(title=month)
        sheet.append(CSV_COLUMNS)
        for r in month_records:
            sheet.append(
                [
                    r.date_iso,
                    r.details,
                    r.withdrawn,
                    r.paid_in,
                    r.balance,
                    r.source_pdf,
                    r.source_md,
                    r.source_row,
                ]
            )

    output_path = export_dir / "monthly_transactions.xlsx"
    workbook.save(output_path)
    return output_path


def load_transactions_from_csv(all_csv: Path) -> list[Transaction]:
    rows: list[Transaction] = []
    with all_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                Transaction(
                    date_iso=row["date_iso"],
                    details=row["details"],
                    withdrawn=float(row["withdrawn"]) if row["withdrawn"] else None,
                    paid_in=float(row["paid_in"]) if row["paid_in"] else None,
                    balance=float(row["balance"]) if row["balance"] else None,
                    source_pdf=row["source_pdf"],
                    source_md=row["source_md"],
                    source_row=int(row["source_row"]),
                )
            )
    rows.sort(key=lambda r: (r.date_iso, r.source_md, r.source_row))
    return rows
