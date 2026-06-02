"""SettingsScreen: app configuration — accounting circular (chế độ kế toán)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from data.repositories.account_repo import AccountRepository
from domain.services.account_service import AccountService
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.card import Card


class SettingsScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("SettingsScreen")

        self._service = AccountService(AccountRepository())

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Cấu hình")
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        card = Card(
            title="Chế độ kế toán / Thông tư áp dụng",
            subtitle="Chọn thông tư để nạp hệ thống tài khoản tương ứng.",
        )

        self._combo = QComboBox()
        for code, label in self._service.available_circulars():
            self._combo.addItem(label, code)
        current = self._service.active_circular()
        idx = self._combo.findData(current)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)

        note = QLabel(
            "Khi đổi thông tư, hệ thống chỉ NẠP THÊM các tài khoản mới — không xóa "
            "tài khoản nào và không ảnh hưởng tới bút toán đã ghi. Nếu một mã tài khoản "
            "có tên khác giữa hai thông tư, tên cũ được giữ nguyên; bạn có thể cập nhật "
            "trong Danh mục › Hệ thống tài khoản."
        )
        note.setObjectName("SettingsNote")
        note.setWordWrap(True)

        apply_btn = Button("Áp dụng", variant=ButtonVariant.PRIMARY, icon_name="check")
        apply_btn.clicked.connect(self._on_apply)

        row = QHBoxLayout()
        row.addWidget(self._combo, 1)
        row.addWidget(apply_btn)

        card.add_layout(row)
        card.add(note)
        root.addWidget(card)
        root.addStretch(1)

    def _on_apply(self) -> None:
        circular = self._combo.currentData()
        confirm = QMessageBox.question(
            self,
            "Đổi thông tư",
            f"Áp dụng {self._combo.currentText()}?\n"
            "Các tài khoản của thông tư này sẽ được nạp thêm.",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            result = self._service.set_circular(circular)
        except Exception as exc:
            QMessageBox.warning(self, "Không thể áp dụng", str(exc))
            return

        message = f"Đã thêm {result.added} tài khoản của {result.circular}."
        if result.conflicts:
            message += (
                f"\n\n{len(result.conflicts)} tài khoản có tên khác giữa hai thông tư "
                "(tên cũ được giữ nguyên). Mở Danh mục › Hệ thống tài khoản để cập nhật "
                "nếu cần:\n"
                + "\n".join(
                    f"  • {code}: {old} → {new}"
                    for code, old, new in result.conflicts[:8]
                )
            )
        QMessageBox.information(self, "Đã áp dụng thông tư", message)
