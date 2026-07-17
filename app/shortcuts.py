"""Keyboard shortcut definitions per plan section 7."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Shortcut:
    key: str
    action: str
    description: str


SHORTCUTS: tuple[Shortcut, ...] = (
    Shortcut("F1", "module.help", "Hướng dẫn sử dụng"),
    Shortcut("F2", "module.dashboard", "Tổng quan"),
    Shortcut("F3", "module.journal", "Sổ nhật ký chung"),
    Shortcut("F4", "module.sales", "Bán hàng"),
    Shortcut("F5", "module.purchase", "Mua hàng"),
    Shortcut("F6", "module.inventory", "Kho hàng"),
    Shortcut("F7", "module.cash", "Quỹ & Ngân hàng"),
    Shortcut("F8", "module.assets", "Tài sản cố định"),
    Shortcut("F9", "module.reports", "Báo cáo tài chính"),
    Shortcut("F10", "module.tax", "Báo cáo thuế"),
    Shortcut("Ctrl+N", "entry.new", "Bút toán mới"),
    Shortcut("Ctrl+I", "invoice.new", "Hóa đơn VAT mới"),
    Shortcut("Ctrl+K", "search.global", "Tìm kiếm toàn cục"),
    Shortcut("Ctrl+S", "transaction.save", "Lưu / ghi sổ"),
    Shortcut("Ctrl+P", "report.print", "In báo cáo"),
)
