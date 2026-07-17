"""CompanyProfile: thông tin người nộp thuế (doanh nghiệp đang sử dụng phần mềm).

Một bản ghi duy nhất, lưu trong bảng ``settings`` (key/value). Dùng để điền sẵn
phần đầu các tờ khai thuế (tên người nộp thuế [04], mã số thuế [05]…).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompanyProfile:
    name: str = ""          # Tên người nộp thuế
    tax_code: str = ""      # Mã số thuế (MST)
    address: str = ""       # Địa chỉ trụ sở

    @property
    def is_filled(self) -> bool:
        return bool(self.name.strip() or self.tax_code.strip())
