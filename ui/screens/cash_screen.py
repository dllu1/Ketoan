"""CashScreen: Quỹ & Ngân hàng — phiếu thu/chi + sổ quỹ với số dư lũy kế."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data.repositories.account_repo import AccountRepository
from data.repositories.journal_repo import JournalRepository
from domain.models.cash import CASH_ACCOUNTS, CashKind
from domain.money import format_money
from domain.services.cash_service import CashService, CashValidationError
from domain.services.journal_service import JournalService
from ui.modals.cash_modal import CashVoucherModal
from ui.primitives.button import Button, ButtonVariant


class CashScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("CashScreen")

        self._service = CashService(JournalService(JournalRepository()), AccountRepository())

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Quỹ & Ngân hàng")
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        toolbar = QHBoxLayout()
        self._account = QComboBox()
        self._account.addItem("Tất cả", None)
        for code, name in CASH_ACCOUNTS.items():
            self._account.addItem(f"{code} — {name}", code)
        self._account.currentIndexChanged.connect(lambda _: self._reload())

        btn_receipt = Button("Phiếu thu", variant=ButtonVariant.PRIMARY, icon_name="arrow-down")
        btn_receipt.clicked.connect(lambda: self._new_voucher(CashKind.RECEIPT))
        btn_payment = Button("Phiếu chi", icon_name="arrow-up")
        btn_payment.clicked.connect(lambda: self._new_voucher(CashKind.PAYMENT))
        btn_delete = Button("Xóa", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_delete.clicked.connect(self._on_delete)

        toolbar.addWidget(QLabel("Tài khoản"))
        toolbar.addWidget(self._account)
        toolbar.addStretch(1)
        toolbar.addWidget(btn_delete)
        toolbar.addWidget(btn_payment)
        toolbar.addWidget(btn_receipt)
        root.addLayout(toolbar)

        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            ["Ngày", "Số CT", "Diễn giải", "TK quỹ", "TK đối ứng", "Thu", "Chi", "Tồn"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setStretchLastSection(False)
        root.addWidget(self._table, 1)

        self._summary = QLabel()
        self._summary.setObjectName("BalanceBar")
        self._summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self._summary)

        self._reload()

    # ----- data ---------------------------------------------------------

    def _reload(self) -> None:
        account_filter = self._account.currentData()
        movements = self._service.list_movements(account_filter)
        self._table.setRowCount(0)
        for mv in movements:
            row = self._table.rowCount()
            self._table.insertRow(row)
            cells = [
                mv.entry_date.strftime("%d/%m/%Y"),
                mv.ref,
                mv.description,
                mv.cash_account,
                mv.counter_account,
                format_money(mv.inflow) if mv.inflow else "",
                format_money(mv.outflow) if mv.outflow else "",
                format_money(mv.balance),
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col == 1:
                    item.setData(Qt.UserRole, mv.ref)
                if col >= 5:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._table.setItem(row, col, item)

        parts = [
            f"{code}: {format_money(self._service.balance(code))}"
            for code in CASH_ACCOUNTS
        ]
        self._summary.setText("Số dư   " + "      ".join(parts))

    # ----- actions ------------------------------------------------------

    def _new_voucher(self, kind: CashKind) -> None:
        dialog = CashVoucherModal(self, kind=kind)
        if not dialog.exec():
            return
        try:
            self._service.create_voucher(
                kind=dialog.kind(), ref=dialog.ref(),
                cash_account=dialog.cash_account(),
                counter_account=dialog.counter_account(),
                amount=dialog.amount(), entry_date=dialog.entry_date(),
                description=dialog.description(),
                partner_code=dialog.partner_code(),
            )
        except CashValidationError as exc:
            QMessageBox.warning(self, "Không thể lưu", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — vd: trùng số phiếu
            QMessageBox.warning(self, "Không thể lưu", str(exc))
            return
        self._reload()

    def _on_delete(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 1)
        if item is None:
            return
        ref = item.data(Qt.UserRole)
        if QMessageBox.question(self, "Xóa phiếu", f"Xóa phiếu '{ref}'?") != QMessageBox.Yes:
            return
        self._service.delete_voucher(ref)
        self._reload()
