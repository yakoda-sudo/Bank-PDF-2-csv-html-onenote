from __future__ import annotations

import html
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .models import Transaction

START_MARKER = "<!-- BS2O:START -->"
END_MARKER = "<!-- BS2O:END -->"


@dataclass
class GraphSettings:
    enabled: bool
    tenant: str
    client_id: str
    scopes: list[str]
    token_cache_file: Path
    notebook_name: str
    section_name: str
    page_title: str


def replace_managed_block(existing: str, replacement: str) -> str:
    if START_MARKER in existing and END_MARKER in existing:
        return replacement
    if existing and not existing.endswith("\n"):
        existing += "\n"
    return existing + replacement


def _summary_values(rows: list[Transaction]) -> tuple[float, float, float]:
    total_income = round(sum(r.paid_in or 0.0 for r in rows), 2)
    total_spending = round(sum(r.withdrawn or 0.0 for r in rows), 2)
    net_increase = round(total_income - total_spending, 2)
    return total_income, total_spending, net_increase


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def build_report_html(
    month_records: dict[str, list[Transaction]],
    chart_paths: dict[str, dict[str, Path | dict]],
    target_page_title: str,
    notebook_name: str,
    section_name: str,
) -> str:
    lines = [
        START_MARKER,
        "<div data-bs2o='managed'>",
        f"<h1>{_escape(target_page_title)}</h1>",
        f"<p><strong>Notebook:</strong> {_escape(notebook_name)} | <strong>Section:</strong> {_escape(section_name)} | "
        f"<strong>Page:</strong> {_escape(target_page_title)}</p>",
        "<h2>Bank Statement Report</h2>",
    ]
    for month in sorted(month_records.keys()):
        lines.append(f"<h2>{_escape(month)}</h2>")
        lines.append("<table border='1' cellpadding='4' cellspacing='0'>")
        lines.append("<tr><th>Date</th><th>Details</th><th>Withdrawn</th><th>Paid In</th><th>Balance</th></tr>")
        for row in month_records[month]:
            lines.append(
                "<tr>"
                f"<td>{_escape(row.date_iso)}</td>"
                f"<td>{_escape(row.details)}</td>"
                f"<td>{'' if row.withdrawn is None else f'{row.withdrawn:.2f}'}</td>"
                f"<td>{'' if row.paid_in is None else f'{row.paid_in:.2f}'}</td>"
                f"<td>{'' if row.balance is None else f'{row.balance:.2f}'}</td>"
                "</tr>"
            )
        lines.append("</table>")

        total_income, total_spending, net_increase = _summary_values(month_records[month])

        if month in chart_paths:
            pie = chart_paths[month].get("pie")
            bar = chart_paths[month].get("bar")
            if isinstance(pie, Path):
                lines.append(f"<p><img src='{pie.as_uri()}' alt='{_escape(month)} income vs spending pie chart' /></p>")
                lines.append("<p><strong>Pie Color Legend:</strong> Blue = Total Income, Orange = Total Spending</p>")
            if isinstance(bar, Path):
                lines.append(f"<p><img src='{bar.as_uri()}' alt='{_escape(month)} daily income and spending bar chart' /></p>")
                lines.append("<p><strong>Bar Color Legend:</strong> Blue = Daily Income, Orange = Daily Spending</p>")

        lines.append("<table border='1' cellpadding='4' cellspacing='0'>")
        lines.append("<tr><th>Summary</th><th>Amount</th></tr>")
        lines.append(f"<tr><td>Total Spending</td><td>{total_spending:.2f}</td></tr>")
        lines.append(f"<tr><td>Total Income</td><td>{total_income:.2f}</td></tr>")
        lines.append(f"<tr><td>Balance Increase (Income - Spending)</td><td>{net_increase:.2f}</td></tr>")
        lines.append("</table>")

    lines.extend(["</div>", END_MARKER])
    return "\n".join(lines)


def sync_to_onenote_preview(
    export_dir: Path,
    month_records: dict[str, list[Transaction]],
    chart_paths: dict[str, dict[str, Path | dict]],
    target_page_title: str,
    notebook_name: str,
    section_name: str,
) -> tuple[Path, str]:
    preview_path = export_dir / "onenote_sync_preview.html"
    existing = preview_path.read_text(encoding="utf-8", errors="ignore") if preview_path.exists() else ""
    payload = build_report_html(
        month_records=month_records,
        chart_paths=chart_paths,
        target_page_title=target_page_title,
        notebook_name=notebook_name,
        section_name=section_name,
    )
    preview_path.write_text(replace_managed_block(existing, payload), encoding="utf-8")
    return preview_path, payload


def _token_from_cache(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None
    if data.get("expires_at", 0) <= time.time() + 30:
        return None
    token = data.get("access_token")
    return token if isinstance(token, str) and token else None


def _save_token_cache(path: Path, token: str, expires_in: int) -> None:
    payload = {"access_token": token, "expires_at": int(time.time()) + max(60, int(expires_in) - 30)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        path.chmod(0o600)
    except Exception:
        pass


def _device_code_access_token(settings: GraphSettings) -> str:
    cached = _token_from_cache(settings.token_cache_file)
    if cached:
        return cached

    tenant = settings.tenant or "common"
    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
    scope_str = " ".join(settings.scopes)

    dc_resp = requests.post(
        f"{base}/devicecode",
        data={"client_id": settings.client_id, "scope": scope_str},
        timeout=30,
    )
    dc_resp.raise_for_status()
    dc = dc_resp.json()

    print(dc.get("message", "Open Microsoft device login page and enter the code shown."))

    interval = int(dc.get("interval", 5))
    expires_at = time.time() + int(dc.get("expires_in", 900))

    while time.time() < expires_at:
        token_resp = requests.post(
            f"{base}/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": settings.client_id,
                "device_code": dc["device_code"],
            },
            timeout=30,
        )
        payload = token_resp.json()
        if token_resp.status_code == 200:
            token = payload["access_token"]
            _save_token_cache(settings.token_cache_file, token, int(payload.get("expires_in", 3600)))
            return token

        error = payload.get("error")
        if error in {"authorization_pending", "slow_down"}:
            time.sleep(interval + (2 if error == "slow_down" else 0))
            continue

        raise RuntimeError(f"Device code auth failed: {payload}")

    raise RuntimeError("Device code login timed out")


def _graph_get(url: str, token: str) -> dict[str, Any]:
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _graph_post(url: str, token: str, json_payload: dict[str, Any] | None = None, html_payload: str | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    kwargs: dict[str, Any] = {"headers": headers, "timeout": 30}
    if html_payload is not None:
        headers["Content-Type"] = "text/html"
        kwargs["data"] = html_payload.encode("utf-8")
    elif json_payload is not None:
        kwargs["json"] = json_payload
    resp = requests.post(url, **kwargs)
    resp.raise_for_status()
    return resp.json()


def _graph_delete(url: str, token: str) -> None:
    resp = requests.delete(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()


def _find_by_name(items: list[dict[str, Any]], field: str, target: str) -> dict[str, Any] | None:
    needle = target.strip().lower()
    for item in items:
        value = str(item.get(field, "")).strip().lower()
        if value == needle:
            return item
    return None


def _get_or_create_notebook(token: str, name: str) -> dict[str, Any]:
    notebooks = _graph_get("https://graph.microsoft.com/v1.0/me/onenote/notebooks?$select=id,displayName", token).get("value", [])
    found = _find_by_name(notebooks, "displayName", name)
    if found:
        return found
    return _graph_post("https://graph.microsoft.com/v1.0/me/onenote/notebooks", token, json_payload={"displayName": name})


def _get_or_create_section(token: str, notebook_id: str, section_name: str) -> dict[str, Any]:
    sections = _graph_get(
        f"https://graph.microsoft.com/v1.0/me/onenote/notebooks/{notebook_id}/sections?$select=id,displayName",
        token,
    ).get("value", [])
    found = _find_by_name(sections, "displayName", section_name)
    if found:
        return found
    return _graph_post(
        f"https://graph.microsoft.com/v1.0/me/onenote/notebooks/{notebook_id}/sections",
        token,
        json_payload={"displayName": section_name},
    )


def _delete_existing_page_if_any(token: str, section_id: str, page_title: str) -> None:
    pages = _graph_get(
        f"https://graph.microsoft.com/v1.0/me/onenote/sections/{section_id}/pages?$select=id,title",
        token,
    ).get("value", [])
    found = _find_by_name(pages, "title", page_title)
    if not found:
        return
    _graph_delete(f"https://graph.microsoft.com/v1.0/me/onenote/pages/{found['id']}", token)


def sync_to_onenote_graph(payload_html: str, settings: GraphSettings) -> str:
    if not settings.client_id:
        raise RuntimeError("OneNote sync requires onenote.client_id in config")

    token = _device_code_access_token(settings)
    notebook = _get_or_create_notebook(token, settings.notebook_name)
    section = _get_or_create_section(token, notebook["id"], settings.section_name)

    _delete_existing_page_if_any(token, section["id"], settings.page_title)

    page_html = (
        "<!DOCTYPE html><html><head>"
        f"<title>{_escape(settings.page_title)}</title>"
        "<meta charset='utf-8'/>"
        "</head><body>"
        f"{payload_html}"
        "</body></html>"
    )

    created = _graph_post(
        f"https://graph.microsoft.com/v1.0/me/onenote/sections/{section['id']}/pages",
        token,
        html_payload=page_html,
    )
    return str(created.get("links", {}).get("oneNoteWebUrl", {}).get("href", ""))
