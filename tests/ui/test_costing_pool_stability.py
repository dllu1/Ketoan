"""Ba ô pool của Bảng tính giá thành phải đứng yên giữa các lần mở tab.

Triệu chứng người dùng báo: "ô sản xuất chung thay đổi liên tục và không cố
định — đúng ra nó phải luôn là một con số cụ thể trừ khi người dùng sửa nó".

Hai nguyên nhân được chốt lại ở đây:

* nút Lưu ghi bút toán kết chuyển ``GT-155/<kỳ>`` có vế **Có 154032**, mà pool
  lại đếm số phát sinh thuần, nên pool tự trừ đúng bằng số vừa phân bổ;
* số gõ tay bị sổ cái ghi đè mỗi lần ``reload()``.

Các test phải có ít nhất một sản phẩm với NVL > 0: Σ NVL = 0 thì không phân bổ
được đồng nào, bút toán kết chuyển không phát sinh và bug không tái hiện.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.period import Period, set_active_period  # noqa: E402


class _SilentBox:
    """Thay QMessageBox trong màn giá thành: hộp thoại modal làm test treo."""

    Yes = QMessageBox.Yes
    No = QMessageBox.No

    @staticmethod
    def information(*_args, **_kwargs):
        return QMessageBox.Ok

    @staticmethod
    def question(*_args, **_kwargs):
        return QMessageBox.Yes


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("data.database.DB_PATH", db_file)

    import data.database as db_mod
    db_mod._conn = None
    db_mod.init_database()
    yield db_mod.get_connection()
    db_mod.close_connection()


@pytest.fixture
def june(temp_db, monkeypatch):
    set_active_period(Period(year=2026, month=6))
    monkeypatch.setattr("ui.screens.costing_view.QMessageBox", _SilentBox)
    return temp_db


def _view(with_product=True):
    """Màn giá thành với sẵn một sản phẩm có NVL, để pool có chỗ phân bổ."""
    from ui.screens import costing_view as cv

    view = cv.CostingView()
    if with_product and view._table.item(0, cv._NVL).text() == "":
        view._table.item(0, cv._CODE).setText("TP01")
        view._table.item(0, cv._NAME).setText("Thành phẩm 1")
        view._table.item(0, cv._QTY).setText("10")
        view._table.item(0, cv._NVL).setText("20.000.000")
    return view


def _post_overhead(conn, ref, amount, account="154032"):
    """Chi phí SX chung có thật: Nợ 154032 (hoặc 154033) / Có 331."""
    from data.repositories.journal_repo import JournalRepository
    from domain.models.journal import EntryStatus, JournalEntry, JournalLine
    from domain.services.journal_service import JournalService

    zero = Decimal("0")
    JournalService(JournalRepository(conn)).create(JournalEntry(
        ref=ref,
        entry_date=date(2026, 6, 30),
        description="Chi phí sản xuất chung",
        status=EntryStatus.POSTED,
        lines=[
            JournalLine(account_code=account, debit=amount, credit=zero),
            JournalLine(account_code="331", debit=zero, credit=amount),
        ],
    ))


def _credits_of(conn, ref_prefix="GT-155/"):
    """{TK: số ghi Có} của bút toán kết chuyển giá thành."""
    from data.repositories.journal_repo import JournalRepository
    from domain.services.journal_service import JournalService

    credits: dict[str, Decimal] = {}
    for entry in JournalService(JournalRepository(conn)).list_all():
        if not entry.ref.startswith(ref_prefix):
            continue
        for line in entry.lines:
            if line.credit:
                credits[line.account_code] = (
                    credits.get(line.account_code, Decimal("0")) + line.credit
                )
    return credits


def test_typed_overhead_survives_reload(app, june):
    """Gõ tay → Lưu → mở lại tab: vẫn đúng con số đó."""
    view = _view()
    view._overhead.setText("10.000.000")
    view._on_save()

    reopened = _view()
    assert reopened._pool_amount(reopened._overhead) == Decimal("10000000")


def test_typed_overhead_survives_repeated_saves(app, june):
    """Lưu nhiều lần liên tiếp không được làm con số trôi đi."""
    view = _view()
    view._overhead.setText("10.000.000")

    for _ in range(3):
        view._on_save()
        view.reload()
        assert view._pool_amount(view._overhead) == Decimal("10000000")


def test_ledger_overhead_survives_save(app, june):
    """Chi phí ghi sổ thật (Nợ 154032) không bị bút toán kết chuyển trừ mất."""
    _post_overhead(june, "PC01", Decimal("8000000"))

    view = _view()
    assert view._pool_amount(view._overhead) == Decimal("8000000")

    view._on_save()
    view.reload()
    assert view._pool_amount(view._overhead) == Decimal("8000000")


def test_ledger_still_fills_untouched_pool(app, june):
    """Ô chưa ai đụng vào vẫn tự lấy từ sổ cái — không mất tính năng cũ."""
    _post_overhead(june, "PC01", Decimal("8000000"))

    view = _view()
    assert view._pool_amount(view._overhead) == Decimal("8000000")
    assert view._manual["overhead"] is False


def test_typed_value_beats_the_ledger(app, june):
    """Người dùng sửa đè lên số sổ cái thì lần sau vẫn là số của người dùng."""
    _post_overhead(june, "PC01", Decimal("8000000"))

    view = _view()
    view._overhead.setText("9.500.000")
    assert view._manual["overhead"] is True
    view._on_save()

    reopened = _view()
    assert reopened._pool_amount(reopened._overhead) == Decimal("9500000")
    assert reopened._manual["overhead"] is True


def test_overhead_box_shows_both_accounts_summed(app, june):
    """Ô "15403" là tổng 154032 + 154033 — bảng chỉ còn một cấp."""
    _post_overhead(june, "PC01", Decimal("8000000"), account="154032")
    _post_overhead(june, "PC02", Decimal("2000000"), account="154033")

    view = _view()
    assert view._pool_amount(view._overhead) == Decimal("10000000")
    assert not hasattr(view, "_other")   # ô "Chi phí khác" đã bỏ


def test_carryover_entry_still_credits_both_accounts(app, june):
    """Hiển thị gộp, nhưng kết chuyển vẫn tách để 154032/154033 tất toán về 0."""
    _post_overhead(june, "PC01", Decimal("8000000"), account="154032")
    _post_overhead(june, "PC02", Decimal("2000000"), account="154033")

    view = _view()
    view._on_save()

    credits = _credits_of(june)
    assert credits["154032"] == Decimal("8000000")
    assert credits["154033"] == Decimal("2000000")


def test_typed_total_goes_to_the_main_overhead_account(app, june):
    """Gõ đè lên ô gộp: 154033 giữ theo sổ, phần chênh dồn vào 154032."""
    _post_overhead(june, "PC02", Decimal("2000000"), account="154033")

    view = _view()
    view._overhead.setText("10.000.000")
    view._on_save()

    credits = _credits_of(june)
    assert credits["154033"] == Decimal("2000000")
    assert credits["154032"] == Decimal("8000000")


def test_merged_column_sums_overhead_and_other(app, june):
    """Cột 15403 trong bảng cũng gộp, khớp với cột đơn giá 15403/sp."""
    from ui.screens import costing_view as cv

    _post_overhead(june, "PC01", Decimal("8000000"), account="154032")
    _post_overhead(june, "PC02", Decimal("2000000"), account="154033")

    view = _view()
    assert view._table.columnCount() == len(cv._HEADERS) == 13
    assert cv._HEADERS[cv._OH] == "15403"
    # Một sản phẩm duy nhất → nhận trọn cả pool.
    assert view._num(0, cv._OH) == Decimal("10000000")


def test_save_does_not_touch_a_missing_signal(app, june):
    """``CostingView`` không khai báo signal ``saved`` — không được gọi nó."""
    view = _view()
    assert not hasattr(view, "saved")
    view._overhead.setText("1.000.000")
    view._on_save()          # trước đây ném AttributeError sau khi đã ghi DB
