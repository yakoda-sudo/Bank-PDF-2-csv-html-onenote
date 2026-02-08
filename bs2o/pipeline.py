from __future__ import annotations

import logging
import re
from pathlib import Path

from .charts import generate_monthly_charts
from .exporter import export_csv_files, export_excel, group_by_month, load_transactions_from_csv
from .md_parser import parse_many_markdowns
from .mineru_runner import convert_folder, discover_markdowns
from .models import Transaction
from .onenote_sync import GraphSettings, sync_to_onenote_graph, sync_to_onenote_preview


class RedactDigitsFilter(logging.Filter):
    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.enabled = enabled
        self.pattern = re.compile(r"\d{6,}")

    def filter(self, record: logging.LogRecord) -> bool:
        if self.enabled:
            msg = str(record.getMessage())
            record.msg = self.pattern.sub("[REDACTED]", msg)
            record.args = ()
        return True


def build_logger(redact_logs: bool) -> logging.Logger:
    logger = logging.getLogger("bs2o")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)
    logger.filters = [RedactDigitsFilter(redact_logs)]
    return logger


def filter_by_date(records: list[Transaction], start_date: str | None, end_date: str | None) -> list[Transaction]:
    filtered = records
    if start_date:
        filtered = [r for r in filtered if r.date_iso >= start_date]
    if end_date:
        filtered = [r for r in filtered if r.date_iso <= end_date]
    return filtered


def run_pipeline(
    input_dir: Path,
    output_dir: Path,
    export_dir: Path,
    mineru_command: str,
    mineru_args: list[str],
    recursive: bool,
    force: bool,
    fail_fast: bool,
    charts_enabled: bool,
    excel: bool,
    utf8_bom: bool,
    start_date: str | None,
    end_date: str | None,
    onenote_enabled: bool,
    onenote_notebook_name: str,
    onenote_section_name: str,
    onenote_page_title: str,
    onenote_graph_enabled: bool,
    onenote_tenant: str,
    onenote_client_id: str,
    onenote_scopes: list[str],
    onenote_token_cache_file: Path,
    redact_logs: bool,
) -> dict[str, object]:
    logger = build_logger(redact_logs)

    md_files = convert_folder(
        input_dir=input_dir,
        output_dir=output_dir,
        command=mineru_command,
        args=mineru_args,
        recursive=recursive,
        force=force,
        fail_fast=fail_fast,
        logger=logger,
    )
    if not md_files:
        logger.warning("No markdown files were generated.")
        return {"records": 0, "exports": {}, "charts": {}, "onenote_preview": None}

    records = parse_many_markdowns(md_files)
    records = filter_by_date(records, start_date=start_date, end_date=end_date)
    exports = export_csv_files(records, export_dir=export_dir, utf8_bom=utf8_bom)

    if excel:
        exports["excel"] = export_excel(records, export_dir=export_dir)

    chart_paths = generate_monthly_charts(records, export_dir=export_dir) if charts_enabled else {}

    preview = None
    onenote_web_url = None
    if onenote_enabled:
        preview, payload_html = sync_to_onenote_preview(
            export_dir=export_dir,
            month_records=group_by_month(records),
            chart_paths=chart_paths,
            target_page_title=onenote_page_title,
            notebook_name=onenote_notebook_name,
            section_name=onenote_section_name,
        )
        if onenote_graph_enabled:
            settings = GraphSettings(
                enabled=True,
                tenant=onenote_tenant,
                client_id=onenote_client_id,
                scopes=onenote_scopes,
                token_cache_file=onenote_token_cache_file,
                notebook_name=onenote_notebook_name,
                section_name=onenote_section_name,
                page_title=onenote_page_title,
            )
            onenote_web_url = sync_to_onenote_graph(payload_html, settings)

    return {
        "records": len(records),
        "exports": exports,
        "charts": chart_paths,
        "onenote_preview": preview,
        "onenote_web_url": onenote_web_url,
    }


def export_only(
    output_dir: Path,
    export_dir: Path,
    charts_enabled: bool,
    excel: bool,
    utf8_bom: bool,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, object]:
    md_files = discover_markdowns(output_dir)
    records = filter_by_date(parse_many_markdowns(md_files), start_date=start_date, end_date=end_date)
    exports = export_csv_files(records, export_dir=export_dir, utf8_bom=utf8_bom)
    if excel:
        exports["excel"] = export_excel(records, export_dir=export_dir)
    charts = generate_monthly_charts(records, export_dir=export_dir) if charts_enabled else {}
    return {"records": len(records), "exports": exports, "charts": charts}


def sync_only(
    all_csv: Path,
    export_dir: Path,
    page_title: str,
    notebook_name: str,
    section_name: str,
    graph_enabled: bool,
    tenant: str,
    client_id: str,
    scopes: list[str],
    token_cache_file: Path,
) -> tuple[Path, str | None]:
    records = load_transactions_from_csv(all_csv)
    grouped = group_by_month(records)
    charts: dict[str, dict[str, Path]] = {}
    for month in grouped:
        pie = export_dir / "charts" / f"{month}_income_vs_spending.png"
        bar = export_dir / "charts" / f"{month}_daily_income_spending.png"
        month_charts: dict[str, Path] = {}
        if pie.exists():
            month_charts["pie"] = pie
        if bar.exists():
            month_charts["bar"] = bar
        if month_charts:
            charts[month] = month_charts
    preview, payload_html = sync_to_onenote_preview(export_dir, grouped, charts, page_title, notebook_name, section_name)
    web_url = None
    if graph_enabled:
        settings = GraphSettings(
            enabled=True,
            tenant=tenant,
            client_id=client_id,
            scopes=scopes,
            token_cache_file=token_cache_file,
            notebook_name=notebook_name,
            section_name=section_name,
            page_title=page_title,
        )
        web_url = sync_to_onenote_graph(payload_html, settings)
    return preview, web_url
