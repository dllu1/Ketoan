"""Enter = nhảy ô kế tiếp (nhập liệu bàn phím, không cần chuột).

Hai lớp điều hướng, dùng độc lập hoặc chung:

* :func:`install_form_enter_nav` — trên một QDialog: Enter ở ô nhập bất kỳ sẽ
  chuyển focus sang ô sau thay vì bấm nút mặc định của hộp thoại. Nút bấm và ô
  nhiều dòng giữ nguyên hành vi gốc.
* :func:`install_grid_enter_nav` — trên một QTableWidget: Enter đi sang **ô sửa
  được** kế tiếp, hết dòng thì xuống đầu dòng dưới, hết bảng thì (tùy chọn) tự
  thêm dòng mới. Cột chỉ đọc (vd "Thành tiền") bị bỏ qua.

Khi ô đang mở editor, phím Enter tới *editor* chứ không tới bảng — Qt cho
delegate lọc sự kiện của editor nên :class:`EnterNavDelegate` là chỗ bắt. Mọi
delegate tùy biến trong app kế thừa lớp này để hành vi đồng nhất.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTextEdit,
)

_ENTER_KEYS = (Qt.Key_Return, Qt.Key_Enter)

# Ô nhập được phép "Enter = sang ô sau". QTextEdit/QPlainTextEdit cố ý không có
# trong danh sách: Enter ở đó là xuống dòng.
_FORM_FIELDS = (QLineEdit, QComboBox, QAbstractSpinBox)

# Bộ điều hướng của từng bảng: advance_to_next_cell cần biết có được tự thêm
# dòng khi chạm đáy hay không. Bộ điều hướng là con của bảng nên cùng vòng đời.
_GRID_NAV: dict[QTableWidget, "_GridEnterNav"] = {}


class EnterNavDelegate(QStyledItemDelegate):
    """Delegate nền: Enter trong editor = ghi giá trị rồi nhảy ô kế tiếp."""

    def eventFilter(self, editor, event) -> bool:  # noqa: N802 (Qt signature)
        if event.type() == QEvent.KeyPress and event.key() in _ENTER_KEYS \
                and not _completer_popup_open(editor):
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QStyledItemDelegate.NoHint)
            table = self.parent()
            if isinstance(table, QTableWidget):
                # Hoãn một vòng lặp: để Qt đóng editor xong mới mở ô kế tiếp.
                QTimer.singleShot(0, lambda: advance_to_next_cell(table))
            return True
        return super().eventFilter(editor, event)


def _completer_popup_open(editor) -> bool:
    """Popup gợi ý đang mở → Enter là "chọn mục", chưa phải nhảy ô."""
    getter = getattr(editor, "completer", None)
    completer = getter() if callable(getter) else None
    return completer is not None and completer.popup().isVisible()


def install_form_enter_nav(dialog: QDialog) -> None:
    """Enter ở ô nhập của ``dialog`` = sang ô sau (thay vì bấm nút mặc định)."""
    dialog.installEventFilter(_FormEnterNav(dialog))


def install_grid_enter_nav(
    table: QTableWidget, *, add_row: Callable[[], None] | None = None
) -> None:
    """Enter trong ``table`` = sang ô sửa được kế tiếp.

    ``add_row`` (nếu có) được gọi khi Enter ở ô cuối bảng, để nhập liên tục
    không phải với chuột bấm "+ Thêm dòng".
    """
    nav = _GridEnterNav(table, add_row)
    table.installEventFilter(nav)
    # Cột không gắn delegate riêng vẫn cần Enter-nhảy-ô trong lúc sửa.
    table.setItemDelegate(EnterNavDelegate(table))
    _GRID_NAV[table] = nav


def advance_to_next_cell(table: QTableWidget) -> None:
    """Đưa con trỏ (và editor) tới ô sửa được kế tiếp của ``table``."""
    row, col = table.currentRow(), table.currentColumn()
    if row < 0 or col < 0:
        return
    target = next_editable_cell(table, row, col)
    if target is None:
        nav = _GRID_NAV.get(table)
        if nav is None or nav.add_row is None:
            return
        nav.add_row()
        target = first_editable_cell(table, table.rowCount() - 1)
        if target is None:
            return
    table.setCurrentCell(*target)
    item = table.item(*target)
    if item is not None:
        table.editItem(item)


def next_editable_cell(
    table: QTableWidget, row: int, col: int
) -> tuple[int, int] | None:
    """Ô sửa được ngay sau (row, col) theo thứ tự đọc; ``None`` nếu hết bảng."""
    columns = table.columnCount()
    while True:
        col += 1
        if col >= columns:
            col = 0
            row += 1
        if row >= table.rowCount():
            return None
        if _is_editable(table, row, col):
            return row, col


def first_editable_cell(table: QTableWidget, row: int) -> tuple[int, int] | None:
    """Ô sửa được đầu tiên của một dòng."""
    if row < 0 or row >= table.rowCount():
        return None
    for col in range(table.columnCount()):
        if _is_editable(table, row, col):
            return row, col
    return None


def _is_editable(table: QTableWidget, row: int, col: int) -> bool:
    if table.isColumnHidden(col) or table.isRowHidden(row):
        return False
    item = table.item(row, col)
    if item is None:
        return False
    return bool(item.flags() & Qt.ItemIsEditable)


class _GridEnterNav(QObject):
    """Bắt Enter khi bảng *không* mở editor (vừa chọn ô bằng chuột/mũi tên)."""

    def __init__(self, table: QTableWidget, add_row: Callable[[], None] | None) -> None:
        super().__init__(table)
        self._table = table
        self.add_row = add_row

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt signature)
        if obj is self._table and event.type() == QEvent.KeyPress \
                and event.key() in _ENTER_KEYS:
            advance_to_next_cell(self._table)
            return True
        return super().eventFilter(obj, event)


class _FormEnterNav(QObject):
    """Bắt Enter ở các ô nhập của hộp thoại và chuyển focus sang ô kế tiếp."""

    # Cố ý không giữ thuộc tính Python nào: bộ lọc chỉ sống nhờ cha C++ (hộp
    # thoại), nên vỏ Python có thể bị GC rồi PySide dựng lại vỏ *trống* khi Qt
    # gọi eventFilter. Dùng parent() để không phụ thuộc vào vỏ Python.

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt signature)
        dialog = self.parent()
        if obj is not dialog or event.type() != QEvent.KeyPress \
                or event.key() not in _ENTER_KEYS:
            return super().eventFilter(obj, event)
        focus = dialog.focusWidget()
        if focus is None or isinstance(focus, (QPushButton, QTextEdit, QPlainTextEdit)):
            return super().eventFilter(obj, event)
        # Trong bảng: đã có _GridEnterNav lo, đừng cướp focus ra khỏi lưới.
        if isinstance(focus, QAbstractItemView) or _inside_item_view(focus):
            return super().eventFilter(obj, event)
        if isinstance(focus, _FORM_FIELDS):
            focus.focusNextChild()
            return True
        return super().eventFilter(obj, event)


def _inside_item_view(widget) -> bool:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractItemView):
            return True
        parent = parent.parentWidget()
    return False
