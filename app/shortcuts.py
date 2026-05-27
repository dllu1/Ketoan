"""Keyboard shortcut definitions per plan section 7."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Shortcut:
    key: str
    action: str
    description: str


SHORTCUTS: tuple[Shortcut, ...] = (
    Shortcut("F1", "help", "Mở trợ giúp"),
    Shortcut("F2", "module.dashboard", "Tổng quan"),
    Shortcut("F3", "module.sales", "Bán hàng"),
    Shortcut("F4", "module.purchase", "Mua hàng"),
    Shortcut("F5", "module.inventory", "Kho - NXT"),
    Shortcut("F6", "module.journal", "Sổ nhật ký chung"),
    Shortcut("F7", "module.assets", "Tài sản cố định"),
    Shortcut("F8", "module.reports", "Báo cáo"),
    Shortcut("F9", "module.directory", "Danh mục"),
    Shortcut("F10", "module.settings", "Cấu hình"),
    Shortcut("Ctrl+N", "entry.new", "Bút toán mới"),
    Shortcut("Ctrl+I", "invoice.new", "Hóa đơn VAT mới"),
    Shortcut("Ctrl+K", "search.global", "Tìm kiếm toàn cục"),
    Shortcut("Ctrl+S", "transaction.save", "Lưu / ghi sổ"),
    Shortcut("Ctrl+P", "report.print", "In báo cáo"),
)
