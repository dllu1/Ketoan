"""TransferRule: một dòng cấu hình kết chuyển (TK nguồn → TK đích, theo chiều)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class TransferDirection(str, Enum):
    """Chiều ghi sổ của bút toán kết chuyển, đặt tên theo phía của TK nguồn."""

    # Nợ TK nguồn / Có TK đích — số dư Có được kết chuyển đi (doanh thu, thu nhập).
    DEBIT_SOURCE = "DEBIT_SOURCE"
    # Có TK nguồn / Nợ TK đích — số dư Nợ được kết chuyển đi (chi phí, giá vốn).
    CREDIT_SOURCE = "CREDIT_SOURCE"

    @property
    def label(self) -> str:
        if self is TransferDirection.DEBIT_SOURCE:
            return "Nợ TK nguồn / Có TK đích"
        return "Có TK nguồn / Nợ TK đích"

    @property
    def hint(self) -> str:
        """Nhóm tài khoản thường dùng chiều này — hiện kèm trong ô chọn."""
        if self is TransferDirection.DEBIT_SOURCE:
            return "doanh thu / thu nhập (số dư Có)"
        return "chi phí / giá vốn (số dư Nợ)"

    @property
    def flipped(self) -> "TransferDirection":
        if self is TransferDirection.DEBIT_SOURCE:
            return TransferDirection.CREDIT_SOURCE
        return TransferDirection.DEBIT_SOURCE


@dataclass
class TransferRule:
    """Kết chuyển ``source_account`` sang ``target_account`` theo ``direction``.

    Các quy tắc cùng ``group_ref`` được gộp vào **một** bút toán (số chứng từ
    ``<group_ref>/<kỳ>``) để sổ nhật ký gọn và dễ đối chiếu.
    """

    source_account: str
    target_account: str = "911"
    direction: TransferDirection = TransferDirection.DEBIT_SOURCE
    group_ref: str = "KC-DT"
    label: str = ""
    include_children: bool = True
    sort_order: int = 0
    active: bool = True
    id: int | None = None

    def matches(self, code: str) -> bool:
        source = self.source_account.strip()
        if not source:
            return False
        return code.startswith(source) if self.include_children else code == source

    @property
    def specificity(self) -> int:
        """Độ dài mã nguồn — mã dài hơn thắng khi một TK khớp nhiều quy tắc."""
        return len(self.source_account.strip())

    def signed_amount(self, debit: Decimal, credit: Decimal) -> Decimal:
        """Số tiền kết chuyển của một TK từ tổng phát sinh Nợ/Có trong kỳ.

        Doanh thu treo bên Có nên lấy Có − Nợ (hàng bán trả lại ghi Nợ thì trừ
        ra); chi phí thì ngược lại.
        """
        if self.direction is TransferDirection.DEBIT_SOURCE:
            return credit - debit
        return debit - credit
