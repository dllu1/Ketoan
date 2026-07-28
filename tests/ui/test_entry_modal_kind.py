"""EntryModal — ba loại chứng từ kèm theo (mua hàng / bán hàng / kết chuyển).

Quy tắc: mua & bán hàng BẮT BUỘC có số hóa đơn mới ghi sổ được; kết chuyển thì
số hóa đơn là tùy chọn. Nếu chọn kết chuyển mà vẫn gõ số hóa đơn thì số đó được
ghi kèm vào diễn giải (không tạo chứng từ mua/bán).

Chạy headless (QT_QPA_PLATFORM=offscreen).
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from domain.models.invoice import InvoiceKind  # noqa: E402
from domain.models.journal import EntryStatus  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def in_memory_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("data.database.DB_PATH", db_file)

    import data.database as db_mod
    db_mod._conn = None
    db_mod.init_database()
    yield db_mod.get_connection()
    db_mod.close_connection()


@pytest.fixture
def modal(app, in_memory_db):
    from ui.modals.entry_modal import EntryModal

    dialog = EntryModal()
    yield dialog
    dialog.deleteLater()


def _select(dialog, label_fragment):
    """Chọn mục trong combo Loại theo một phần nhãn (vd 'Mua hàng')."""
    combo = dialog._invoice_kind
    for i in range(combo.count()):
        if label_fragment.lower() in combo.itemText(i).lower():
            combo.setCurrentIndex(i)
            return
    raise AssertionError(f"Không thấy mục '{label_fragment}' trong combo Loại")


def _fill_balanced_lines(dialog):
    """Hai dòng cân đối để nút Ghi sổ được bật."""
    dialog._table.item(0, 0).setText("632")
    dialog._table.item(0, 2).setText("1000000")
    dialog._table.item(1, 0).setText("155")
    dialog._table.item(1, 3).setText("1000000")


# ----- combo có đủ ba mục ----------------------------------------------------


def test_kind_combo_offers_three_options(modal):
    labels = [modal._invoice_kind.itemText(i)
              for i in range(modal._invoice_kind.count())]
    assert len(labels) == 3
    assert any("Mua hàng" in t for t in labels)
    assert any("Bán hàng" in t for t in labels)
    assert any("Kết chuyển" in t for t in labels)


def test_defaults_to_transfer_so_manual_entries_still_save(modal):
    assert "Kết chuyển" in modal._invoice_kind.currentText()
    assert modal._selected_kind() is None
    # Ô số hóa đơn không bị đánh dấu bắt buộc.
    assert "*" not in modal._invoice_no_label.text()


def test_kind_combo_is_always_enabled(modal):
    """Trước đây combo bị khóa cho tới khi gõ số hóa đơn — nay Loại là gốc."""
    assert modal._invoice_kind.isEnabled()


# ----- mua / bán: bắt buộc số hóa đơn ---------------------------------------


@pytest.mark.parametrize("kind_label", ["Mua hàng", "Bán hàng"])
def test_posting_without_invoice_no_is_blocked(modal, monkeypatch, kind_label):
    warned: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: warned.append(a[2]))

    _select(modal, kind_label)
    _fill_balanced_lines(modal)
    assert modal._invoice_no_label.text().endswith("*")

    modal._submit(EntryStatus.POSTED)

    assert warned, "phải cảnh báo khi thiếu số hóa đơn"
    assert "số hóa đơn" in warned[0].lower()
    assert modal.result() != int(QDialog.Accepted)   # hộp thoại chưa đóng


@pytest.mark.parametrize("kind_label", ["Mua hàng", "Bán hàng"])
def test_posting_with_invoice_no_goes_through(modal, monkeypatch, kind_label):
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: pytest.fail("không được cảnh báo"))

    _select(modal, kind_label)
    modal._invoice_no.setText("HD001")
    _fill_balanced_lines(modal)

    modal._submit(EntryStatus.POSTED)

    assert modal.result() == int(QDialog.Accepted)
    assert modal.entry().status is EntryStatus.POSTED


def test_draft_is_allowed_without_invoice_no(modal, monkeypatch):
    """Chỉ chặn Ghi sổ; lưu nháp vẫn cho để bổ sung số hóa đơn sau."""
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: pytest.fail("không được cảnh báo"))

    _select(modal, "Bán hàng")
    _fill_balanced_lines(modal)
    modal._submit(EntryStatus.DRAFT)

    assert modal.result() == int(QDialog.Accepted)
    assert modal.entry().status is EntryStatus.DRAFT


def test_sale_and_purchase_route_to_the_right_tab(modal):
    _select(modal, "Mua hàng")
    modal._invoice_no.setText("HD001")
    request = modal.invoice_request()
    assert request is not None and request[1] is InvoiceKind.PURCHASE

    _select(modal, "Bán hàng")
    request = modal.invoice_request()
    assert request is not None and request[1] is InvoiceKind.SALE


# ----- kết chuyển: số hóa đơn tùy chọn --------------------------------------


def test_transfer_posts_without_invoice_no(modal, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: pytest.fail("không được cảnh báo"))

    _select(modal, "Kết chuyển")
    _fill_balanced_lines(modal)
    modal._submit(EntryStatus.POSTED)

    assert modal.result() == int(QDialog.Accepted)
    assert modal.invoice_request() is None      # không tạo chứng từ mua/bán


def test_transfer_never_creates_an_invoice_even_with_a_number(modal):
    _select(modal, "Kết chuyển")
    modal._invoice_no.setText("HD001")
    assert modal.invoice_request() is None


def test_transfer_folds_invoice_no_into_description(modal):
    """Số đã gõ không bị bỏ đi — nó vào diễn giải để còn tra cứu."""
    _select(modal, "Kết chuyển")
    modal._description.setText("Kết chuyển giá vốn tháng 10")
    modal._invoice_no.setText("HD001")
    _fill_balanced_lines(modal)

    assert modal.entry().description == "Kết chuyển giá vốn tháng 10 (HĐ HD001)"


def test_transfer_uses_invoice_no_alone_when_description_empty(modal):
    _select(modal, "Kết chuyển")
    modal._invoice_no.setText("HD001")
    _fill_balanced_lines(modal)

    assert modal.entry().description == "HĐ HD001"


def test_transfer_description_is_not_appended_twice(modal):
    _select(modal, "Kết chuyển")
    modal._description.setText("Kết chuyển (HĐ HD001)")
    modal._invoice_no.setText("HD001")
    _fill_balanced_lines(modal)

    assert modal.entry().description == "Kết chuyển (HĐ HD001)"


def test_sale_description_is_left_alone(modal):
    """Mua/bán có chứng từ riêng nên không nhét số hóa đơn vào diễn giải."""
    _select(modal, "Bán hàng")
    modal._description.setText("Bán hàng tháng 10")
    modal._invoice_no.setText("HD001")
    _fill_balanced_lines(modal)

    assert modal.entry().description == "Bán hàng tháng 10"
