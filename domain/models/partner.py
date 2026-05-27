"""Partner: khách hàng / nhà cung cấp (unified)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PartnerType(str, Enum):
    CUSTOMER = "CUSTOMER"
    SUPPLIER = "SUPPLIER"
    BOTH = "BOTH"


@dataclass
class Partner:
    code: str
    name: str
    type: PartnerType = PartnerType.CUSTOMER
    tax_code: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    contact_person: str = ""
    bank_account: str = ""
    bank_name: str = ""
    notes: str = ""
    active: bool = True
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def display_label(self) -> str:
        return f"{self.code} — {self.name}"
