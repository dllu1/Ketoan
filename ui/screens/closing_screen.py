"""ClosingScreen: Kết chuyển — người dùng tự khai TK nào sang TK nào, chiều nào.

Ba phần xếp dọc:

1. **Tài khoản xác định kết quả** — TK trung gian (911) và TK nhận lãi/lỗ (4212).
2. **Quy tắc kết chuyển** — lưới sửa trực tiếp: TK nguồn → TK đích, chiều Nợ/Có,
   gom vào số chứng từ nào. Đây là phần thay cho danh sách tài khoản cứng cũ.
3. **Tài khoản không có số dư cuối kỳ** — danh sách TK phải về 0, kèm dung sai;
   bấm Kiểm tra để soi tài khoản nào còn treo số dư.
4. **Chạy kết chuyển** — chọn kết chuyển theo tháng / quý / năm, xem trước rồi
   ghi sổ. Bộ chọn này quyết định luôn số liệu hiển thị ở bảng xem trước và
   bảng kiểm tra số dư cuối kỳ; mặc định bám theo kỳ trên thanh KỲ KẾ TOÁN.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.period import Period, PeriodScope, active_period, quarter_of
from data.repositories.account_repo import AccountRepository
from data.repositories.journal_repo import JournalRepository
from domain.models.transfer_rule import TransferDirection, TransferRule
from domain.money import format_money
from domain.services.journal_service import JournalService
from domain.services.result_service import ResultError, ResultService
from domain.models.zero_balance import ZeroBalanceRule
from domain.services.transfer_rule_service import (
    TransferRuleError,
    TransferRuleService,
)
from domain.services.zero_balance_service import (
    ZeroBalanceError,
    ZeroBalanceService,
    parse_tolerance,
)
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.card import Card

# Cột của lưới quy tắc.
(_C_SOURCE, _C_NAME, _C_SCOPE, _C_DIRECTION,
 _C_TARGET, _C_GROUP, _C_LABEL, _C_ACTIVE) = range(8)
_RULE_HEADERS = [
    "TK nguồn", "Tên tài khoản", "Phạm vi", "Chiều kết chuyển",
    "TK đích", "Số chứng từ", "Diễn giải", "Áp dụng",
]

_SCOPE_CHILDREN = "Gồm cả TK con"
_SCOPE_EXACT = "Chỉ đúng mã này"

# Cột của lưới "tài khoản không có số dư cuối kỳ".
(_Z_CODE, _Z_NAME, _Z_SCOPE, _Z_TOLERANCE, _Z_NOTE, _Z_ACTIVE) = range(6)
_ZERO_HEADERS = [
    "Tài khoản", "Tên tài khoản", "Phạm vi", "Dung sai", "Ghi chú", "Kiểm tra",
]


class ClosingScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ClosingScreen")

        self._rules_service = TransferRuleService()
        self._zero_service = ZeroBalanceService(accounts=AccountRepository())
        self._accounts = AccountRepository()
        # True trong lúc đổ dữ liệu vào lưới: chặn itemChanged chạy nửa chừng.
        self._loading = False
        # True trong lúc dựng / đồng bộ hai ô chọn kỳ: currentIndexChanged bắn
        # ngay từ addItem đầu tiên, mà lúc đó lưới còn chưa có.
        self._syncing = True
        self._anchor_month = active_period().anchor_month

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Kết chuyển cuối kỳ")
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(scroll, 1)

        container = QWidget()
        container.setObjectName("SettingsBody")
        body = QVBoxLayout(container)
        body.setContentsMargins(0, 0, 8, 0)
        body.setSpacing(16)
        scroll.setWidget(container)

        body.addWidget(self._build_accounts_card())
        body.addWidget(self._build_rules_card(), 1)
        body.addWidget(self._build_zero_balance_card(), 1)
        body.addWidget(self._build_run_card())
        body.addStretch(1)

        self._sync_scope_controls()
        self._reload()

    # ----- dựng giao diện --------------------------------------------------

    def _build_accounts_card(self) -> Card:
        card = Card(
            title="Tài khoản xác định kết quả",
            subtitle="TK trung gian nhận doanh thu / chi phí, và TK nhận lãi lỗ "
                     "cuối cùng. Bút toán KC-LN tự sinh theo hai tài khoản này.",
        )
        self._result_account = QLineEdit()
        self._result_account.setPlaceholderText("VD: 911")
        self._result_account.setMaximumWidth(160)
        self._profit_account = QLineEdit()
        self._profit_account.setPlaceholderText("VD: 4212")
        self._profit_account.setMaximumWidth(160)

        save = Button("Lưu tài khoản", variant=ButtonVariant.PRIMARY, icon_name="check")
        save.clicked.connect(self._on_save_accounts)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("TK xác định kết quả"))
        row.addWidget(self._result_account)
        row.addSpacing(16)
        row.addWidget(QLabel("TK lợi nhuận"))
        row.addWidget(self._profit_account)
        row.addWidget(save)
        row.addStretch(1)
        card.add_layout(row)
        return card

    def _build_rules_card(self) -> Card:
        card = Card(
            title="Quy tắc kết chuyển",
            subtitle="Mỗi dòng là một tài khoản được kết chuyển. Chọn chiều "
                     "\"Nợ TK nguồn / Có TK đích\" cho doanh thu (VD: 515 sang Có "
                     "911) và chiều ngược lại cho chi phí. Các dòng cùng số chứng "
                     "từ được gộp vào một bút toán.",
        )
        self._table = QTableWidget(0, len(_RULE_HEADERS))
        self._table.setHorizontalHeaderLabels(_RULE_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(_C_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(_C_LABEL, QHeaderView.Stretch)
        self._table.setMinimumHeight(320)
        self._table.itemChanged.connect(self._on_rule_cell_changed)
        card.add(self._table, 1)

        add = Button("Thêm dòng", icon_name="plus")
        add.clicked.connect(self._on_add_rule)
        remove = Button("Xóa dòng", variant=ButtonVariant.DANGER, icon_name="trash")
        remove.clicked.connect(self._on_remove_rule)
        restore = Button("Khôi phục mặc định", icon_name="settings")
        restore.clicked.connect(self._on_restore_defaults)
        save = Button("Lưu quy tắc", variant=ButtonVariant.PRIMARY, icon_name="check")
        save.clicked.connect(self._on_save_rules)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        row.addWidget(restore)
        row.addWidget(save)
        card.add_layout(row)
        return card

    def _build_zero_balance_card(self) -> Card:
        card = Card(
            title="Tài khoản không có số dư cuối kỳ",
            subtitle="Khai những tài khoản phải về 0 sau khi kết chuyển. Chương "
                     "trình chỉ kiểm tra và cảnh báo, không tự sửa sổ. Dung sai "
                     "để bỏ qua chênh lệch làm tròn (để 0 là phải sạch tuyệt đối).",
        )
        self._zero_table = QTableWidget(0, len(_ZERO_HEADERS))
        self._zero_table.setHorizontalHeaderLabels(_ZERO_HEADERS)
        self._zero_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._zero_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._zero_table.setAlternatingRowColors(True)
        self._zero_table.verticalHeader().setVisible(False)
        zero_header = self._zero_table.horizontalHeader()
        zero_header.setSectionResizeMode(QHeaderView.Interactive)
        zero_header.setSectionResizeMode(_Z_NAME, QHeaderView.Stretch)
        zero_header.setSectionResizeMode(_Z_NOTE, QHeaderView.Stretch)
        self._zero_table.setMinimumHeight(260)
        self._zero_table.itemChanged.connect(self._on_zero_cell_changed)
        card.add(self._zero_table, 1)

        add = Button("Thêm tài khoản", icon_name="plus")
        add.clicked.connect(self._on_add_zero_rule)
        remove = Button("Xóa dòng", variant=ButtonVariant.DANGER, icon_name="trash")
        remove.clicked.connect(self._on_remove_zero_rule)
        restore = Button("Khôi phục mặc định", icon_name="settings")
        restore.clicked.connect(self._on_restore_zero_defaults)
        save = Button("Lưu danh sách", variant=ButtonVariant.PRIMARY, icon_name="check")
        save.clicked.connect(self._on_save_zero_rules)
        check = Button("Kiểm tra số dư", icon_name="search")
        check.clicked.connect(self._on_check_zero_balance)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(add)
        row.addWidget(remove)
        row.addWidget(check)
        row.addStretch(1)
        row.addWidget(restore)
        row.addWidget(save)
        card.add_layout(row)

        self._zero_result = QTableWidget(0, 5)
        self._zero_result.setHorizontalHeaderLabels(
            ["Tài khoản", "Tên tài khoản", "Dư Nợ", "Dư Có", "Dung sai"]
        )
        self._zero_result.setSelectionMode(QAbstractItemView.NoSelection)
        self._zero_result.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._zero_result.setAlternatingRowColors(True)
        self._zero_result.verticalHeader().setVisible(False)
        self._zero_result.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._zero_result.setMinimumHeight(140)
        card.add(self._zero_result, 1)

        self._zero_note = QLabel()
        self._zero_note.setObjectName("SectionLabel")
        self._zero_note.setWordWrap(True)
        card.add(self._zero_note)
        return card

    def _build_run_card(self) -> Card:
        card = Card(
            title="Chạy kết chuyển",
            subtitle="Chọn kết chuyển theo tháng, theo quý hay theo năm — bảng "
                     "xem trước và bảng kiểm tra số dư bên trên đổi theo lựa "
                     "chọn này. Giá vốn (KC-GV) chạy trước, rồi tới các nhóm quy "
                     "tắc, cuối cùng là lãi/lỗ (KC-LN). Chạy lại thay thế bút "
                     "toán cũ.",
        )
        card.add_layout(self._build_scope_row())

        self._state_note = QLabel()
        self._state_note.setObjectName("SettingsNote")
        self._state_note.setWordWrap(True)

        self._preview = QTableWidget(0, 6)
        self._preview.setHorizontalHeaderLabels(
            ["Số chứng từ", "TK nguồn", "Tên tài khoản", "Ghi", "Số tiền", "TK đích"]
        )
        self._preview.setSelectionMode(QAbstractItemView.NoSelection)
        self._preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._preview.setAlternatingRowColors(True)
        self._preview.verticalHeader().setVisible(False)
        self._preview.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._preview.setMinimumHeight(220)

        self._preview_note = QLabel()
        self._preview_note.setObjectName("SectionLabel")

        refresh = Button("Xem trước", icon_name="search")
        refresh.clicked.connect(self._refresh_preview)
        post = Button("Kết chuyển", variant=ButtonVariant.PRIMARY, icon_name="check")
        post.clicked.connect(self._on_post)
        undo = Button("Hủy kết chuyển", variant=ButtonVariant.DANGER, icon_name="trash")
        undo.clicked.connect(self._on_unpost)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(refresh)
        row.addWidget(post)
        row.addWidget(undo)
        row.addStretch(1)
        card.add_layout(row)
        card.add(self._state_note)
        card.add(self._preview, 1)
        card.add(self._preview_note)
        return card

    def _build_scope_row(self) -> QHBoxLayout:
        """Hai ô chọn: kết chuyển theo mức nào, và cụ thể tháng/quý nào."""
        self._scope = QComboBox()
        for scope in (PeriodScope.MONTH, PeriodScope.QUARTER, PeriodScope.YEAR):
            self._scope.addItem(scope.label, scope.value)
        self._scope.setMinimumWidth(140)
        self._scope.currentIndexChanged.connect(self._on_scope_changed)

        self._slot = QComboBox()
        self._slot.setMinimumWidth(180)
        self._slot.currentIndexChanged.connect(self._on_slot_changed)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("Kết chuyển"))
        row.addWidget(self._scope)
        row.addWidget(self._slot)
        row.addStretch(1)
        return row

    # ----- nạp / hiển thị ---------------------------------------------------

    def on_activated(self) -> None:
        """Chrome gọi khi mở màn hình / đổi kỳ → đọc lại cấu hình và sổ."""
        self._sync_scope_controls()
        self._reload()

    # ----- kỳ kết chuyển (tháng / quý / năm) --------------------------------

    def _sync_scope_controls(self) -> None:
        """Kéo hai ô chọn về đúng kỳ trên thanh KỲ KẾ TOÁN."""
        period = active_period()
        self._syncing = True
        # Mốc tháng đi theo người dùng khi đổi qua lại tháng ↔ quý: chọn tháng
        # 05 rồi chuyển sang "theo quý" thì ra quý 2, không nhảy về quý khác.
        self._anchor_month = period.anchor_month
        index = self._scope.findData(period.scope.value)
        self._scope.setCurrentIndex(max(index, 0))
        self._fill_slot()
        self._syncing = False

    def _fill_slot(self) -> None:
        """Đổ danh sách tháng / quý của năm đang chọn vào ô thứ hai."""
        year = active_period().year
        scope = self._selected_scope()
        self._slot.clear()
        if scope is PeriodScope.YEAR:
            self._slot.addItem(f"Cả năm {year}", None)
            self._slot.setEnabled(False)
            return
        self._slot.setEnabled(True)
        if scope is PeriodScope.QUARTER:
            for q in range(1, 5):
                first = (q - 1) * 3 + 1
                self._slot.addItem(
                    f"Quý {q}/{year} (tháng {first:02d}–{first + 2:02d})", q)
            target = quarter_of(self._anchor_month)
        else:
            for m in range(1, 13):
                self._slot.addItem(f"Tháng {m:02d}/{year}", m)
            target = self._anchor_month
        index = self._slot.findData(target)
        self._slot.setCurrentIndex(max(index, 0))

    def _selected_scope(self) -> PeriodScope:
        # currentData() trả về str thuần với enum kế thừa str — phải ép lại kiểu.
        data = self._scope.currentData()
        return PeriodScope(data) if data else PeriodScope.YEAR

    def _closing_period(self) -> Period:
        """Kỳ mà mọi thứ trong thẻ "Chạy kết chuyển" nói tới.

        Năm luôn lấy từ thanh KỲ KẾ TOÁN; tháng / quý lấy từ hai ô chọn ở đây,
        nên kế toán chạy được từng tháng mà không phải rời màn hình.
        """
        year = active_period().year
        scope = self._selected_scope()
        if scope is PeriodScope.YEAR:
            return Period.of_year(year)
        value = self._slot.currentData()
        if value is None:       # ô chưa kịp đổ dữ liệu
            return Period.of_year(year)
        if scope is PeriodScope.QUARTER:
            return Period.of_quarter(year, int(value))
        return Period.of_month(year, int(value))

    def _on_scope_changed(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        self._fill_slot()
        self._syncing = False
        self._refresh_run_card()

    def _on_slot_changed(self) -> None:
        if self._syncing:
            return
        self._anchor_month = self._closing_period().anchor_month
        self._refresh_run_card()

    def _refresh_run_card(self) -> None:
        """Số liệu hiển thị bám theo kỳ kết chuyển vừa chọn."""
        self._refresh_state_note()
        self._refresh_preview()
        self._refresh_zero_check()

    def _reload(self) -> None:
        self._result_account.setText(self._rules_service.result_account())
        self._profit_account.setText(self._rules_service.profit_account())
        self._fill_rules(self._rules_service.list_rules())
        self._fill_zero_rules(self._zero_service.list_rules())
        self._refresh_run_card()

    def _result_service(self) -> ResultService:
        # Dựng mới mỗi lần để luôn đọc trạng thái sổ hiện tại.
        return ResultService(
            JournalService(JournalRepository()), self._accounts,
            rules=self._rules_service,
        )

    def _account_names(self) -> dict[str, str]:
        return {a.code: a.name for a in self._accounts.list_all()}

    def _fill_rules(self, rules: list[TransferRule]) -> None:
        names = self._account_names()
        self._loading = True
        self._table.setRowCount(0)
        for rule in rules:
            self._append_rule_row(rule, names)
        self._loading = False

    def _append_rule_row(self, rule: TransferRule, names: dict[str, str]) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, _C_SOURCE, QTableWidgetItem(rule.source_account))
        name_item = QTableWidgetItem(names.get(rule.source_account, ""))
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, _C_NAME, name_item)
        self._table.setItem(row, _C_TARGET, QTableWidgetItem(rule.target_account))
        self._table.setItem(row, _C_GROUP, QTableWidgetItem(rule.group_ref))
        self._table.setItem(row, _C_LABEL, QTableWidgetItem(rule.label))

        self._table.setCellWidget(row, _C_SCOPE, _scope_combo(rule.include_children))
        self._table.setCellWidget(row, _C_DIRECTION, _direction_combo(rule.direction))
        self._table.setCellWidget(row, _C_ACTIVE, _active_combo(rule.active))

    def _on_rule_cell_changed(self, item: QTableWidgetItem) -> None:
        """Gõ mã TK nguồn xong thì điền luôn tên để kế toán biết chọn đúng chưa."""
        if self._loading or item.column() != _C_SOURCE:
            return
        name = self._account_names().get(item.text().strip(), "")
        name_item = self._table.item(item.row(), _C_NAME)
        if name_item is not None:
            name_item.setText(name)

    def _collect_rules(self) -> list[TransferRule]:
        rules: list[TransferRule] = []
        for row in range(self._table.rowCount()):
            source = self._cell(row, _C_SOURCE)
            if not source:
                continue    # dòng vừa thêm mà chưa khai gì — bỏ qua
            rules.append(TransferRule(
                source_account=source,
                target_account=self._cell(row, _C_TARGET),
                direction=_combo_direction(self._table.cellWidget(row, _C_DIRECTION)),
                group_ref=self._cell(row, _C_GROUP),
                label=self._cell(row, _C_LABEL),
                include_children=_combo_flag(self._table.cellWidget(row, _C_SCOPE)),
                active=_combo_flag(self._table.cellWidget(row, _C_ACTIVE)),
                sort_order=(row + 1) * 10,
            ))
        return rules

    def _cell(self, row: int, column: int) -> str:
        item = self._table.item(row, column)
        return item.text().strip() if item is not None else ""

    # ----- lưới "không có số dư cuối kỳ" -----------------------------------

    def _fill_zero_rules(self, rules: list[ZeroBalanceRule]) -> None:
        names = self._account_names()
        self._loading = True
        self._zero_table.setRowCount(0)
        for rule in rules:
            self._append_zero_row(rule, names)
        self._loading = False

    def _append_zero_row(self, rule: ZeroBalanceRule, names: dict[str, str]) -> None:
        row = self._zero_table.rowCount()
        self._zero_table.insertRow(row)
        self._zero_table.setItem(row, _Z_CODE, QTableWidgetItem(rule.account_code))
        name_item = QTableWidgetItem(names.get(rule.account_code, rule.note))
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        self._zero_table.setItem(row, _Z_NAME, name_item)
        tolerance = QTableWidgetItem(format_money(rule.tolerance))
        tolerance.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._zero_table.setItem(row, _Z_TOLERANCE, tolerance)
        self._zero_table.setItem(row, _Z_NOTE, QTableWidgetItem(rule.note))
        self._zero_table.setCellWidget(
            row, _Z_SCOPE, _scope_combo(rule.include_children))
        self._zero_table.setCellWidget(row, _Z_ACTIVE, _active_combo(rule.active))

    def _on_zero_cell_changed(self, item: QTableWidgetItem) -> None:
        """Gõ mã TK xong thì điền luôn tên để biết chọn đúng tài khoản chưa."""
        if self._loading or item.column() != _Z_CODE:
            return
        name_item = self._zero_table.item(item.row(), _Z_NAME)
        if name_item is not None:
            name_item.setText(self._account_names().get(item.text().strip(), ""))

    def _collect_zero_rules(self) -> list[ZeroBalanceRule]:
        rules: list[ZeroBalanceRule] = []
        for row in range(self._zero_table.rowCount()):
            code = self._zero_cell(row, _Z_CODE)
            if not code:
                continue    # dòng vừa thêm mà chưa khai gì — bỏ qua
            rules.append(ZeroBalanceRule(
                account_code=code,
                include_children=_combo_flag(
                    self._zero_table.cellWidget(row, _Z_SCOPE)),
                tolerance=parse_tolerance(self._zero_cell(row, _Z_TOLERANCE)),
                note=self._zero_cell(row, _Z_NOTE),
                active=_combo_flag(self._zero_table.cellWidget(row, _Z_ACTIVE)),
                sort_order=(row + 1) * 10,
            ))
        return rules

    def _zero_cell(self, row: int, column: int) -> str:
        item = self._zero_table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _on_add_zero_rule(self) -> None:
        self._loading = True
        self._append_zero_row(ZeroBalanceRule(account_code=""), self._account_names())
        self._loading = False
        self._zero_table.setCurrentCell(self._zero_table.rowCount() - 1, _Z_CODE)

    def _on_remove_zero_rule(self) -> None:
        row = self._zero_table.currentRow()
        if row < 0:
            return
        self._zero_table.removeRow(row)

    def _on_restore_zero_defaults(self) -> None:
        confirm = QMessageBox.question(
            self, "Khôi phục mặc định",
            "Thay danh sách hiện có bằng bộ mặc định (511, 515, 632, 641, 642, "
            "711, 811, 821, 911…)?",
        )
        if confirm != QMessageBox.Yes:
            return
        self._fill_zero_rules(self._zero_service.restore_defaults())
        self._refresh_zero_check()

    def _on_save_zero_rules(self) -> None:
        try:
            saved = self._zero_service.save_rules(self._collect_zero_rules())
        except ZeroBalanceError as exc:
            QMessageBox.warning(self, "Không thể lưu danh sách", str(exc))
            return
        self._fill_zero_rules(saved)
        self._refresh_zero_check()
        QMessageBox.information(
            self, "Đã lưu",
            f"Đang theo dõi {len(saved)} tài khoản phải hết số dư cuối kỳ.\n"
            "Xóa hết dòng rồi Lưu là tắt hẳn việc kiểm tra.",
        )

    def _refresh_zero_check(self) -> None:
        """Dựng lại bảng kết quả kiểm tra theo kỳ kết chuyển đang chọn."""
        period = self._closing_period()
        report = self._zero_service.check(period.date_to)
        self._zero_result.setRowCount(0)
        for issue in report.issues:
            row = self._zero_result.rowCount()
            self._zero_result.insertRow(row)
            cells = [
                issue.account_code,
                issue.account_name or issue.note,
                format_money(issue.debit_balance) if issue.debit_balance else "",
                format_money(issue.credit_balance) if issue.credit_balance else "",
                format_money(issue.tolerance),
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if col >= 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._zero_result.setItem(row, col, item)
        if report.checked_accounts == 0:
            self._zero_note.setText(
                "Danh sách trống — chương trình không kiểm tra số dư cuối kỳ."
            )
        elif report.is_clean:
            self._zero_note.setText(
                f"Đến {period.date_to:%d/%m/%Y}: {report.checked_accounts} tài khoản "
                "theo dõi đều đã hết số dư."
            )
        else:
            self._zero_note.setText(
                f"Đến {period.date_to:%d/%m/%Y}: {len(report.issues)} tài khoản còn "
                f"số dư, tổng {format_money(report.total)}. Thường là do thiếu quy "
                "tắc kết chuyển, khai sai chiều Nợ/Có, hoặc có bút toán ghi thêm "
                "sau khi đã kết chuyển."
            )

    def _on_check_zero_balance(self) -> None:
        period = self._closing_period()
        report = self._zero_service.check(period.date_to)
        self._refresh_zero_check()
        if report.checked_accounts == 0:
            QMessageBox.information(
                self, "Chưa khai tài khoản nào",
                "Danh sách trống nên không có gì để kiểm tra. Bấm “Khôi phục mặc "
                "định” để lấy bộ tài khoản chuẩn.",
            )
            return
        if report.is_clean:
            QMessageBox.information(
                self, "Số dư cuối kỳ sạch",
                f"{report.checked_accounts} tài khoản theo dõi đều đã hết số dư "
                f"đến ngày {period.date_to:%d/%m/%Y}.",
            )
            return
        QMessageBox.warning(
            self, "Còn tài khoản treo số dư",
            f"Đến {period.date_to:%d/%m/%Y} còn {len(report.issues)} tài khoản "
            "chưa hết số dư:\n"
            + "\n".join(
                f"   {i.account_code}  {i.side_label} {format_money(abs(i.balance))}"
                for i in report.issues
            )
            + "\n\nKiểm tra lại bảng quy tắc kết chuyển hoặc chạy lại kết chuyển.",
        )

    # ----- hành động: cấu hình ---------------------------------------------

    def _on_save_accounts(self) -> None:
        try:
            retargeted = self._rules_service.set_result_accounts(
                self._result_account.text(), self._profit_account.text()
            )
        except TransferRuleError as exc:
            QMessageBox.warning(self, "Không thể lưu", str(exc))
            return
        self._reload()
        moved = (
            f"\n{retargeted} quy tắc đang trỏ về tài khoản cũ đã được chuyển sang "
            "tài khoản mới." if retargeted else ""
        )
        QMessageBox.information(
            self, "Đã lưu",
            "Lần kết chuyển sau sẽ dùng hai tài khoản này. Kỳ đã kết chuyển rồi "
            "thì bấm “Kết chuyển” lại để ghi theo cấu hình mới." + moved,
        )

    def _on_add_rule(self) -> None:
        self._loading = True
        self._append_rule_row(
            TransferRule(
                source_account="",
                target_account=self._result_account.text().strip(),
                group_ref="KC-CP",
                direction=TransferDirection.CREDIT_SOURCE,
            ),
            self._account_names(),
        )
        self._loading = False
        self._table.setCurrentCell(self._table.rowCount() - 1, _C_SOURCE)

    def _on_remove_rule(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._table.removeRow(row)

    def _on_restore_defaults(self) -> None:
        confirm = QMessageBox.question(
            self, "Khôi phục mặc định",
            "Thay toàn bộ quy tắc hiện có bằng bộ mặc định "
            "(511/512/515/711 sang Có 911; 632/635/641/642/811/812/821 sang Nợ 911)?",
        )
        if confirm != QMessageBox.Yes:
            return
        self._fill_rules(self._rules_service.restore_defaults())
        self._refresh_preview()

    def _on_save_rules(self) -> None:
        try:
            saved = self._rules_service.save_rules(self._collect_rules())
        except TransferRuleError as exc:
            QMessageBox.warning(self, "Không thể lưu quy tắc", str(exc))
            return
        self._fill_rules(saved)
        self._refresh_preview()
        QMessageBox.information(
            self, "Đã lưu quy tắc",
            f"Đã lưu {len(saved)} quy tắc kết chuyển. Bấm “Xem trước” để đối chiếu "
            "số tiền trước khi ghi sổ.",
        )

    # ----- hành động: chạy kết chuyển --------------------------------------

    def _refresh_state_note(self) -> None:
        period = self._closing_period()
        done = self._result_service().is_posted(period.date_from, period.date_to)
        active = active_period()
        # Kỳ trên thanh và kỳ kết chuyển tách nhau được — nói rõ khi lệch, nếu
        # không kế toán tưởng mình đang chạy cho kỳ ở thanh trên.
        differs = ("" if period == active
                   else f"   ·   thanh KỲ KẾ TOÁN đang là {active.label}")
        self._state_note.setText(
            f"Kỳ kết chuyển: {period.label} "
            f"({period.date_from:%d/%m/%Y} → {period.date_to:%d/%m/%Y}) — "
            f"{'đã kết chuyển' if done else 'chưa kết chuyển'}.{differs}"
        )

    def _refresh_preview(self) -> None:
        period = self._closing_period()
        plan = self._result_service().plan(period.date_from, period.date_to)
        self._preview.setRowCount(0)
        for group in plan.groups:
            for line in group.lines:
                row = self._preview.rowCount()
                self._preview.insertRow(row)
                source_debit = line.direction is TransferDirection.DEBIT_SOURCE
                cells = [
                    f"{group.ref_prefix}/{plan.period_tag}",
                    line.account_code,
                    line.account_name,
                    "Nợ" if source_debit else "Có",
                    format_money(line.amount),
                    f"{'Có' if source_debit else 'Nợ'} {line.target_account}",
                ]
                for col, value in enumerate(cells):
                    item = QTableWidgetItem(value)
                    if col == 4:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self._preview.setItem(row, col, item)
        if plan.is_empty:
            self._preview_note.setText(
                "Kỳ này chưa có phát sinh nào khớp quy tắc kết chuyển."
            )
            return
        verdict = "LÃI" if plan.is_profit else "LỖ"
        self._preview_note.setText(
            f"Doanh thu {format_money(plan.total_revenue)}   ·   "
            f"Chi phí {format_money(plan.total_expense)}   ·   "
            f"{verdict} {format_money(abs(plan.profit))} → TK {plan.profit_account}"
        )

    def _on_post(self) -> None:
        period = self._closing_period()
        service = self._result_service()
        if service.is_posted(period.date_from, period.date_to):
            confirm = QMessageBox.question(
                self, "Kết chuyển lại",
                f"Kỳ {period.label} đã kết chuyển rồi.\n"
                "Kết chuyển lại sẽ thay thế các bút toán KC cũ. Tiếp tục?",
            )
            if confirm != QMessageBox.Yes:
                return
        try:
            created = service.post(period.date_from, period.date_to)
        except (ResultError, ValueError) as exc:
            QMessageBox.warning(self, "Không thể kết chuyển", str(exc))
            return
        self._refresh_state_note()
        self._refresh_preview()
        # Kết chuyển xong là lúc duy nhất số dư "phải sạch" có thể kiểm chứng —
        # báo ngay thay vì để kế toán tự phát hiện khi lên báo cáo.
        report = self._zero_service.check(period.date_to)
        self._refresh_zero_check()
        summary = (
            f"Đã tạo {len(created)} bút toán cho kỳ {period.label}:\n"
            + "\n".join(f"   {e.ref} — {e.description}" for e in created)
            + "\n\nXem ở Sổ nhật ký chung."
        )
        if report.is_clean:
            QMessageBox.information(self, "Đã kết chuyển", summary)
            return
        QMessageBox.warning(
            self, "Đã kết chuyển — còn tài khoản treo số dư",
            summary + "\n\nNhưng các tài khoản sau vẫn còn số dư:\n"
            + "\n".join(
                f"   {i.account_code}  {i.side_label} {format_money(abs(i.balance))}"
                for i in report.issues
            ),
        )

    def _on_unpost(self) -> None:
        period = self._closing_period()
        confirm = QMessageBox.question(
            self, "Hủy kết chuyển",
            f"Xóa các bút toán kết chuyển (KC-…) của kỳ {period.label}?",
        )
        if confirm != QMessageBox.Yes:
            return
        self._result_service().unpost(period.date_from, period.date_to)
        self._refresh_state_note()
        self._refresh_preview()
        self._refresh_zero_check()
        QMessageBox.information(self, "Đã hủy", "Đã xóa các bút toán kết chuyển của kỳ.")


# ----- ô chọn trong lưới ----------------------------------------------------


def _direction_combo(direction: TransferDirection) -> QComboBox:
    combo = QComboBox()
    for value in (TransferDirection.DEBIT_SOURCE, TransferDirection.CREDIT_SOURCE):
        combo.addItem(f"{value.label} — {value.hint}", value.value)
    index = combo.findData(direction.value)
    combo.setCurrentIndex(max(index, 0))
    return combo


def _scope_combo(include_children: bool) -> QComboBox:
    combo = QComboBox()
    combo.addItem(_SCOPE_CHILDREN, True)
    combo.addItem(_SCOPE_EXACT, False)
    combo.setCurrentIndex(0 if include_children else 1)
    return combo


def _active_combo(active: bool) -> QComboBox:
    combo = QComboBox()
    combo.addItem("Có", True)
    combo.addItem("Không", False)
    combo.setCurrentIndex(0 if active else 1)
    return combo


def _combo_direction(widget) -> TransferDirection:
    # currentData() trả về str thuần với enum kế thừa str — phải ép lại kiểu.
    if widget is None:
        return TransferDirection.DEBIT_SOURCE
    return TransferDirection(widget.currentData())


def _combo_flag(widget) -> bool:
    return True if widget is None else bool(widget.currentData())
