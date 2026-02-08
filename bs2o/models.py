from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Transaction:
    date_iso: str
    details: str
    withdrawn: float | None
    paid_in: float | None
    balance: float | None
    source_pdf: str
    source_md: str
    source_row: int

    @property
    def month_key(self) -> str:
        return self.date_iso[:7].replace("-", ".")
