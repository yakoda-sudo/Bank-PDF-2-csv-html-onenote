from __future__ import annotations

import math
import struct
import zlib
from collections import defaultdict
from datetime import date
from pathlib import Path

from .exporter import group_by_month
from .models import Transaction

try:
    import matplotlib.pyplot as plt  # type: ignore

    _HAS_MATPLOTLIB = True
except Exception:
    _HAS_MATPLOTLIB = False

Color = tuple[int, int, int]

_DIGIT_FONT = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "001", "001", "001"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    ".": ["000", "000", "000", "000", "010"],
    "-": ["000", "000", "111", "000", "000"],
    ",": ["000", "000", "000", "010", "100"],
    " ": ["000", "000", "000", "000", "000"],
}

INCOME_COLOR = (44 / 255.0, 127 / 255.0, 184 / 255.0)  # blue
SPENDING_COLOR = (242 / 255.0, 142 / 255.0, 43 / 255.0)  # orange


class Canvas:
    def __init__(self, width: int, height: int, background: Color = (255, 255, 255)) -> None:
        self.width = width
        self.height = height
        self.pixels = [background] * (width * height)

    def set_pixel(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y * self.width + x] = color

    def draw_line(self, x1: int, y1: int, x2: int, y2: int, color: Color) -> None:
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx + dy
        x, y = x1, y1
        while True:
            self.set_pixel(x, y, color)
            if x == x2 and y == y2:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def draw_rect(self, x: int, y: int, w: int, h: int, color: Color, fill: bool = True) -> None:
        if w <= 0 or h <= 0:
            return
        if fill:
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    self.set_pixel(xx, yy, color)
            return
        self.draw_line(x, y, x + w - 1, y, color)
        self.draw_line(x, y, x, y + h - 1, color)
        self.draw_line(x + w - 1, y, x + w - 1, y + h - 1, color)
        self.draw_line(x, y + h - 1, x + w - 1, y + h - 1, color)

    def draw_text(self, x: int, y: int, text: str, color: Color, scale: int = 1) -> None:
        cursor_x = x
        for char in text:
            glyph = _DIGIT_FONT.get(char, _DIGIT_FONT[" "])
            for gy, row in enumerate(glyph):
                for gx, px in enumerate(row):
                    if px != "1":
                        continue
                    for sy in range(scale):
                        for sx in range(scale):
                            self.set_pixel(cursor_x + gx * scale + sx, y + gy * scale + sy, color)
            cursor_x += (len(glyph[0]) + 1) * scale


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def save_png(path: Path, canvas: Canvas) -> None:
    raw = bytearray()
    for y in range(canvas.height):
        raw.append(0)
        for x in range(canvas.width):
            r, g, b = canvas.pixels[y * canvas.width + x]
            raw.extend((r, g, b))

    ihdr = struct.pack(">IIBBBBB", canvas.width, canvas.height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), level=9)
    png = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")
    path.write_bytes(png)


def summarize_month(month_records: list[Transaction]) -> dict[str, float]:
    total_income = round(sum(r.paid_in or 0.0 for r in month_records), 2)
    total_spending = round(sum(r.withdrawn or 0.0 for r in month_records), 2)
    net_increase = round(total_income - total_spending, 2)
    return {
        "total_income": total_income,
        "total_spending": total_spending,
        "net_increase": net_increase,
    }


def _month_days(month_records: list[Transaction]) -> list[str]:
    first = month_records[0].date_iso
    year = int(first[:4])
    month = int(first[5:7])

    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    days: list[str] = []
    cur = start
    while cur < end:
        days.append(cur.isoformat())
        cur = date.fromordinal(cur.toordinal() + 1)
    return days


def _daily_series(month_records: list[Transaction]) -> tuple[list[str], list[float], list[float]]:
    days = _month_days(month_records)
    daily_income = defaultdict(float)
    daily_spending = defaultdict(float)

    for record in month_records:
        if record.paid_in:
            daily_income[record.date_iso] += record.paid_in
        if record.withdrawn:
            daily_spending[record.date_iso] += record.withdrawn

    income = [round(daily_income[d], 2) for d in days]
    spending = [round(daily_spending[d], 2) for d in days]
    return days, income, spending


def _generate_with_matplotlib(month: str, month_records: list[Transaction], summary: dict[str, float], charts_dir: Path) -> tuple[Path, Path]:
    days, income, spending = _daily_series(month_records)

    # Pie with true ratio based on total income vs spending.
    pie_path = charts_dir / f"{month}_income_vs_spending.png"
    fig, ax = plt.subplots(figsize=(4.4, 2.6), dpi=100)
    sizes = [summary["total_income"], summary["total_spending"]]

    def _fmt_autopct(pct: float) -> str:
        total = sum(sizes)
        value = (pct / 100.0) * total
        return "" if value <= 0 else f"{value:.2f}"

    wedges, _, autotexts = ax.pie(
        sizes,
        startangle=90,
        colors=[INCOME_COLOR, SPENDING_COLOR],
        autopct=_fmt_autopct,
        textprops={"color": "#1f1f1f", "fontsize": 8},
    )
    for txt in autotexts:
        txt.set_fontsize(8)
    ax.legend(
        wedges,
        [f"Income: {summary['total_income']:.2f}", f"Spending: {summary['total_spending']:.2f}"],
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
    )
    ax.set_title(f"{month} Income vs Spending", fontsize=9)
    fig.tight_layout()
    fig.savefig(pie_path)
    plt.close(fig)

    # Dense bar chart: every day in x-axis, visible in one month.
    bar_path = charts_dir / f"{month}_daily_income_spending.png"
    fig, ax = plt.subplots(figsize=(9.0, 3.2), dpi=100)
    x = list(range(len(days)))
    # Stack as: income at bottom, spending on top.
    ax.bar(x, income, color=INCOME_COLOR, width=0.76, label="Daily Income")
    ax.bar(x, spending, bottom=income, color=SPENDING_COLOR, width=0.76, label="Daily Spending")

    totals = [round(spending[i] + income[i], 2) for i in range(len(days))]
    ymax = max(totals) if any(totals) else 1.0
    for i in range(len(days)):
        income_val = income[i]
        spend_val = spending[i]
        total = totals[i]
        if total <= 0:
            continue

        # Place labels above bar in strict stacked order so they never overlap:
        # top segment label first, then lower segment label.
        base_y = total + ymax * 0.01
        step = ymax * 0.03
        if income_val > 0 and spend_val > 0:
            # spending is on top in current stack.
            ax.text(i, base_y + step, f"{spend_val:.2f}", ha="center", va="bottom", fontsize=6, color="#1f1f1f")
            ax.text(i, base_y, f"{income_val:.2f}", ha="center", va="bottom", fontsize=6, color="#1f1f1f")
        elif spend_val > 0:
            ax.text(i, base_y, f"{spend_val:.2f}", ha="center", va="bottom", fontsize=6, color="#1f1f1f")
        elif income_val > 0:
            ax.text(i, base_y, f"{income_val:.2f}", ha="center", va="bottom", fontsize=6, color="#1f1f1f")

    ax.set_xticks(x)
    ax.set_xticklabels([d[8:10] for d in days], fontsize=6)
    ax.set_xlabel("Day of Month", fontsize=8)
    ax.set_ylabel("Amount", fontsize=8)
    ax.set_xlim(-0.6, len(days) - 0.4)
    ax.grid(axis="y", linestyle="--", alpha=0.25)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", frameon=False)
    ax.set_title(f"{month} Daily Income and Spending (Every Day)", fontsize=9)
    fig.tight_layout()
    fig.savefig(bar_path)
    plt.close(fig)

    return pie_path, bar_path


def _to_rgb(color: tuple[float, float, float]) -> Color:
    return (int(color[0] * 255), int(color[1] * 255), int(color[2] * 255))


def _format_amount(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _fallback_pie(canvas: Canvas, income: float, spending: float) -> None:
    income_color = _to_rgb(INCOME_COLOR)
    spending_color = _to_rgb(SPENDING_COLOR)
    text_color = (35, 35, 35)

    cx, cy = canvas.width // 2 - 80, canvas.height // 2
    radius = min(canvas.width, canvas.height) // 3
    total = income + spending
    ratio = 0.5 if total <= 0 else (income / total)

    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            dx = x - cx
            dy = y - cy
            if dx * dx + dy * dy > radius * radius:
                continue
            angle = (math.atan2(dy, dx) + 2 * math.pi) / (2 * math.pi)
            color = income_color if angle <= ratio else spending_color
            canvas.set_pixel(x, y, color)

    # value labels; tiny slice can skip in-slice label.
    if ratio >= 0.08:
        mid = (ratio / 2) * 2 * math.pi
        canvas.draw_text(int(cx + math.cos(mid) * radius * 0.55), int(cy + math.sin(mid) * radius * 0.55), _format_amount(income), text_color, scale=2)
    if (1.0 - ratio) >= 0.08:
        mid = (ratio + (1.0 - ratio) / 2) * 2 * math.pi
        canvas.draw_text(int(cx + math.cos(mid) * radius * 0.55), int(cy + math.sin(mid) * radius * 0.55), _format_amount(spending), text_color, scale=2)


def _fallback_bars(canvas: Canvas, month_records: list[Transaction]) -> None:
    margin = 44
    axis = (100, 100, 100)
    income_color = _to_rgb(INCOME_COLOR)
    spending_color = _to_rgb(SPENDING_COLOR)
    text_color = (35, 35, 35)

    days, income, spending = _daily_series(month_records)
    totals = [income[i] + spending[i] for i in range(len(days))]

    canvas.draw_line(margin, canvas.height - margin, canvas.width - margin, canvas.height - margin, axis)
    canvas.draw_line(margin, margin, margin, canvas.height - margin, axis)

    vmax = max(totals) if any(totals) else 1.0
    plot_w = canvas.width - (2 * margin)
    plot_h = canvas.height - (2 * margin)
    bucket_w = max(3, int(plot_w / len(days)))
    bar_w = max(2, min(14, bucket_w - 1))

    for i, day in enumerate(days):
        total = totals[i]
        x0 = margin + i * bucket_w
        bar_left = x0 + max(0, (bucket_w - bar_w) // 2)

        if total > 0:
            total_h = max(1, int((total / vmax) * plot_h))
            spending_h = int((spending[i] / total) * total_h) if total > 0 else 0
            income_h = total_h - spending_h
            spend_top = canvas.height - margin - spending_h
            income_top = spend_top - income_h

            if spending_h > 0:
                canvas.draw_rect(bar_left, spend_top, bar_w, spending_h, spending_color, fill=True)
            if income_h > 0:
                canvas.draw_rect(bar_left, income_top, bar_w, income_h, income_color, fill=True)
            canvas.draw_rect(bar_left, income_top, bar_w, total_h, (65, 65, 65), fill=False)

            if bucket_w >= 12:
                # Keep number sequence aligned with stacked order: top segment label above lower segment label.
                label_top = max(margin, income_top - 8)
                if income_h > 0 and spending_h > 0:
                    if income_top < spend_top:
                        canvas.draw_text(bar_left - 1, label_top, _format_amount(income[i]), text_color, scale=1)
                        canvas.draw_text(bar_left - 1, label_top + 8, _format_amount(spending[i]), text_color, scale=1)
                    else:
                        canvas.draw_text(bar_left - 1, label_top, _format_amount(spending[i]), text_color, scale=1)
                        canvas.draw_text(bar_left - 1, label_top + 8, _format_amount(income[i]), text_color, scale=1)
                elif income_h > 0:
                    canvas.draw_text(bar_left - 1, label_top, _format_amount(income[i]), text_color, scale=1)
                elif spending_h > 0:
                    canvas.draw_text(bar_left - 1, label_top, _format_amount(spending[i]), text_color, scale=1)

        # every day label shown to satisfy dense x-axis requirement.
        canvas.draw_line(x0, canvas.height - margin, x0, canvas.height - margin + 4, axis)
        canvas.draw_text(x0 - 4, canvas.height - margin + 7, day[8:10], text_color, scale=1)


def generate_monthly_charts(records: list[Transaction], export_dir: Path) -> dict[str, dict[str, Path | dict[str, float]]]:
    charts_dir = export_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, dict[str, Path | dict[str, float]]] = {}

    for month, month_records in group_by_month(records).items():
        if not month_records:
            continue

        summary = summarize_month(month_records)

        if _HAS_MATPLOTLIB:
            pie_path, bar_path = _generate_with_matplotlib(month, month_records, summary, charts_dir)
        else:
            pie = Canvas(380, 210)
            _fallback_pie(pie, income=summary["total_income"], spending=summary["total_spending"])
            pie_path = charts_dir / f"{month}_income_vs_spending.png"
            save_png(pie_path, pie)

            days = _month_days(month_records)
            # dynamic width keeps every day visible in fallback mode.
            width = max(600, 30 * len(days))
            bar = Canvas(width, 230)
            _fallback_bars(bar, month_records)
            bar_path = charts_dir / f"{month}_daily_income_spending.png"
            save_png(bar_path, bar)

        outputs[month] = {"pie": pie_path, "bar": bar_path, "summary": summary}

    return outputs
