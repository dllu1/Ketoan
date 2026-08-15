"""AssetModal: create / edit a fixed asset (tài sản cố định)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from data.repositories.account_repo import AccountRepository
from domain.models.fixed_asset import FixedAsset
from ui.primitives.date_edit import DateEdit
from ui.primitives.enter_nav import install_form_enter_nav

_ASSET_ACCOUNTS = [("211", "211 — TSCĐ hữu hình"), ("213", "213 — TSCĐ vô hình")]
# Gợi ý nhanh, xếp trên cùng; phía dưới là TOÀN BỘ hệ thống tài khoản nên kế toán
# chọn được TK chi phí bất kỳ (kể cả TK con tự khai) và khấu hao vào đúng TK đó.
# 15403 = CP sản xuất chung đi thẳng vào giá thành — dùng cho máy móc sản xuất.
_EXPENSE_PRESETS = [
    ("642", "642 — CP quản lý DN"),
    ("641", "641 — CP bán hàng"),
    ("15403", "15403 — CP sản xuất chung (máy SX · vào giá thành)"),
    ("627", "627 — CP sản xuất chung (TT200)"),
]


class AssetModal(QDialog):
    def __init__(self, parent: QWidget | None = None, *, asset: FixedAsset | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AssetModal")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setWindowTitle("Tài sản mới" if asset is None else f"Sửa: {asset.name}")

        self._original = asset

        self._code = QLineEdit()
        self._name = QLineEdit()

        self._asset_account = QComboBox()
        for code, label in _ASSET_ACCOUNTS:
            self._asset_account.addItem(label, code)

        self._expense_account = self._build_expense_combo()

        self._cost = self._money_spin()
        self._salvage = self._money_spin()

        self._life = QSpinBox()
        self._life.setRange(1, 1200)
        self._life.setValue(12)
        self._life.setSuffix(" tháng")

        # DateEdit: bôi đen + Delete để xóa trắng rồi gõ tay cả ngày/tháng/năm.
        self._start = DateEdit()

        self._notes = QTextEdit()
        self._notes.setFixedHeight(60)

        form = QFormLayout()
        form.addRow("Mã *", self._code)
        form.addRow("Tên *", self._name)
        form.addRow("TK tài sản", self._asset_account)
        form.addRow("TK chi phí KH", self._expense_account)
        expense_hint = QLabel(
            "Gõ mã hoặc tên để tìm — khấu hao hằng tháng sẽ ghi Nợ đúng tài khoản "
            "này / Có 214. Đổi tài khoản xong, các tháng đã ghi khấu hao được ghi "
            "lại theo tài khoản mới."
        )
        expense_hint.setObjectName("SettingsNote")
        expense_hint.setWordWrap(True)
        form.addRow("", expense_hint)
        form.addRow("Nguyên giá *", self._cost)
        form.addRow("Giá trị thu hồi", self._salvage)
        form.addRow("Thời gian KH", self._life)
        form.addRow("Ngày bắt đầu", self._start)
        form.addRow("Ghi chú", self._notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        # Enter ở ô nhập = sang ô sau (không bấm "Save" nhầm).
        install_form_enter_nav(self)

        if asset is not None:
            self._populate(asset)
            self._code.setReadOnly(True)

    @staticmethod
    def _build_expense_combo() -> QComboBox:
        """Ô chọn TK chi phí khấu hao: gợi ý nhanh + toàn bộ hệ thống tài khoản.

        Để editable + completer nên kế toán gõ thẳng mã TK con của mình (vd
        6422, 154031) thay vì bị bó trong bốn lựa chọn cứng như trước.
        """
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        seen: set[str] = set()
        for code, label in _EXPENSE_PRESETS:
            combo.addItem(label, code)
            seen.add(code)
        try:
            accounts = AccountRepository().list_all()
        except Exception:  # noqa: BLE001 — chưa có DB (test dựng modal trần)
            accounts = []
        for account in accounts:
            if account.code in seen:
                continue
            combo.addItem(f"{account.code} — {account.name}", account.code)
            seen.add(account.code)
        completer = combo.completer()
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        return combo

    def _expense_code(self) -> str:
        """Mã TK đang chọn — kể cả khi người dùng tự gõ chuỗi không có trong list."""
        typed = self._expense_account.currentText().strip()
        index = self._expense_account.findText(typed)
        if index >= 0:
            return self._expense_account.itemData(index) or ""
        # Người dùng gõ tay: lấy phần mã ở đầu ("6422 — …" hoặc chỉ "6422").
        return typed.split("—")[0].split(" ")[0].strip()

    @staticmethod
    def _money_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setMaximum(1e15)
        spin.setDecimals(0)
        spin.setGroupSeparatorShown(True)
        return spin

    def _populate(self, asset: FixedAsset) -> None:
        self._code.setText(asset.code)
        self._name.setText(asset.name)
        ai = self._asset_account.findData(asset.asset_account)
        if ai >= 0:
            self._asset_account.setCurrentIndex(ai)
        ei = self._expense_account.findData(asset.expense_account)
        if ei >= 0:
            self._expense_account.setCurrentIndex(ei)
        else:
            # TK đã khai nhưng không còn trong danh mục — vẫn hiện đúng mã cũ.
            self._expense_account.setEditText(asset.expense_account)
        self._cost.setValue(float(asset.cost))
        self._salvage.setValue(float(asset.salvage_value))
        self._life.setValue(asset.useful_life_months)
        self._start.setDate(QDate(asset.start_date.year, asset.start_date.month, asset.start_date.day))
        self._notes.setPlainText(asset.notes)

    def asset(self) -> FixedAsset:
        asset = self._original or FixedAsset(code="", name="")
        asset.code = self._code.text().strip()
        asset.name = self._name.text().strip()
        asset.asset_account = self._asset_account.currentData()
        asset.expense_account = self._expense_code()
        asset.cost = Decimal(str(self._cost.value()))
        asset.salvage_value = Decimal(str(self._salvage.value()))
        asset.useful_life_months = self._life.value()
        # DateEdit tự diễn giải chuỗi nếu người dùng đang gõ tay dở.
        asset.start_date = self._start.date_value()
        asset.notes = self._notes.toPlainText().strip()
        return asset
