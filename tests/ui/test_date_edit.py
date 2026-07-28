"""DateEdit: xóa trắng ô ngày rồi gõ tay.

Chạy headless (QT_QPA_PLATFORM=offscreen) nên không cần màn hình thật.
"""
from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.primitives.date_edit import DateEdit, parse_date_text  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _press(widget, key: int, text: str = "") -> None:
    widget.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, key, Qt.NoModifier, text))


def _type(widget, text: str) -> None:
    for char in text:
        _press(widget, Qt.Key_unknown, char)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("01/02/2026", date(2026, 2, 1)),
        ("5/3/2026", date(2026, 3, 5)),
        ("01022026", date(2026, 2, 1)),
        ("01-02-2026", date(2026, 2, 1)),
        ("01.02.2026", date(2026, 2, 1)),
    ],
)
def test_parse_date_text_accepts_the_usual_hand_typed_forms(text, expected):
    parsed = parse_date_text(text)
    assert parsed is not None
    assert parsed.toPython() == expected


@pytest.mark.parametrize("text", ["", "   ", "linh tinh", "32/13/2026"])
def test_parse_date_text_rejects_nonsense(text):
    assert parse_date_text(text) is None


def test_select_all_then_delete_clears_the_field_for_free_typing(app):
    widget = DateEdit(value=QDate(2026, 1, 10))
    widget.lineEdit().selectAll()

    _press(widget, Qt.Key_Delete)

    assert widget.is_free_typing
    assert widget.lineEdit().text() == ""


def test_typing_a_full_date_by_hand_commits_on_enter(app):
    widget = DateEdit(value=QDate(2026, 1, 10))
    widget.lineEdit().selectAll()
    _press(widget, Qt.Key_Delete)

    _type(widget, "01/02/2026")
    _press(widget, Qt.Key_Return)

    assert not widget.is_free_typing
    assert widget.date_value() == date(2026, 2, 1)


def test_unreadable_hand_typed_text_falls_back_to_the_previous_date(app):
    widget = DateEdit(value=QDate(2026, 1, 10))
    widget.lineEdit().selectAll()
    _press(widget, Qt.Key_Delete)

    _type(widget, "abc")
    _press(widget, Qt.Key_Return)

    # Không bao giờ để ô rỗng / ngày rác: quay về ngày cũ.
    assert widget.date_value() == date(2026, 1, 10)
    assert widget.lineEdit().text() == "10/01/2026"


def test_escape_cancels_free_typing_and_restores_the_display(app):
    widget = DateEdit(value=QDate(2026, 1, 10))
    widget.lineEdit().selectAll()
    _press(widget, Qt.Key_Delete)
    _type(widget, "99")

    _press(widget, Qt.Key_Escape)

    assert not widget.is_free_typing
    assert widget.lineEdit().text() == "10/01/2026"
    assert widget.date_value() == date(2026, 1, 10)


def test_date_value_commits_pending_free_typing(app):
    """Bấm "Lưu" khi ô ngày còn đang gõ dở vẫn lấy đúng ngày vừa gõ."""
    widget = DateEdit(value=QDate(2026, 1, 10))
    widget.lineEdit().selectAll()
    _press(widget, Qt.Key_Delete)
    _type(widget, "15/06/2026")

    assert widget.date_value() == date(2026, 6, 15)
