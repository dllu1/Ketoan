"""AssetsScreen: Tài sản cố định — danh mục TSCĐ + lưới khấu hao 12 tháng."""
from __future__ import annotations

from datetime import date

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

from app.period import active_period
from data.repositories.account_repo import AccountRepository
from data.repositories.fixed_asset_repo import FixedAssetRepository
from data.repositories.journal_repo import JournalRepository
from domain.models.fixed_asset import FixedAsset
from domain.money import format_money
from domain.services.fixed_asset_service import (
    FixedAssetService,
    FixedAssetValidationError,
)
from domain.services.journal_service import JournalService
from ui.modals.asset_modal import AssetModal
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.icon_input import IconInput

_MONTHS = [f"Tháng {m:02d}" for m in range(1, 13)]


class AssetsScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("AssetsScreen")

        self._service = FixedAssetService(
            FixedAssetRepository(),
            JournalService(JournalRepository()),
            AccountRepository(),
        )
        # Cache theo id: chọn dòng / dựng lưới khấu hao không phải nạp lại toàn
        # bộ danh mục từ DB mỗi lần con trỏ đổi ô.
        self._assets: dict[int, FixedAsset] = {}
        # True trong lúc dựng lại bảng: chặn currentCellChanged dựng lại lưới 12
        # tháng nhiều lần cho mỗi lần nạp.
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Tài sản cố định")
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        toolbar = QHBoxLayout()
        self._search = IconInput(placeholder="Tìm theo mã / tên tài sản…", icon_name="search")
        self._search.search_changed.connect(lambda _: self._reload())

        today = date.today()
        self._year = QComboBox()
        for y in range(today.year - 5, today.year + 2):
            self._year.addItem(str(y), y)
        self._year.setCurrentText(str(today.year))
        self._year.currentIndexChanged.connect(lambda _: self._on_period_changed())

        self._month = QComboBox()
        for i, label in enumerate(_MONTHS, start=1):
            self._month.addItem(label, i)
        self._month.setCurrentIndex(today.month - 1)
        # Đổi tháng cũng phải nạp lại bảng: cột "Đã KH"/"Còn lại" tính đến kỳ
        # đang chọn, nếu không người dùng bấm mà bảng đứng im như bị treo.
        self._month.currentIndexChanged.connect(lambda _: self._on_period_changed())

        btn_post = Button("Ghi khấu hao kỳ", icon_name="check")
        btn_post.clicked.connect(self._on_post_depreciation)
        btn_new = Button("Tài sản mới", variant=ButtonVariant.PRIMARY, icon_name="plus")
        btn_new.clicked.connect(self._on_new)
        btn_edit = Button("Sửa", icon_name="edit")
        btn_edit.clicked.connect(self._on_edit)

        toolbar.addWidget(self._search, 1)
        toolbar.addWidget(QLabel("Năm"))
        toolbar.addWidget(self._year)
        toolbar.addWidget(self._month)
        toolbar.addWidget(btn_post)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_new)
        root.addLayout(toolbar)

        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels(
            ["Mã", "Tên tài sản", "TK", "TK chi phí", "Nguyên giá", "Số kỳ",
             "KH/tháng", "Đã KH", "Còn lại"]
        )
        self._configure_table(self._table)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.currentCellChanged.connect(lambda *_: self._show_schedule())
        self._table.itemDoubleClicked.connect(lambda *_: self._on_edit())
        root.addWidget(self._table, 3)

        schedule_label = QLabel("Lưới khấu hao 12 tháng")
        schedule_label.setObjectName("SectionLabel")
        root.addWidget(schedule_label)

        self._schedule = QTableWidget(0, 4)
        self._schedule.setHorizontalHeaderLabels(
            ["Tháng", "Khấu hao", "Lũy kế", "Giá trị còn lại"]
        )
        self._configure_table(self._schedule)
        root.addWidget(self._schedule, 2)

        self._reload()

    # ----- list/detail --------------------------------------------------

    def on_activated(self) -> None:
        """Chrome gọi mỗi lần mở màn hình hoặc đổi kỳ kế toán → nạp lại từ DB.

        Thiếu hàm này màn hình chỉ nạp một lần lúc khởi động: TSCĐ mới thêm,
        khấu hao vừa ghi hay dữ liệu vừa reset đều không hiện ra, nhìn như bị
        treo."""
        self._sync_period()
        self._reload()

    def _sync_period(self) -> None:
        """Kéo bộ chọn Năm/Tháng về kỳ kế toán đang chọn ở thanh trên."""
        period = active_period()
        self._updating = True
        index = self._year.findData(period.year)
        if index < 0:  # kỳ nằm ngoài dải năm mặc định
            self._year.addItem(str(period.year), period.year)
            index = self._year.count() - 1
        self._year.setCurrentIndex(index)
        # "Cả năm" → lấy mốc cuối năm cho cột lũy kế.
        self._month.setCurrentIndex((period.month or 12) - 1)
        self._updating = False

    def _reload(self) -> None:
        query = self._search.text() if hasattr(self, "_search") else ""
        year, month = self._year.currentData(), self._month.currentData()
        keep_id = self._selected_id()
        assets = self._service.search(query)
        self._assets = {a.id: a for a in assets if a.id is not None}
        self._updating = True
        self._table.setRowCount(0)
        self._table.setHorizontalHeaderLabels(
            ["Mã", "Tên tài sản", "TK", "TK chi phí", "Nguyên giá", "Số kỳ",
             "KH/tháng", f"Đã KH đến {month:02d}/{year}", "Còn lại"]
        )
        for asset in assets:
            row = self._table.rowCount()
            self._table.insertRow(row)
            accumulated = asset.accumulated_through(year, month)
            book_value = asset.cost - accumulated
            cells = [
                asset.code,
                asset.name,
                asset.asset_account,
                asset.expense_account,
                format_money(asset.cost),
                str(asset.useful_life_months),
                format_money(asset.monthly_depreciation),
                format_money(accumulated),
                format_money(book_value),
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.UserRole, asset.id)
                if col >= 4:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._table.setItem(row, col, item)
        self._updating = False
        self._restore_selection(keep_id)
        self._show_schedule()

    def _restore_selection(self, asset_id: int | None) -> None:
        """Giữ nguyên tài sản đang xem sau khi nạp lại; mặc định chọn dòng đầu."""
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.UserRole) == asset_id:
                self._table.setCurrentCell(row, 0)
                return
        if self._table.rowCount():
            self._table.setCurrentCell(0, 0)

    def _show_schedule(self) -> None:
        if self._updating:
            return
        asset = self._selected()
        self._schedule.setRowCount(0)
        if asset is None:
            return
        year = self._year.currentData()
        for period in self._service.depreciation_schedule(asset, year):
            row = self._schedule.rowCount()
            self._schedule.insertRow(row)
            cells = [
                f"{period.month:02d}/{year}",
                format_money(period.depreciation) if period.depreciation else "",
                format_money(period.accumulated),
                format_money(period.book_value),
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col >= 1:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._schedule.setItem(row, col, item)

    def _on_period_changed(self) -> None:
        if self._updating:  # combo đang được đồng bộ theo kỳ, chưa phải người dùng
            return
        self._reload()

    # ----- actions ------------------------------------------------------

    def _on_new(self) -> None:
        dialog = AssetModal(self)
        if not dialog.exec():
            return
        self._save(dialog.asset(), is_update=False)

    def _on_edit(self) -> None:
        asset = self._selected()
        if asset is None:
            return
        dialog = AssetModal(self, asset=asset)
        if not dialog.exec():
            return
        self._save(dialog.asset(), is_update=True)

    def _save(self, asset: FixedAsset, *, is_update: bool) -> None:
        try:
            if is_update:
                self._service.update(asset)
            else:
                self._service.create(asset)
        except FixedAssetValidationError as exc:
            QMessageBox.warning(self, "Không thể lưu", str(exc))
            return
        self._reload()

    def _on_post_depreciation(self) -> None:
        year = self._year.currentData()
        month = self._month.currentData()
        try:
            entry = self._service.post_monthly_depreciation(year, month)
        except FixedAssetValidationError as exc:
            QMessageBox.warning(self, "Không thể ghi", str(exc))
            return
        if entry is None:
            QMessageBox.information(
                self, "Không có khấu hao",
                f"Không có tài sản nào phát sinh khấu hao trong tháng {month:02d}/{year}.",
            )
            return
        QMessageBox.information(
            self, "Đã ghi khấu hao",
            f"Đã ghi bút toán '{entry.ref}' — tổng khấu hao {format_money(entry.total_debit)}.",
        )
        self._reload()

    def _selected(self) -> FixedAsset | None:
        asset_id = self._selected_id()
        return None if asset_id is None else self._assets.get(asset_id)

    def _selected_id(self) -> int | None:
        row = self._table.currentRow()
        item = self._table.item(row, 0) if row >= 0 else None
        return None if item is None else item.data(Qt.UserRole)

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
