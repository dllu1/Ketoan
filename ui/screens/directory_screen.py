"""Directory screen: Partner + Item management (Phase 1)."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.period import active_period
from data.repositories.account_repo import AccountRepository
from data.repositories.item_repo import ItemRepository
from data.repositories.journal_repo import JournalRepository
from data.repositories.partner_repo import PartnerRepository
from domain.models.account import Account
from domain.models.bom import BomLine
from domain.models.item import Item, ItemCategory
from domain.models.opening import OpeningBalance
from domain.models.partner import Partner
from domain.money import format_money, parse_money
from domain.services.account_service import AccountService
from domain.services.bom_service import BomService
from domain.services.item_service import ItemService
from domain.services.opening_service import (
    OpeningBalanceService,
    OpeningValidationError,
)
from domain.services.partner_service import PartnerService
from domain.services.report_service import ReportService
from ui.modals.account_modal import AccountModal
from ui.modals.item_modal import ItemModal
from ui.modals.partner_modal import PartnerModal
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.enter_nav import EnterNavDelegate, install_grid_enter_nav
from ui.primitives.icon_input import IconInput
from ui.screens.material_sheet_view import _fmt_qty

_DUPLICATE = QColor("#ef4444")  # mã bị nhập trùng — không lưu được


def _parse_decimal(text: str) -> Decimal | None:
    """Đọc một số (đã nhóm nghìn) từ ô nhập; trả None nếu trống/không hợp lệ."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return parse_money(text)
    except ValueError:
        return None


def _fmt_ratio(value: Decimal) -> str:
    """Định dạng định mức suy ra (1/N) tới 4 chữ số thập phân, bỏ số 0 thừa."""
    if value == 0:
        return "0"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


class _MaterialCompleterDelegate(EnterNavDelegate):
    """Ô "Mã NVL": gợi ý ``"mã — tên"`` theo NVL (152) đã khai; ô lưu mã trần.

    Kế thừa :class:`EnterNavDelegate` để Enter vẫn nhảy sang ô kế tiếp. Danh
    sách gợi ý lấy động (``entries_fn``) nên luôn phản ánh vật tư mới thêm.
    """

    def __init__(self, entries_fn, parent=None) -> None:
        super().__init__(parent)
        self._entries_fn = entries_fn  # () -> list[tuple[mã, "mã — tên"]]
        self._code_by_label: dict[str, str] = {}

    def createEditor(self, parent, option, index):  # noqa: N802 (Qt signature)
        entries = self._entries_fn()
        self._code_by_label = {label: code for code, label in entries}
        editor = QLineEdit(parent)
        completer = QCompleter([label for _, label in entries], editor)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        editor.setCompleter(completer)
        return editor

    def setEditorData(self, editor: QLineEdit, index):  # noqa: N802
        editor.setText((index.data(Qt.EditRole) or "").strip())

    def setModelData(self, editor: QLineEdit, model, index):  # noqa: N802
        text = editor.text().strip()
        # Chọn từ popup → nhãn đầy đủ "mã — tên"; gõ tay → tách token mã đầu.
        code = self._code_by_label.get(text)
        if code is None:
            code = text.split(" — ")[0].split()[0] if text else ""
        model.setData(index, code, Qt.EditRole)


class DirectoryScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DirectoryScreen")

        self._partner_service = PartnerService(PartnerRepository())
        self._item_service = ItemService(ItemRepository())
        self._account_service = AccountService(AccountRepository())
        self._opening_service = OpeningBalanceService()
        self._bom_service = BomService()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Danh mục")
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.setObjectName("DirectoryTabs")
        tabs.addTab(self._build_partner_tab(), "Đối tác (KH/NCC)")
        tabs.addTab(self._build_item_tab(), "Vật tư / Hàng hóa")
        tabs.addTab(self._build_account_tab(), "Hệ thống tài khoản")
        tabs.addTab(self._build_opening_tab(), "Số dư đầu kỳ")
        tabs.addTab(self._build_bom_tab(), "Định mức")
        root.addWidget(tabs, 1)

        self._reload_partners()
        self._reload_items()
        self._reload_accounts()
        self._reload_opening()
        self._reload_bom_products()

    def on_activated(self) -> None:
        """Chrome gọi khi mở màn hình / đổi kỳ → nạp lại các danh mục từ DB.

        Tab "Số dư đầu kỳ" là lưới sửa tay có nút Lưu riêng nên không nạp đè:
        chỉ kéo ô năm về kỳ đang chọn, spinbox tự nạp lại khi năm thật sự đổi.
        """
        self._reload_partners()
        self._reload_items()
        self._reload_accounts()
        self._reload_bom_products()
        self._opening_year.setValue(active_period().year)

    # ----- Partners ----------------------------------------------------------

    def _build_partner_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._partner_search = IconInput(
            placeholder="Tìm theo mã / tên / MST…",
            icon_name="search",
        )
        self._partner_search.search_changed.connect(lambda _: self._reload_partners())

        btn_new = Button("Đối tác mới", variant=ButtonVariant.PRIMARY, icon_name="plus")
        btn_new.clicked.connect(self._on_partner_new)

        btn_edit = Button("Sửa", icon_name="edit")
        btn_edit.clicked.connect(self._on_partner_edit)

        toolbar.addWidget(self._partner_search, 1)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_new)
        layout.addLayout(toolbar)

        self._partner_table = QTableWidget(0, 6)
        self._partner_table.setHorizontalHeaderLabels(
            ["Mã", "Tên đối tác", "Loại", "MST", "Điện thoại", "Email"]
        )
        self._configure_table(self._partner_table)
        self._partner_table.itemDoubleClicked.connect(lambda *_: self._on_partner_edit())
        layout.addWidget(self._partner_table, 1)

        return widget

    def _reload_partners(self) -> None:
        query = self._partner_search.text() if hasattr(self, "_partner_search") else ""
        partners = self._partner_service.search(query)
        self._partner_table.setRowCount(0)
        for partner in partners:
            row = self._partner_table.rowCount()
            self._partner_table.insertRow(row)
            cells = [
                partner.code,
                partner.name,
                partner.type.value,
                partner.tax_code,
                partner.phone,
                partner.email,
            ]
            for col, value in enumerate(cells):
                table_item = QTableWidgetItem(value)
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                if col == 0:
                    table_item.setData(Qt.UserRole, partner.id)
                self._partner_table.setItem(row, col, table_item)

    def _on_partner_new(self) -> None:
        dialog = PartnerModal(self)
        if dialog.exec():
            try:
                self._partner_service.create(dialog.partner())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_partners()

    def _on_partner_edit(self) -> None:
        partner = self._selected_partner()
        if partner is None:
            return
        dialog = PartnerModal(self, partner=partner)
        if dialog.exec():
            try:
                self._partner_service.update(dialog.partner())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_partners()

    def _selected_partner(self) -> Partner | None:
        row = self._partner_table.currentRow()
        if row < 0:
            return None
        partner_id = self._partner_table.item(row, 0).data(Qt.UserRole)
        for p in self._partner_service.list_all():
            if p.id == partner_id:
                return p
        return None

    # ----- Items -------------------------------------------------------------

    def _build_item_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._item_search = IconInput(
            placeholder="Tìm theo mã / tên vật tư…",
            icon_name="search",
        )
        self._item_search.search_changed.connect(lambda _: self._reload_items())

        btn_new = Button("Vật tư mới", variant=ButtonVariant.PRIMARY, icon_name="plus")
        btn_new.clicked.connect(self._on_item_new)

        btn_edit = Button("Sửa", icon_name="edit")
        btn_edit.clicked.connect(self._on_item_edit)

        btn_delete = Button("Xóa", icon_name="trash")
        btn_delete.clicked.connect(self._on_item_delete)

        toolbar.addWidget(self._item_search, 1)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_delete)
        toolbar.addWidget(btn_new)
        layout.addLayout(toolbar)

        self._item_table = QTableWidget(0, 6)
        self._item_table.setHorizontalHeaderLabels(
            ["Mã", "Tên", "Mã kho", "ĐVT", "Đơn giá", "VAT %"]
        )
        self._configure_table(self._item_table)
        self._item_table.itemDoubleClicked.connect(lambda *_: self._on_item_edit())
        layout.addWidget(self._item_table, 1)

        return widget

    def _reload_items(self) -> None:
        query = self._item_search.text() if hasattr(self, "_item_search") else ""
        items = self._item_service.search(query)
        self._item_table.setRowCount(0)
        for item in items:
            row = self._item_table.rowCount()
            self._item_table.insertRow(row)
            cells = [
                item.code,
                item.name,
                item.category.value,
                item.unit,
                f"{item.unit_price:,.0f}",
                f"{item.vat_rate}",
            ]
            for col, value in enumerate(cells):
                table_item = QTableWidgetItem(value)
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                if col == 0:
                    table_item.setData(Qt.UserRole, item.id)
                if col in (4, 5):
                    table_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._item_table.setItem(row, col, table_item)

    def _on_item_new(self) -> None:
        dialog = ItemModal(self)
        if dialog.exec():
            try:
                self._item_service.create(dialog.item())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_items()
            self._reload_bom_products()

    def _on_item_edit(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        dialog = ItemModal(self, item=item)
        if dialog.exec():
            try:
                self._item_service.update(dialog.item())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_items()
            self._reload_bom_products()

    def _on_item_delete(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        confirm = QMessageBox.question(
            self,
            "Xóa vật tư",
            f"Xóa vật tư '{item.code} — {item.name}'?\n"
            "Các chứng từ và bút toán đã ghi sổ vẫn được giữ nguyên.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._item_service.delete(item)
        except Exception as exc:
            QMessageBox.warning(self, "Không thể xóa", str(exc))
            return
        self._reload_items()
        self._reload_bom_products()

    def _selected_item(self) -> Item | None:
        row = self._item_table.currentRow()
        if row < 0:
            return None
        item_id = self._item_table.item(row, 0).data(Qt.UserRole)
        for i in self._item_service.list_all():
            if i.id == item_id:
                return i
        return None

    # ----- Accounts ----------------------------------------------------------

    def _build_account_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._account_search = IconInput(
            placeholder="Tìm theo mã / tên tài khoản…",
            icon_name="search",
        )
        self._account_search.search_changed.connect(lambda _: self._reload_accounts())

        btn_new = Button("Tài khoản mới", variant=ButtonVariant.PRIMARY, icon_name="plus")
        btn_new.clicked.connect(self._on_account_new)

        btn_edit = Button("Sửa", icon_name="edit")
        btn_edit.clicked.connect(self._on_account_edit)

        toolbar.addWidget(self._account_search, 1)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_new)
        layout.addLayout(toolbar)

        self._account_table = QTableWidget(0, 6)
        self._account_table.setHorizontalHeaderLabels(
            ["Mã", "Tên tài khoản", "Loại", "Thuộc TK tổng hợp",
             "Số dư lũy kế", "Nguồn (TT)"]
        )
        self._configure_table(self._account_table)
        self._account_table.itemDoubleClicked.connect(lambda *_: self._on_account_edit())
        layout.addWidget(self._account_table, 1)

        return widget

    def _reload_accounts(self) -> None:
        query = self._account_search.text() if hasattr(self, "_account_search") else ""
        accounts = self._account_service.search(query)
        # Số dư lũy kế đã cộng gộp con vào cha (tài khoản tổng hợp). Dựng lại
        # ReportService mỗi lần làm mới để phản ánh bút toán mới nhất.
        try:
            balances = ReportService(JournalRepository()).aggregated_balances()
        except Exception:
            balances = {}
        names = {a.code: a.name for a in self._account_service.list_all()}
        self._account_table.setRowCount(0)
        for account in accounts:
            row = self._account_table.rowCount()
            self._account_table.insertRow(row)
            parent_label = ""
            if account.parent_code:
                parent_name = names.get(account.parent_code, "")
                parent_label = (f"{account.parent_code} — {parent_name}"
                                if parent_name else account.parent_code)
            net = balances.get(account.code)
            balance_label = format_money(net) if net else ""
            cells = [
                account.code, account.name, account.kind, parent_label,
                balance_label, account.circular,
            ]
            for col, value in enumerate(cells):
                table_item = QTableWidgetItem(value)
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                if col == 4:
                    table_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == 0:
                    table_item.setData(Qt.UserRole, account.id)
                self._account_table.setItem(row, col, table_item)

    def _on_account_new(self) -> None:
        dialog = AccountModal(self, accounts=self._account_service.list_all())
        if dialog.exec():
            try:
                self._account_service.create(dialog.account())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_accounts()

    def _on_account_edit(self) -> None:
        account = self._selected_account()
        if account is None:
            return
        dialog = AccountModal(
            self, account=account, accounts=self._account_service.list_all()
        )
        if dialog.exec():
            try:
                self._account_service.update(dialog.account())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_accounts()

    def _selected_account(self) -> Account | None:
        row = self._account_table.currentRow()
        if row < 0:
            return None
        account_id = self._account_table.item(row, 0).data(Qt.UserRole)
        for a in self._account_service.list_all():
            if a.id == account_id:
                return a
        return None

    # ----- Opening balances (Số dư đầu kỳ) -----------------------------------

    _OPENING_HEADERS = [
        "Tài khoản", "Mã hàng", "Tên hàng", "ĐVT",
        "SL đầu kỳ", "Giá trị đầu kỳ", "Nợ đầu kỳ", "Có đầu kỳ",
    ]
    _OPEN_ACCOUNT, _OPEN_ITEM, _OPEN_NAME, _OPEN_UNIT = 0, 1, 2, 3
    _OPEN_QTY, _OPEN_VALUE, _OPEN_DEBIT, _OPEN_CREDIT = 4, 5, 6, 7
    _OPEN_EDITABLE = (0, 1, 4, 5, 6, 7)

    def _build_opening_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Năm tài chính"))
        self._opening_year = QSpinBox()
        self._opening_year.setRange(2000, 2100)
        self._opening_year.setValue(active_period().year)
        self._opening_year.valueChanged.connect(lambda _: self._reload_opening())
        toolbar.addWidget(self._opening_year)
        toolbar.addStretch(1)

        btn_add = Button("Thêm dòng", icon_name="plus")
        btn_add.clicked.connect(lambda: self._add_opening_row())
        btn_del = Button("Xóa dòng", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_del.clicked.connect(self._remove_opening_row)
        btn_save = Button("Lưu", variant=ButtonVariant.PRIMARY, icon_name="check")
        btn_save.clicked.connect(lambda: self._on_opening_save())
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_del)
        toolbar.addWidget(btn_save)
        layout.addLayout(toolbar)

        hint = QLabel(
            "Nhập tồn đầu kỳ cho kho 152/155/156 chi tiết theo mã hàng (SL + giá trị); "
            "dòng không có mã hàng dùng cho số dư Nợ/Có cấp tài khoản. "
            "Số liệu chảy vào Báo cáo và Nhập–Xuất–Tồn khi kỳ trước chưa có số liệu."
        )
        hint.setObjectName("SectionLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._opening_updating = False
        self._opening_table = QTableWidget(0, len(self._OPENING_HEADERS))
        self._opening_table.setHorizontalHeaderLabels(self._OPENING_HEADERS)
        self._configure_table(self._opening_table)
        self._opening_table.horizontalHeader().setSectionResizeMode(
            self._OPEN_NAME, QHeaderView.Stretch
        )
        self._opening_table.itemChanged.connect(self._on_opening_item_changed)
        layout.addWidget(self._opening_table, 1)
        return widget

    def _item_lookup(self) -> dict[str, Item]:
        return {i.code: i for i in self._item_service.list_all()}

    def _reload_opening(self) -> None:
        self._opening_updating = True
        self._opening_table.setRowCount(0)
        rows = self._opening_service.load(self._opening_year.value())
        for ob in rows:
            self._add_opening_row(ob)
        if not rows:
            self._add_opening_row()
        self._highlight_opening_duplicates()
        self._opening_updating = False

    def _add_opening_row(self, ob: OpeningBalance | None = None) -> None:
        was = self._opening_updating
        self._opening_updating = True
        row = self._opening_table.rowCount()
        self._opening_table.insertRow(row)
        item = self._item_lookup().get(ob.item_code) if ob else None
        values = [""] * len(self._OPENING_HEADERS)
        if ob is not None:
            values[self._OPEN_ACCOUNT] = ob.account_code
            values[self._OPEN_ITEM] = ob.item_code
            values[self._OPEN_NAME] = item.name if item else ""
            values[self._OPEN_UNIT] = item.unit if item else ""
            values[self._OPEN_QTY] = _fmt_qty(ob.opening_qty) if ob.opening_qty else ""
            values[self._OPEN_VALUE] = format_money(ob.opening_value) if ob.opening_value else ""
            values[self._OPEN_DEBIT] = format_money(ob.opening_debit) if ob.opening_debit else ""
            values[self._OPEN_CREDIT] = format_money(ob.opening_credit) if ob.opening_credit else ""
        for col, value in enumerate(values):
            cell = QTableWidgetItem(value)
            if col not in (self._OPEN_ACCOUNT, self._OPEN_ITEM,
                           self._OPEN_NAME, self._OPEN_UNIT):
                cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if col not in self._OPEN_EDITABLE:
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
            self._opening_table.setItem(row, col, cell)
        self._opening_updating = was

    def _remove_opening_row(self) -> None:
        row = self._opening_table.currentRow()
        if row >= 0:
            self._opening_table.removeRow(row)
            self._highlight_opening_duplicates()

    def _on_opening_item_changed(self, cell: QTableWidgetItem) -> None:
        if self._opening_updating:
            return
        if cell.column() not in (self._OPEN_ACCOUNT, self._OPEN_ITEM):
            return
        self._opening_updating = True
        if cell.column() == self._OPEN_ITEM:
            row = cell.row()
            code = cell.text().strip()
            item = self._item_lookup().get(code)
            self._opening_table.item(row, self._OPEN_NAME).setText(item.name if item else "")
            self._opening_table.item(row, self._OPEN_UNIT).setText(item.unit if item else "")
            account_cell = self._opening_table.item(row, self._OPEN_ACCOUNT)
            if item and not account_cell.text().strip():
                account_cell.setText(item.account_code)
        self._highlight_opening_duplicates()
        self._opening_updating = False

    def _opening_cell(self, row: int, col: int) -> str:
        cell = self._opening_table.item(row, col)
        return cell.text().strip() if cell else ""

    def _opening_num(self, row: int, col: int) -> Decimal:
        try:
            return parse_money(self._opening_cell(row, col))
        except ValueError:
            return Decimal("0")

    def _opening_row_models(self) -> list[tuple[int, OpeningBalance]]:
        """Các dòng có dữ liệu trên bảng, kèm chỉ số dòng để tô màu khi lỗi."""
        models: list[tuple[int, OpeningBalance]] = []
        for r in range(self._opening_table.rowCount()):
            ob = OpeningBalance(
                fiscal_year=self._opening_year.value(),
                account_code=self._opening_cell(r, self._OPEN_ACCOUNT),
                item_code=self._opening_cell(r, self._OPEN_ITEM),
                opening_qty=self._opening_num(r, self._OPEN_QTY),
                opening_value=self._opening_num(r, self._OPEN_VALUE),
                opening_debit=self._opening_num(r, self._OPEN_DEBIT),
                opening_credit=self._opening_num(r, self._OPEN_CREDIT),
            )
            if not ob.is_empty:
                models.append((r, ob))
        return models

    def _opening_duplicate_rows(self) -> dict[tuple[str, str], list[int]]:
        """Khóa (mã TK, mã hàng) bị lặp → các dòng đang giữ khóa đó."""
        seen: dict[tuple[str, str], list[int]] = {}
        for row, ob in self._opening_row_models():
            seen.setdefault(ob.key, []).append(row)
        return {key: rows for key, rows in seen.items() if len(rows) > 1}

    def _highlight_opening_duplicates(self) -> None:
        """Tô đỏ mã TK / mã hàng của các dòng trùng khóa (mỗi năm chỉ 1 dòng)."""
        was = self._opening_updating
        self._opening_updating = True
        flagged = {r for rows in self._opening_duplicate_rows().values() for r in rows}
        for r in range(self._opening_table.rowCount()):
            duplicate = r in flagged
            for col in (self._OPEN_ACCOUNT, self._OPEN_ITEM):
                cell = self._opening_table.item(r, col)
                if cell is None:
                    continue
                cell.setForeground(_DUPLICATE if duplicate else QColor())
                cell.setToolTip(
                    "Mã này đã có ở dòng khác trong cùng năm — gộp lại hoặc đổi mã."
                    if duplicate else ""
                )
        self._opening_updating = was

    def _on_opening_save(self, merge: bool = False) -> None:
        year = self._opening_year.value()
        rows = [ob for _, ob in self._opening_row_models()]
        try:
            self._opening_service.save(year, rows, merge=merge)
        except OpeningValidationError as exc:
            self._ask_merge_opening_duplicates(exc)
            return
        except Exception as exc:  # noqa: BLE001 — surface any save failure to user
            QMessageBox.warning(self, "Không thể lưu", str(exc))
            return
        QMessageBox.information(
            self, "Đã lưu", f"Đã lưu số dư đầu kỳ năm {year}."
        )
        self._reload_opening()

    def _ask_merge_opening_duplicates(self, exc: OpeningValidationError) -> None:
        """Chỉ tới dòng trùng đầu tiên rồi hỏi có gộp các dòng trùng lại không."""
        self._highlight_opening_duplicates()
        duplicates = self._opening_duplicate_rows()
        first = min((r for rows in duplicates.values() for r in rows), default=-1)
        if first >= 0:
            self._opening_table.setCurrentCell(first, self._OPEN_ITEM)
            self._opening_table.scrollToItem(
                self._opening_table.item(first, self._OPEN_ITEM)
            )
        message = (
            f"{exc}\n\n"
            "Gộp các dòng trùng lại (cộng dồn SL, giá trị, Nợ/Có đầu kỳ) rồi lưu?"
        )
        answer = QMessageBox.question(
            self, "Mã bị nhập trùng", message,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self._on_opening_save(merge=True)

    # ----- Định mức (BOM) ----------------------------------------------------

    _BOM_HEADERS = [
        "Mã NVL (152)", "Tên", "ĐVT",
        "Số TP / 1 ĐVT NVL", "Định mức / 1 TP", "Ghi chú",
    ]
    _BOM_MATERIAL, _BOM_NAME, _BOM_UNIT, _BOM_PACK, _BOM_QTY, _BOM_NOTE = range(6)
    _BOM_EDITABLE = (0, 3, 4, 5)
    _BOM_TOOLTIPS = {
        3: "Quy cách đóng gói: 1 đơn vị NVL (vd 1 thùng carton) bao được bao "
           "nhiêu thành phẩm. Nhập cho NVL đóng gói — vd 1 thùng chứa 25 cây → "
           "gõ 25. Để trống nếu là NVL thường (nhập trực tiếp Định mức / 1 TP).",
        4: "Lượng NVL dùng cho 1 thành phẩm (vd 0,8 kg thép/1 cây). Nếu đã nhập "
           "'Số TP / 1 ĐVT NVL' thì ô này tự tính = 1 / số đó.",
    }

    def _build_bom_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Thành phẩm (155)"))
        self._bom_product = QComboBox()
        self._bom_product.setMinimumWidth(260)
        self._bom_product.currentIndexChanged.connect(lambda _: self._reload_bom_lines())
        toolbar.addWidget(self._bom_product)
        toolbar.addStretch(1)

        btn_import = Button("Lấy NVL từ kho", icon_name="download")
        btn_import.setToolTip(
            "Đưa các NVL đã khai ở Kho hàng (Nhập–Xuất–Tồn) vào Danh mục vật tư, "
            "để khỏi phải nhập tay lại. Mã đã có trong danh mục được giữ nguyên."
        )
        btn_import.clicked.connect(self._on_import_materials_from_stock)
        btn_add = Button("Thêm dòng", icon_name="plus")
        btn_add.clicked.connect(lambda: self._add_bom_row())
        btn_del = Button("Xóa dòng", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_del.clicked.connect(self._remove_bom_row)
        btn_save = Button("Lưu", variant=ButtonVariant.PRIMARY, icon_name="check")
        btn_save.clicked.connect(self._on_bom_save)
        toolbar.addWidget(btn_import)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_del)
        toolbar.addWidget(btn_save)
        layout.addLayout(toolbar)

        hint = QLabel(
            "Khai định mức NVL (kho 152) cho 1 thành phẩm — có 2 cách nhập mỗi dòng:\n"
            "•  NVL thường (thép, sơn…): nhập trực tiếp cột “Định mức / 1 TP” = "
            "lượng NVL dùng cho 1 thành phẩm (vd 0,8 kg thép / 1 cây).\n"
            "•  NVL đóng gói (thùng carton…): chỉ cần nhập cột “Số TP / 1 ĐVT NVL” = "
            "1 thùng chứa được bao nhiêu cây (vd 25) — định mức tự tính = 1/25.\n"
            "Giá thành = định mức × số lượng sản xuất × đơn giá NVL. NVL phải có "
            "trong Danh mục — dùng “Lấy NVL từ kho” nếu đã khai ở Kho hàng."
        )
        hint.setObjectName("SectionLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._bom_updating = False
        self._bom_table = QTableWidget(0, len(self._BOM_HEADERS))
        self._bom_table.setHorizontalHeaderLabels(self._BOM_HEADERS)
        for col, tip in self._BOM_TOOLTIPS.items():
            header_item = self._bom_table.horizontalHeaderItem(col)
            if header_item is not None:
                header_item.setToolTip(tip)
        self._configure_table(self._bom_table)
        self._bom_table.horizontalHeader().setSectionResizeMode(
            self._BOM_NAME, QHeaderView.Stretch
        )
        self._bom_table.itemChanged.connect(self._on_bom_item_changed)
        # Ô "Mã NVL" gợi ý theo NVL (152) đã khai để mã luôn khớp danh mục →
        # tên/ĐVT tự điền được. Enter nhảy Mã NVL → Định mức → Ghi chú → dòng mới,
        # bỏ qua cột chỉ đọc (Tên, ĐVT) đúng như các bảng nhập khác trong app.
        self._bom_table.setItemDelegateForColumn(
            self._BOM_MATERIAL,
            _MaterialCompleterDelegate(self._material_entries, self._bom_table),
        )
        install_grid_enter_nav(self._bom_table, add_row=self._add_bom_row)
        layout.addWidget(self._bom_table, 1)
        return widget

    def _material_entries(self) -> list[tuple[str, str]]:
        """(mã, "mã — tên") của NVL (152) cho gợi ý ô Mã NVL của định mức."""
        return [
            (i.code, f"{i.code} — {i.name}")
            for i in self._item_service.list_all(ItemCategory.MATERIAL)
        ]

    def _reload_bom_products(self) -> None:
        # Remember the current selection so adding/editing another item doesn't
        # bounce the dropdown back to the first product.
        previous = self._current_product_code()
        self._bom_product.blockSignals(True)
        self._bom_product.clear()
        products = [
            i for i in self._item_service.list_all()
            if i.category is ItemCategory.PRODUCT
        ]
        for it in products:
            self._bom_product.addItem(f"{it.code} — {it.name}", it.code)
        restored = self._bom_product.findData(previous) if previous else -1
        if restored >= 0:
            self._bom_product.setCurrentIndex(restored)
        self._bom_product.blockSignals(False)
        self._reload_bom_lines()

    def _current_product_code(self) -> str:
        return self._bom_product.currentData() or ""

    def _on_import_materials_from_stock(self) -> None:
        """Đồng bộ NVL từ Kho hàng vào Danh mục vật tư (152).

        Gộp hai nguồn kho: sổ NXT sinh từ chứng từ (tab Nhập–Xuất–Tồn) là chính,
        rồi bổ sung mã chỉ có ở Bảng kê NVL chính (nhập tay). Nhờ vậy mọi NVL đang
        thấy ở Kho hàng đều lấy được, không phải nhập tay lại.
        """
        from data.repositories.inventory_repo import InventoryRepository
        from data.repositories.material_sheet_repo import MaterialSheetRepository
        from domain.services.inventory_service import InventoryService

        merged: dict[str, tuple[str, str]] = {}
        inventory = InventoryService(InventoryRepository(), ItemRepository())
        for code, name, unit in inventory.list_stock_materials("152"):
            merged[code] = (name, unit)
        for code, name, unit in MaterialSheetRepository().list_distinct_materials():
            merged.setdefault(code, (name, unit))
        materials = [(code, name, unit) for code, (name, unit) in sorted(merged.items())]
        if not materials:
            QMessageBox.information(
                self, "Chưa có NVL trong kho",
                "Sổ kho (Kho hàng → Nhập–Xuất–Tồn) chưa có nguyên vật liệu nào "
                "để lấy sang danh mục.",
            )
            return
        created = self._item_service.import_materials(materials)
        # Danh mục vừa đổi → làm mới bảng vật tư và gợi ý ô Mã NVL của định mức.
        self._reload_items()
        self._reload_bom_products()
        if created:
            QMessageBox.information(
                self, "Đã lấy NVL từ kho",
                f"Đã thêm {created} nguyên vật liệu mới vào danh mục. "
                "Giờ có thể chọn chúng khi khai định mức.",
            )
        else:
            QMessageBox.information(
                self, "Không có NVL mới",
                "Mọi nguyên vật liệu trong kho đều đã có trong danh mục.",
            )

    def _reload_bom_lines(self) -> None:
        self._bom_updating = True
        self._bom_table.setRowCount(0)
        code = self._current_product_code()
        lines = self._bom_service.load(code).lines if code else []
        for ln in lines:
            self._add_bom_row(ln)
        if not lines:
            self._add_bom_row()
        self._bom_updating = False

    def _add_bom_row(self, line: BomLine | None = None) -> None:
        was = self._bom_updating
        self._bom_updating = True
        row = self._bom_table.rowCount()
        self._bom_table.insertRow(row)
        values = [""] * len(self._BOM_HEADERS)
        if line is not None:
            values[self._BOM_MATERIAL] = line.material_code
            values[self._BOM_NAME] = line.material_name
            values[self._BOM_UNIT] = line.unit
            values[self._BOM_PACK] = (
                _fmt_qty(line.pieces_per_pack) if line.pieces_per_pack else ""
            )
            values[self._BOM_QTY] = _fmt_qty(line.quantity_per) if line.quantity_per else ""
            values[self._BOM_NOTE] = line.note
        for col, value in enumerate(values):
            cell = QTableWidgetItem(value)
            if col in (self._BOM_PACK, self._BOM_QTY):
                cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if col not in self._BOM_EDITABLE:
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
            self._bom_table.setItem(row, col, cell)
        # NVL đóng gói: khoá ô định mức và để nó tự tính từ số TP / thùng.
        self._sync_bom_packaging(row)
        self._bom_updating = was

    def _remove_bom_row(self) -> None:
        row = self._bom_table.currentRow()
        if row >= 0:
            self._bom_table.removeRow(row)

    def _on_bom_item_changed(self, cell: QTableWidgetItem) -> None:
        if self._bom_updating:
            return
        col = cell.column()
        if col == self._BOM_MATERIAL:
            self._bom_updating = True
            row = cell.row()
            item = self._item_lookup().get(cell.text().strip())
            self._bom_table.item(row, self._BOM_NAME).setText(item.name if item else "")
            self._bom_table.item(row, self._BOM_UNIT).setText(item.unit if item else "")
            self._bom_updating = False
        elif col == self._BOM_PACK:
            self._bom_updating = True
            self._sync_bom_packaging(cell.row())
            self._bom_updating = False

    def _sync_bom_packaging(self, row: int) -> None:
        """Khi khai 'Số TP / 1 ĐVT NVL', tự tính định mức = 1/N và khoá ô đó.

        Bỏ trống ô đóng gói thì trả ô 'Định mức / 1 TP' về nhập tay được.
        """
        pack_cell = self._bom_table.item(row, self._BOM_PACK)
        qty_cell = self._bom_table.item(row, self._BOM_QTY)
        if pack_cell is None or qty_cell is None:
            return
        pieces = _parse_decimal(pack_cell.text())
        if pieces and pieces > 0:
            derived = Decimal(1) / pieces
            qty_cell.setText(_fmt_ratio(derived))
            qty_cell.setFlags(qty_cell.flags() & ~Qt.ItemIsEditable)
            qty_cell.setToolTip(f"Tự tính = 1 / {pack_cell.text().strip()} (đóng gói)")
        else:
            qty_cell.setFlags(qty_cell.flags() | Qt.ItemIsEditable)
            qty_cell.setToolTip("")

    def _on_bom_save(self) -> None:
        code = self._current_product_code()
        if not code:
            QMessageBox.warning(self, "Chưa chọn thành phẩm",
                                "Tạo thành phẩm (nhóm 155) trong tab Vật tư / Hàng hóa trước.")
            return
        lines: list[BomLine] = []
        for r in range(self._bom_table.rowCount()):
            material = self._bom_table.item(r, self._BOM_MATERIAL)
            pack_cell = self._bom_table.item(r, self._BOM_PACK)
            qty_cell = self._bom_table.item(r, self._BOM_QTY)
            note_cell = self._bom_table.item(r, self._BOM_NOTE)
            material_code = material.text().strip() if material else ""
            try:
                qty = parse_money(qty_cell.text()) if qty_cell else Decimal("0")
            except ValueError:
                qty = Decimal("0")
            pieces = _parse_decimal(pack_cell.text()) if pack_cell else None
            line = BomLine(
                product_code=code, material_code=material_code,
                quantity_per=qty, note=note_cell.text().strip() if note_cell else "",
                pieces_per_pack=pieces or Decimal("0"),
            )
            # apply_packaging (trong BomService.save) sẽ suy ra quantity_per=1/N
            # cho dòng đóng gói; ở đây chỉ cần không loại nhầm dòng đó là rỗng.
            if not line.is_empty or (material_code and pieces):
                lines.append(line)
        self._bom_service.save(code, lines)
        QMessageBox.information(self, "Đã lưu", f"Đã lưu định mức cho {code}.")
        self._reload_bom_lines()

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
