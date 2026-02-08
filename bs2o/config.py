from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "paths": {
        "input_pdf_dir": "./pdf_report",
        "mineru_output_dir": "./pdf_convert",
        "export_dir": "./export",
    },
    "mineru": {
        "command": "mineru",
        "args": ["-p", "{input}", "-o", "{output}"],
        "recursive": True,
    },
    "onenote": {
        "enabled": False,
        "graph_enabled": False,
        "notebook_name": "PTSB_transactions",
        "section_name": "PTSB_transactions",
        "page_title": "PTSB_transactions",
        "create_if_missing": True,
        "tenant": "common",
        "client_id": "",
        "scopes": ["Notes.ReadWrite", "offline_access"],
        "token_cache_file": "./.bs2o_graph_token.json",
    },
    "reports": {
        "charts_enabled": True,
        "monthly_table_enabled": True,
    },
}


def expand_path(value: str | Path, base_dir: str | Path | None = None) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(str(value)))
    path = Path(expanded)
    if path.is_absolute():
        return path
    if base_dir is None:
        return Path.cwd() / path
    return Path(base_dir) / path


def _coerce_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none"}:
        return None
    if (value.startswith("\"") and value.endswith("\"")) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    lines = [
        line.rstrip("\n")
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    def _indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def parse_block(start: int, indent: int) -> tuple[Any, int]:
        if start >= len(lines):
            return {}, start
        if lines[start].lstrip().startswith("- "):
            items: list[Any] = []
            idx = start
            while idx < len(lines) and _indent(lines[idx]) == indent and lines[idx].lstrip().startswith("- "):
                items.append(_coerce_scalar(lines[idx].lstrip()[2:]))
                idx += 1
            return items, idx

        obj: dict[str, Any] = {}
        idx = start
        while idx < len(lines):
            line = lines[idx]
            current_indent = _indent(line)
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError(f"Unexpected indentation: {line}")
            stripped = line.strip()
            if ":" not in stripped:
                raise ValueError(f"Invalid YAML line: {line}")
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            idx += 1
            if value == "":
                child, idx = parse_block(idx, indent + 2)
                obj[key] = child
            else:
                obj[key] = _coerce_scalar(value)
        return obj, idx

    parsed, _ = parse_block(0, 0)
    if not isinstance(parsed, dict):
        raise ValueError("config root must be a mapping")
    return parsed


def _dump_yaml(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_dump_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {json.dumps(item)}" if isinstance(item, str) else f"{prefix}{key}: {item}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(_dump_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}- {json.dumps(item)}" if isinstance(item, str) else f"{prefix}- {item}")
        return lines
    return [f"{prefix}{value}"]


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return deepcopy(DEFAULT_CONFIG)

    text = config_path.read_text(encoding="utf-8", errors="ignore")
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        loaded = _parse_simple_yaml(text)
    if not isinstance(loaded, dict):
        raise ValueError("config file must contain an object at root")
    return deep_merge(DEFAULT_CONFIG, loaded)


def save_config(config_path: Path, config: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("\n".join(_dump_yaml(config)) + "\n", encoding="utf-8")
