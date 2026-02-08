from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path


def discover_pdfs(input_dir: Path, recursive: bool = True) -> list[Path]:
    if recursive:
        files = sorted(input_dir.rglob("*.pdf"))
    else:
        files = sorted(input_dir.glob("*.pdf"))
    return [f for f in files if f.is_file()]


def discover_markdowns(output_dir: Path) -> list[Path]:
    return sorted([p for p in output_dir.rglob("*.md") if p.is_file()])


def split_command(command: str) -> list[str]:
    return shlex.split(command, posix=(os.name != "nt"))


def build_command(command: str, args: list[str], pdf_path: Path, out_dir: Path) -> list[str]:
    base = split_command(command)
    rendered_args = [arg.format(input=str(pdf_path), output=str(out_dir)) for arg in args]
    return [*base, *rendered_args]


def convert_pdf(
    pdf_path: Path,
    output_root: Path,
    command: str,
    args: list[str],
    force: bool,
    logger: logging.Logger,
) -> list[Path]:
    pdf_out_dir = output_root / pdf_path.stem
    existing = discover_markdowns(pdf_out_dir)
    if existing and not force:
        logger.info("Skipping already converted file: %s", pdf_path)
        return existing

    pdf_out_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_command(command, args, pdf_path, pdf_out_dir)
    logger.info("Running MinerU for %s", pdf_path)
    proc = subprocess.run(cmd, shell=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"MinerU failed for {pdf_path}. exit={proc.returncode}. stderr={proc.stderr.strip()[:500]}"
        )

    outputs = discover_markdowns(pdf_out_dir)
    if not outputs:
        raise RuntimeError(f"MinerU did not produce markdown files for {pdf_path}")
    return outputs


def convert_folder(
    input_dir: Path,
    output_dir: Path,
    command: str,
    args: list[str],
    recursive: bool,
    force: bool,
    fail_fast: bool,
    logger: logging.Logger,
) -> list[Path]:
    md_files: list[Path] = []
    for pdf in discover_pdfs(input_dir, recursive=recursive):
        try:
            md_files.extend(convert_pdf(pdf, output_dir, command, args, force=force, logger=logger))
        except Exception as exc:
            logger.error("Failed to convert %s: %s", pdf, exc)
            if fail_fast:
                raise
    # Deduplicate while preserving deterministic order.
    return sorted(set(md_files))
