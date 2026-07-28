"""ItemImportModal: chọn mặt hàng trong kho để đưa vào Danh mục vật tư.

Mở từ nút "Nhập vào danh mục" ở tab Nhập–Xuất–Tồn. Người dùng **chủ động tích
chọn** từng mã (hoặc lọc theo mã kho rồi "Chọn tất cả") — mặc định không tích gì
để tránh đưa cả kho vào danh mục một cách vô tội vạ. Mặt hàng đã có trong danh
mục hiển thị trạng thái "Đã có" và không cho tích lại.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.primitives.button import Button, ButtonVariant

# Candidate = (mã, tên, ĐVT, TK kho, đã có trong danh mục?)
Candidate = tuple[str, str, str, str, bool]

_HEADERS = ["", "Mã hàng", "Tên hàng", "ĐVT", "Nhóm TK", "Trạng thái"]
(_C_CHECK, _C_CODE, _C_NAME, _C_UNIT, _C_ACCOUNT, _C_STATUS) = range(6)

_ACCOUNT_LABELS = {
    "152": "152 — Nguyên vật liệu",
    "153": "153 — Công cụ, dụng cụ",
    "155": "155 — Thành phẩm",
    "156": "156 — Hàng hóa",
}


def _account_label(account: str) -> str:
    return _ACCOUNT_LABELS.get((account or "")[:3], account or "Chưa phân nhóm")


class ItemImportModal(QDialog):
    def __init__(
        self, parent: QWidget | None = None, *, candidates: list[Candidate]
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ItemImportModal")
        self.setModal(True)
        self.setMinimumSize(720, 520)
        self.setWindowTitle("Nhập hàng hóa vào danh mục")
        self._candidates = candidates

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title = QLabel("Chọn mặt hàng trong kho để đưa vào Danh mục")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)
        hint = QLabel(
            "Tích chọn từng mã, hoặc lọc theo nhóm TK kho rồi bấm “Chọn tất cả”. "
            "Mặt hàng đã có trong danh mục được bỏ qua."
        )
        hint.setObjectName("DialogSubtitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ----- thanh lọc + chọn nhanh ---------------------------------------
        tools = QHBoxLayout()
        tools.addWidget(QLabel("Nhóm TK"))
        self._account = QComboBox()
        self._account.addItem("Tất cả nhóm", "")
        for account in sorted({c[3][:3] for c in candidates if c[3]}):
            self._account.addItem(_account_label(account), account)
        self._account.currentIndexChanged.connect(lambda _: self._apply_filter())
        tools.addWidget(self._account)
        tools.addStretch(1)
        btn_all = Button("Chọn tất cả", variant=ButtonVariant.GHOST)
        btn_all.clicked.connect(lambda: self._set_visible_checked(True))
        btn_none = Button("Bỏ chọn", variant=ButtonVariant.GHOST)
        btn_none.clicked.connect(lambda: self._set_visible_checked(False))
        tools.addWidget(btn_all)
        tools.addWidget(btn_none)
        layout.addLayout(tools)

        # ----- bảng ---------------------------------------------------------
        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        head = self._table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setSectionResizeMode(_C_NAME, QHeaderView.Stretch)
        layout.addWidget(self._table, 1)
        self._fill_rows()

        # ----- chân: đếm + nút ----------------------------------------------
        footer = QHBoxLayout()
        self._count = QLabel()
        self._count.setObjectName("BalanceBar")
        footer.addWidget(self._count, 1)
        btn_cancel = Button("Hủy", variant=ButtonVariant.GHOST)
        btn_cancel.clicked.connect(self.reject)
        self._btn_ok = Button("Nhập vào danh mục", variant=ButtonVariant.PRIMARY,
                              icon_name="check")
        self._btn_ok.clicked.connect(self._on_accept)
        footer.addWidget(btn_cancel)
        footer.addWidget(self._btn_ok)
        layout.addLayout(footer)

        # Nối sau khi mọi widget đã dựng: tránh itemChanged bắn lúc đổ dòng.
        self._table.itemChanged.connect(lambda _: self._refresh_count())
        self._refresh_count()

    # ----- build -----------------------------------------------------------

    def _fill_rows(self) -> None:
        for code, name, unit, account, exists in self._candidates:
            row = self._table.rowCount()
            self._table.insertRow(row)
            check = QTableWidgetItem()
            if exists:
                # Đã có trong danh mục → không cho tích lại.
                check.setFlags(Qt.ItemIsSelectable)
            else:
                check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                               | Qt.ItemIsSelectable)
            check.setCheckState(Qt.Unchecked)
            self._table.setItem(row, _C_CHECK, check)
            cells = [
                code, name, unit, _account_label(account),
                "Đã có trong danh mục" if exists else "Chưa có — sẽ thêm",
            ]
            for offset, value in enumerate(cells, start=1):
                cell = QTableWidgetItem(value)
                cell.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._table.setItem(row, offset, cell)

    # ----- helpers ---------------------------------------------------------

    def _apply_filter(self) -> None:
        wanted = self._account.currentData() or ""
        for row in range(self._table.rowCount()):
            account = self._candidates[row][3][:3]
            self._table.setRowHidden(row, bool(wanted) and account != wanted)
        self._refresh_count()

    def _set_visible_checked(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        for row in range(self._table.rowCount()):
            if self._table.isRowHidden(row):
                continue
            check = self._table.item(row, _C_CHECK)
            if check.flags() & Qt.ItemIsUserCheckable:
                check.setCheckState(state)

    def _refresh_count(self) -> None:
        n = len(self.selected())
        self._count.setText(f"Đã chọn {n} mặt hàng để thêm vào danh mục")
        self._btn_ok.setEnabled(n > 0)

    def selected(self) -> list[tuple[str, str, str, str]]:
        """(mã, tên, ĐVT, TK kho) của các dòng được tích."""
        out: list[tuple[str, str, str, str]] = []
        for row in range(self._table.rowCount()):
            check = self._table.item(row, _C_CHECK)
            if check is not None and check.checkState() == Qt.Checked:
                code, name, unit, account, _exists = self._candidates[row]
                out.append((code, name, unit, account))
        return out

    def _on_accept(self) -> None:
        if self.selected():
            self.accept()
