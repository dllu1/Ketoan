"""Chọn nhiều chứng từ + ghi sổ/xóa hàng loạt trên DocumentScreen.

Chạy headless (QT_QPA_PLATFORM=offscreen), dùng DocumentService giả trong bộ nhớ
nên không chạm database thật.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.period import Period, set_active_period  # noqa: E402
from domain.models.invoice import (  # noqa: E402
    Invoice,
    InvoiceKind,
    InvoiceLine,
    InvoiceStatus,
)
from ui.screens.document_screen import DocumentScreen, DocumentScreenConfig  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeService:
    """DocumentService tối giản: giữ chứng từ trong list, ghi lại lời gọi."""

    def __init__(self, invoices):
        self._invoices = list(invoices)
        self.posted: list[str] = []
        self.deleted: list[str] = []
        self.post_should_fail: set[str] = set()

    def list_all(self, kind=None):
        return list(self._invoices)

    def search(self, query=""):
        return list(self._invoices)

    def post(self, invoice, save_new_partner=False):
        if invoice.ref in self.post_should_fail:
            raise ValueError("số lượng phải lớn hơn 0")
        self.posted.append(invoice.ref)
        invoice.status = InvoiceStatus.POSTED

    def delete(self, invoice):
        self.deleted.append(invoice.ref)
        self._invoices = [i for i in self._invoices if i.ref != invoice.ref]

    def partner_exists(self, code):
        return True          # không hỏi lưu danh mục trong test

    def partner_is_unknown(self, invoice):
        return False


def _invoice(ref: str, invoice_id: int) -> Invoice:
    return Invoice(
        id=invoice_id, ref=ref, invoice_no=ref, serial="1C22TAA",
        invoice_date=date(2026, 1, 15), kind=InvoiceKind.SALE,
        status=InvoiceStatus.DRAFT, partner_code="KH01", partner_name="KH MOT",
        lines=[InvoiceLine(item_code="H1", item_name="Hang 1", unit="cai",
                           quantity=Decimal("1"), unit_price=Decimal("1000"))],
    )


def _screen(service) -> DocumentScreen:
    set_active_period(Period(year=2026, month=None))
    return DocumentScreen(service, DocumentScreenConfig(
        kind=InvoiceKind.SALE, title="Bán hàng", search_placeholder="tìm",
        new_label="Hóa đơn mới", new_icon="invoice",
        partner_header="Khách hàng", partner_noun="khách hàng",
    ))


def _auto_answer(monkeypatch, answer=QMessageBox.Yes):
    """Bấm sẵn nút trả lời cho mọi hộp thoại xác nhận/thông báo."""
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: answer))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))


def test_post_all_posts_every_visible_draft(app, monkeypatch):
    service = _FakeService([_invoice(f"HD-{i}", i) for i in range(1, 4)])
    screen = _screen(service)
    _auto_answer(monkeypatch)

    screen._on_post_all()

    assert service.posted == ["HD-1", "HD-2", "HD-3"]


def test_post_selected_only_touches_chosen_rows(app, monkeypatch):
    service = _FakeService([_invoice(f"HD-{i}", i) for i in range(1, 4)])
    screen = _screen(service)
    _auto_answer(monkeypatch)

    screen._table.selectRow(2)
    screen._on_post()

    assert service.posted == ["HD-3"]


def test_delete_removes_all_selected_rows(app, monkeypatch):
    service = _FakeService([_invoice(f"HD-{i}", i) for i in range(1, 4)])
    screen = _screen(service)
    _auto_answer(monkeypatch)

    screen._table.selectAll()
    screen._on_delete()

    assert service.deleted == ["HD-1", "HD-2", "HD-3"]


def test_failed_document_does_not_stop_the_batch(app, monkeypatch):
    service = _FakeService([_invoice(f"HD-{i}", i) for i in range(1, 4)])
    service.post_should_fail = {"HD-2"}
    screen = _screen(service)
    _auto_answer(monkeypatch)

    screen._on_post_all()

    # HĐ lỗi bị bỏ qua, các chứng từ còn lại vẫn được ghi sổ.
    assert service.posted == ["HD-1", "HD-3"]


def test_cancelling_confirmation_posts_nothing(app, monkeypatch):
    service = _FakeService([_invoice(f"HD-{i}", i) for i in range(1, 4)])
    screen = _screen(service)
    _auto_answer(monkeypatch, answer=QMessageBox.No)

    screen._on_post_all()

    assert service.posted == []


def test_post_all_reports_when_nothing_is_draft(app, monkeypatch):
    service = _FakeService([_invoice("HD-1", 1)])
    service._invoices[0].status = InvoiceStatus.POSTED
    screen = _screen(service)
    _auto_answer(monkeypatch)

    screen._on_post_all()

    assert service.posted == []
