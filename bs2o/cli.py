from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG, expand_path, load_config, save_config
from .pipeline import export_only, run_pipeline, sync_only


def _prompt(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def _prompt_bool(label: str, default: bool) -> bool:
    default_text = "true" if default else "false"
    value = input(f"{label} [{default_text}]: ").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "y", "yes"}


def run_init(config_path: Path) -> None:
    cfg = load_config(config_path)
    print("bank-statement-2-onenote setup wizard")

    cfg["paths"]["input_pdf_dir"] = _prompt("Source PDF folder", cfg["paths"]["input_pdf_dir"])
    cfg["paths"]["mineru_output_dir"] = _prompt("MinerU markdown output folder", cfg["paths"]["mineru_output_dir"])
    cfg["paths"]["export_dir"] = _prompt("CSV/XML export folder", cfg["paths"]["export_dir"])
    cfg["mineru"]["command"] = _prompt("MinerU command", cfg["mineru"]["command"])

    cfg["onenote"]["enabled"] = _prompt_bool("Export to OneNote", cfg["onenote"].get("enabled", False))
    cfg["onenote"]["graph_enabled"] = _prompt_bool(
        "Enable real Microsoft OneNote sync",
        cfg["onenote"].get("graph_enabled", False),
    )
    cfg["onenote"]["notebook_name"] = _prompt(
        "OneNote notebook name",
        cfg["onenote"].get("notebook_name", "PTSB_transactions"),
    )
    cfg["onenote"]["section_name"] = _prompt(
        "OneNote tab(section) name",
        cfg["onenote"].get("section_name", "PTSB_transactions"),
    )
    cfg["onenote"]["page_title"] = _prompt(
        "OneNote page name",
        cfg["onenote"].get("page_title", "PTSB_transactions"),
    )
    cfg["onenote"]["tenant"] = _prompt("Azure tenant", cfg["onenote"].get("tenant", "common"))
    cfg["onenote"]["client_id"] = _prompt("Azure app client id", cfg["onenote"].get("client_id", ""))

    save_config(config_path, cfg)
    print(f"Saved configuration to {config_path}")


def run_first_time_setup(config_path: Path) -> None:
    cfg = load_config(config_path)
    print("First run detected. Please answer a few setup questions.")

    cfg["paths"]["input_pdf_dir"] = _prompt("Source PDF folder", cfg["paths"]["input_pdf_dir"])
    cfg["paths"]["mineru_output_dir"] = _prompt(
        "Source MinerU output folder (.md files)",
        cfg["paths"]["mineru_output_dir"],
    )
    cfg["paths"]["export_dir"] = _prompt("Destination CSV/XML export folder", cfg["paths"]["export_dir"])

    cfg["onenote"]["enabled"] = _prompt_bool("Would you like to export to OneNote", True)
    cfg["onenote"]["graph_enabled"] = _prompt_bool("Enable real Microsoft OneNote sync", True)
    cfg["onenote"]["notebook_name"] = _prompt("OneNote notebook name", "PTSB_transactions")
    cfg["onenote"]["section_name"] = _prompt("OneNote tab(section) name", "PTSB_transactions")
    cfg["onenote"]["page_title"] = _prompt("OneNote page name", "PTSB_transactions")
    cfg["onenote"]["tenant"] = _prompt("Azure tenant", "common")
    cfg["onenote"]["client_id"] = _prompt("Azure app client id", "")

    save_config(config_path, cfg)
    print(f"Saved first-run config to {config_path}")


def apply_overrides(cfg: dict, args: argparse.Namespace, config_path: Path) -> dict:
    cfg = {
        **cfg,
        "paths": {**cfg["paths"]},
        "mineru": {**cfg["mineru"]},
        "onenote": {**cfg["onenote"]},
        "reports": {**cfg["reports"]},
    }

    if getattr(args, "input", None):
        cfg["paths"]["input_pdf_dir"] = args.input
    if getattr(args, "out", None):
        cfg["paths"]["mineru_output_dir"] = args.out
    if getattr(args, "export", None):
        cfg["paths"]["export_dir"] = args.export
    if getattr(args, "onenote_page_title", None):
        cfg["onenote"]["page_title"] = args.onenote_page_title
    if getattr(args, "onenote_notebook", None):
        cfg["onenote"]["notebook_name"] = args.onenote_notebook
    if getattr(args, "onenote_section", None):
        cfg["onenote"]["section_name"] = args.onenote_section
    if getattr(args, "onenote_live", False):
        cfg["onenote"]["graph_enabled"] = True

    if getattr(args, "no_onenote", False):
        cfg["onenote"]["enabled"] = False
    if getattr(args, "onenote_create_if_missing", False):
        cfg["onenote"]["create_if_missing"] = True

    base_dir = config_path.parent
    cfg["paths"]["input_pdf_dir"] = str(expand_path(cfg["paths"]["input_pdf_dir"], base_dir))
    cfg["paths"]["mineru_output_dir"] = str(expand_path(cfg["paths"]["mineru_output_dir"], base_dir))
    cfg["paths"]["export_dir"] = str(expand_path(cfg["paths"]["export_dir"], base_dir))
    cfg["onenote"]["token_cache_file"] = str(
        expand_path(cfg["onenote"].get("token_cache_file", "./.bs2o_graph_token.json"), base_dir)
    )

    return cfg


def _add_common_config_arg(parser: argparse.ArgumentParser, set_default: bool) -> None:
    kwargs = {"help": "Path to config yaml"}
    if set_default:
        kwargs["default"] = "./config.yaml"
    else:
        kwargs["default"] = argparse.SUPPRESS
    parser.add_argument("--config", **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bs2o", description="Bank statement to OneNote pipeline")
    _add_common_config_arg(parser, set_default=True)

    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Interactive setup wizard")
    _add_common_config_arg(init, set_default=False)

    run = sub.add_parser("run", help="Convert PDFs, parse markdown, and export")
    _add_common_config_arg(run, set_default=False)
    run.add_argument("--input")
    run.add_argument("--out")
    run.add_argument("--export")
    run.add_argument("--onenote-page-title")
    run.add_argument("--onenote-notebook")
    run.add_argument("--onenote-section")
    run.add_argument("--onenote-live", action="store_true")
    run.add_argument("--onenote-create-if-missing", action="store_true")
    run.add_argument("--no-onenote", action="store_true")
    run.add_argument("--excel", action="store_true")
    run.add_argument("--force", action="store_true")
    run.add_argument("--fail-fast", action="store_true")
    run.add_argument("--start-date")
    run.add_argument("--end-date")
    run.add_argument("--no-recursive", action="store_true")
    run.add_argument("--csv-utf8-bom", action="store_true")
    run.add_argument("--redact-logs", action="store_true")

    export = sub.add_parser("export", help="Export only from existing markdown output")
    _add_common_config_arg(export, set_default=False)
    export.add_argument("--out")
    export.add_argument("--export")
    export.add_argument("--excel", action="store_true")
    export.add_argument("--start-date")
    export.add_argument("--end-date")
    export.add_argument("--csv-utf8-bom", action="store_true")

    sync = sub.add_parser("sync-onenote", help="Sync from existing CSV/charts")
    _add_common_config_arg(sync, set_default=False)
    sync.add_argument("--export")
    sync.add_argument("--onenote-page-title")
    sync.add_argument("--onenote-notebook")
    sync.add_argument("--onenote-section")
    sync.add_argument("--onenote-live", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = expand_path(args.config)

    if args.command == "init":
        run_init(config_path)
        return 0

    if not config_path.exists():
        if not sys.stdin.isatty():
            print(f"Config file not found: {config_path}. Run `bs2o init --config \"{config_path}\"` first.")
            return 2
        run_first_time_setup(config_path)

    cfg = load_config(config_path)
    cfg = apply_overrides(cfg, args, config_path)

    if args.command == "run":
        try:
            result = run_pipeline(
                input_dir=Path(cfg["paths"]["input_pdf_dir"]),
                output_dir=Path(cfg["paths"]["mineru_output_dir"]),
                export_dir=Path(cfg["paths"]["export_dir"]),
                mineru_command=cfg["mineru"].get("command", DEFAULT_CONFIG["mineru"]["command"]),
                mineru_args=cfg["mineru"].get("args", DEFAULT_CONFIG["mineru"]["args"]),
                recursive=not args.no_recursive,
                force=args.force,
                fail_fast=args.fail_fast,
                charts_enabled=cfg["reports"].get("charts_enabled", True),
                excel=args.excel,
                utf8_bom=args.csv_utf8_bom,
                start_date=args.start_date,
                end_date=args.end_date,
                onenote_enabled=cfg["onenote"].get("enabled", False),
                onenote_notebook_name=cfg["onenote"].get("notebook_name", "PTSB_transactions"),
                onenote_section_name=cfg["onenote"].get("section_name", "PTSB_transactions"),
                onenote_page_title=cfg["onenote"].get("page_title", "PTSB_transactions"),
                onenote_graph_enabled=cfg["onenote"].get("graph_enabled", False),
                onenote_tenant=cfg["onenote"].get("tenant", "common"),
                onenote_client_id=cfg["onenote"].get("client_id", ""),
                onenote_scopes=cfg["onenote"].get("scopes", ["Notes.ReadWrite", "offline_access"]),
                onenote_token_cache_file=Path(cfg["onenote"].get("token_cache_file", "./.bs2o_graph_token.json")),
                redact_logs=args.redact_logs,
            )
        except Exception as exc:
            print(f"run failed: {exc}")
            return 1
        print(f"Processed {result['records']} transactions")
        if result.get("onenote_preview"):
            print(f"OneNote preview updated: {result['onenote_preview']}")
        if result.get("onenote_web_url"):
            print(f"OneNote page synced: {result['onenote_web_url']}")
        return 0

    if args.command == "export":
        result = export_only(
            output_dir=Path(cfg["paths"]["mineru_output_dir"]),
            export_dir=Path(cfg["paths"]["export_dir"]),
            charts_enabled=cfg["reports"].get("charts_enabled", True),
            excel=args.excel,
            utf8_bom=args.csv_utf8_bom,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"Exported {result['records']} transactions")
        return 0

    if args.command == "sync-onenote":
        export_dir = Path(cfg["paths"]["export_dir"])
        all_csv = export_dir / "all_transactions.csv"
        try:
            preview, web_url = sync_only(
                all_csv=all_csv,
                export_dir=export_dir,
                page_title=cfg["onenote"].get("page_title", "PTSB_transactions"),
                notebook_name=cfg["onenote"].get("notebook_name", "PTSB_transactions"),
                section_name=cfg["onenote"].get("section_name", "PTSB_transactions"),
                graph_enabled=cfg["onenote"].get("graph_enabled", False),
                tenant=cfg["onenote"].get("tenant", "common"),
                client_id=cfg["onenote"].get("client_id", ""),
                scopes=cfg["onenote"].get("scopes", ["Notes.ReadWrite", "offline_access"]),
                token_cache_file=Path(cfg["onenote"].get("token_cache_file", "./.bs2o_graph_token.json")),
            )
        except Exception as exc:
            print(f"sync-onenote failed: {exc}")
            return 1
        print(f"OneNote preview synced to: {preview}")
        if web_url:
            print(f"OneNote page synced: {web_url}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
