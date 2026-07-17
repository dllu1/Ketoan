"""SettingsScreen: app configuration — accounting circular (chế độ kế toán)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.theme import current_mode, set_mode
from data.repositories.account_repo import AccountRepository
from domain.models.company import CompanyProfile
from domain.services.account_service import AccountService
from domain.services.closing_service import ClosingService
from domain.services.company_service import CompanyService
from domain.services.email_config_service import (
    AUTH_OAUTH,
    AUTH_PASSWORD,
    PROVIDER_PRESETS,
    EmailConfig,
    EmailConfigService,
)
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.card import Card


class _ConsentWorker(QThread):
    """Chạy OAuth consent flow (mở trình duyệt + server loopback) ngoài GUI thread."""

    done = Signal(object, object)  # refresh_token|None, error|None

    def __init__(self, client_id: str, client_secret: str, parent=None) -> None:
        super().__init__(parent)
        self._client_id = client_id
        self._client_secret = client_secret

    def run(self) -> None:  # noqa: D401 — QThread entrypoint
        try:
            from data.email.oauth import run_consent_flow

            token = run_consent_flow(self._client_id, self._client_secret)
            self.done.emit(token, None)
        except Exception as exc:  # noqa: BLE001 — báo về main thread, không crash
            self.done.emit(None, exc)


class SettingsScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("SettingsScreen")

        self._service = AccountService(AccountRepository())
        self._closing = ClosingService()
        self._company = CompanyService()
        self._email_cfg = EmailConfigService()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Cấu hình")
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        # Scrollable body — the cards below can exceed the viewport height.
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

        # ----- thông tin công ty (người nộp thuế) ------------------------
        company_card = Card(
            title="Thông tin công ty",
            subtitle="Dùng để điền sẵn phần đầu các tờ khai thuế (tên, MST, địa chỉ).",
        )
        profile = self._company.load()
        self._company_name = self._make_input(
            profile.name, "VD: CÔNG TY TNHH THƯƠNG MẠI - SẢN XUẤT …")
        self._company_tax = self._make_input(profile.tax_code, "VD: 0302830818")
        self._company_addr = self._make_input(profile.address, "Địa chỉ trụ sở chính")

        company_card.add_layout(
            self._field_row("Tên người nộp thuế", self._company_name))
        company_card.add_layout(
            self._field_row("Mã số thuế (MST)", self._company_tax))
        company_card.add_layout(self._field_row("Địa chỉ", self._company_addr))

        save_company = Button("Lưu thông tin", variant=ButtonVariant.PRIMARY,
                              icon_name="check")
        save_company.clicked.connect(self._on_save_company)
        company_row = QHBoxLayout()
        company_row.addStretch(1)
        company_row.addWidget(save_company)
        company_card.add_layout(company_row)
        body.addWidget(company_card)

        # ----- giao diện: sáng / tối -------------------------------------
        theme_card = Card(
            title="Giao diện",
            subtitle="Chọn chế độ hiển thị sáng (mặc định) hoặc tối.",
        )
        self._theme = QComboBox()
        self._theme.addItem("Sáng (Light)", "light")
        self._theme.addItem("Tối (Dark)", "dark")
        idx = self._theme.findData(current_mode())
        if idx >= 0:
            self._theme.setCurrentIndex(idx)
        self._theme.currentIndexChanged.connect(self._on_theme_changed)
        theme_row = QHBoxLayout()
        theme_row.addWidget(self._theme, 1)
        theme_row.addStretch(1)
        theme_card.add_layout(theme_row)
        body.addWidget(theme_card)

        body.addWidget(self._build_demo_card())

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
        body.addWidget(card)

        # ----- chốt sổ cuối năm ------------------------------------------
        close_card = Card(
            title="Chốt sổ cuối năm",
            subtitle="Khóa toàn bộ chứng từ của một năm tài chính.",
        )
        self._year_combo = QComboBox()
        self._close_btn = Button("Chốt sổ", variant=ButtonVariant.PRIMARY, icon_name="check")
        self._close_btn.clicked.connect(self._on_close_year)
        close_row = QHBoxLayout()
        close_row.addWidget(self._year_combo, 1)
        close_row.addWidget(self._close_btn)

        self._close_note = QLabel()
        self._close_note.setObjectName("SettingsNote")
        self._close_note.setWordWrap(True)

        close_card.add_layout(close_row)
        close_card.add(self._close_note)
        body.addWidget(close_card)
        self._refresh_closing()

        body.addWidget(self._build_email_card())

        body.addStretch(1)

    # ----- dữ liệu mẫu (demo) -------------------------------------------

    def _build_demo_card(self) -> Card:
        card = Card(
            title="Dữ liệu mẫu (Demo)",
            subtitle="Nạp bộ số liệu mẫu 12 tháng để xem thử cách chương trình tính toán.",
        )
        note = QLabel(
            "• Bấm “Nạp dữ liệu mẫu” để tạo sẵn khách hàng, nhà cung cấp, hóa đơn "
            "mua/bán, tồn kho, tài sản và bảng tính giá thành của một năm — rồi mở "
            "Tổng quan, Báo cáo, Kho hàng… để đối chiếu kết quả.\n"
            "• Bấm “Xóa toàn bộ dữ liệu” khi muốn bắt đầu nhập số liệu thật.\n\n"
            "Lưu ý: cả hai thao tác đều XÓA sạch dữ liệu đang có trước khi chạy. "
            "Hệ thống tài khoản và thông tư đang chọn luôn được giữ nguyên."
        )
        note.setObjectName("SettingsNote")
        note.setWordWrap(True)
        card.add(note)

        load_btn = Button("Nạp dữ liệu mẫu", variant=ButtonVariant.PRIMARY,
                          icon_name="sparkle")
        load_btn.clicked.connect(self._on_load_demo)
        clear_btn = Button("Xóa toàn bộ dữ liệu", variant=ButtonVariant.DANGER,
                           icon_name="trash")
        clear_btn.clicked.connect(self._on_clear_data)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(clear_btn)
        row.addWidget(load_btn)
        card.add_layout(row)
        return card

    def _on_load_demo(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Nạp dữ liệu mẫu",
            "Thao tác này sẽ XÓA toàn bộ dữ liệu hiện có rồi tạo lại bộ số liệu "
            "mẫu 12 tháng.\nHệ thống tài khoản và thông tư được giữ nguyên. Tiếp tục?",
        )
        if confirm != QMessageBox.Yes:
            return
        # Nạp qua service thật nên có thể mất vài giây — hiện con trỏ chờ.
        from data.seed import seed_demo

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            seed_demo(reset=True)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Không thể nạp dữ liệu mẫu", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_closing()
        QMessageBox.information(
            self, "Đã nạp dữ liệu mẫu",
            "Đã tạo xong bộ số liệu mẫu.\nMở các phân hệ Tổng quan / Bán hàng / "
            "Mua hàng / Kho hàng / Báo cáo để xem chương trình tính toán.",
        )

    def _on_clear_data(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Xóa toàn bộ dữ liệu",
            "Xóa sạch mọi chứng từ, hóa đơn, tồn kho, bảng kê… để bắt đầu nhập "
            "số liệu thật?\nHệ thống tài khoản và thông tư được giữ nguyên. "
            "Thao tác không thể hoàn tác.",
        )
        if confirm != QMessageBox.Yes:
            return
        from data.seed import reset_data

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            reset_data()
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_closing()
        QMessageBox.information(
            self, "Đã xóa dữ liệu",
            "Sổ kế toán đã trống. Bạn có thể bắt đầu nhập số liệu thật.",
        )

    # ----- email / hóa đơn điện tử --------------------------------------

    def _build_email_card(self) -> Card:
        cfg = self._email_cfg.load()
        card = Card(
            title="Email / Hóa đơn điện tử",
            subtitle="Tự lấy HĐĐT (XML+PDF) nhà cung cấp gửi về hộp thư rồi nhập nháp.",
        )

        self._email_provider = QComboBox()
        self._email_provider.addItem("Gmail", "gmail")
        self._email_provider.addItem("Yahoo Mail", "yahoo")
        self._email_provider.addItem("Tùy chỉnh (IMAP)", "custom")
        i = self._email_provider.findData(cfg.provider)
        if i >= 0:
            self._email_provider.setCurrentIndex(i)
        self._email_provider.currentIndexChanged.connect(
            self._on_email_provider_changed)

        # Cách xác thực: OAuth (Gmail/Workspace, không cần App Password) hoặc
        # App Password / mật khẩu IMAP thường (Yahoo, máy chủ tùy chỉnh).
        self._email_auth_mode = QComboBox()
        self._email_auth_mode.addItem("OAuth (Google / Workspace)", AUTH_OAUTH)
        self._email_auth_mode.addItem("App Password / mật khẩu IMAP", AUTH_PASSWORD)
        j = self._email_auth_mode.findData(cfg.auth_mode)
        if j >= 0:
            self._email_auth_mode.setCurrentIndex(j)
        self._email_auth_mode.currentIndexChanged.connect(self._on_auth_mode_changed)

        self._email_host = self._make_input(cfg.host, "VD: imap.gmail.com")
        self._email_port = self._make_input(str(cfg.port), "993")
        self._email_address = self._make_input(cfg.email, "you@gmail.com")
        self._email_password = self._make_input(cfg.app_password, "App Password")
        self._email_password.setEchoMode(QLineEdit.Password)

        # Trường OAuth (Client ID / Secret lấy từ Google Cloud Console → Desktop app).
        self._oauth_refresh_token = cfg.oauth_refresh_token
        self._email_client_id = self._make_input(
            cfg.oauth_client_id, "xxxxx.apps.googleusercontent.com")
        self._email_client_secret = self._make_input(
            cfg.oauth_client_secret, "Client secret")
        self._email_client_secret.setEchoMode(QLineEdit.Password)
        self._oauth_status = QLabel()
        self._oauth_status.setObjectName("SettingsNote")
        self._oauth_login_btn = Button("Đăng nhập Google", icon_name="check")
        self._oauth_login_btn.clicked.connect(self._on_oauth_login)

        self._email_folder = self._make_input(cfg.folder, "INBOX")
        self._email_poll = self._make_input(str(cfg.poll_minutes), "15")
        self._email_auto = QCheckBox("Tự động kiểm tra hộp thư định kỳ")
        self._email_auto.setChecked(cfg.auto_enabled)

        card.add_layout(self._field_row("Nhà cung cấp", self._email_provider))
        card.add_layout(self._field_row("Cách xác thực", self._email_auth_mode))
        card.add_layout(self._field_row("Máy chủ IMAP", self._email_host))
        card.add_layout(self._field_row("Cổng", self._email_port))
        card.add_layout(self._field_row("Địa chỉ email", self._email_address))

        # Các dòng phụ thuộc cách xác thực → bọc trong QWidget để ẩn/hiện.
        self._password_row_w = self._field_row_widget("App Password", self._email_password)
        self._client_id_row_w = self._field_row_widget("Client ID", self._email_client_id)
        self._client_secret_row_w = self._field_row_widget(
            "Client Secret", self._email_client_secret)
        oauth_action = QHBoxLayout()
        oauth_action.setContentsMargins(0, 0, 0, 0)
        oauth_action.addWidget(self._oauth_status, 1)
        oauth_action.addWidget(self._oauth_login_btn)
        self._oauth_action_w = QWidget()
        self._oauth_action_w.setLayout(oauth_action)

        card.add(self._password_row_w)
        card.add(self._client_id_row_w)
        card.add(self._client_secret_row_w)
        card.add(self._oauth_action_w)

        card.add_layout(self._field_row("Thư mục", self._email_folder))
        card.add_layout(self._field_row("Chu kỳ (phút)", self._email_poll))

        auto_row = QHBoxLayout()
        auto_row.addWidget(self._email_auto, 1)
        card.add_layout(auto_row)

        note = QLabel(
            "OAuth (khuyên dùng cho Gmail/Workspace): tạo OAuth client 'Desktop app' "
            "trong Google Cloud Console (scope https://mail.google.com/), dán Client "
            "ID/Secret rồi bấm “Đăng nhập Google”. App Password chỉ dùng cho Yahoo hoặc "
            "IMAP tùy chỉnh. Thông tin chỉ lưu trên máy này. Phân loại bán/mua tự động "
            "theo MST công ty đã khai ở phần Thông tin công ty."
        )
        note.setObjectName("SettingsNote")
        note.setWordWrap(True)
        card.add(note)

        self._on_auth_mode_changed()  # đặt trạng thái ẩn/hiện + nhãn ban đầu

        rescan_btn = Button("Quét lại từ đầu", icon_name="invoice")
        rescan_btn.clicked.connect(self._on_rescan_email)
        test_btn = Button("Kiểm tra kết nối", icon_name="check")
        test_btn.clicked.connect(self._on_test_email)
        save_btn = Button("Lưu cấu hình", variant=ButtonVariant.PRIMARY,
                          icon_name="check")
        save_btn.clicked.connect(self._on_save_email)
        btn_row = QHBoxLayout()
        btn_row.addWidget(rescan_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(test_btn)
        btn_row.addWidget(save_btn)
        card.add_layout(btn_row)
        return card

    def _read_email_form(self) -> EmailConfig:
        def _to_int(text: str, default: int) -> int:
            try:
                return int(text.strip())
            except (TypeError, ValueError):
                return default

        return EmailConfig(
            provider=self._email_provider.currentData(),
            host=self._email_host.text(),
            port=_to_int(self._email_port.text(), 993),
            email=self._email_address.text(),
            app_password=self._email_password.text(),
            folder=self._email_folder.text(),
            auto_enabled=self._email_auto.isChecked(),
            poll_minutes=_to_int(self._email_poll.text(), 15),
            last_uid=self._email_cfg.load().last_uid,
            auth_mode=self._email_auth_mode.currentData(),
            oauth_client_id=self._email_client_id.text(),
            oauth_client_secret=self._email_client_secret.text(),
            oauth_refresh_token=self._oauth_refresh_token,
        )

    def _on_email_provider_changed(self) -> None:
        provider = self._email_provider.currentData()
        preset_host, preset_port = PROVIDER_PRESETS.get(
            provider, PROVIDER_PRESETS["custom"])
        if provider != "custom":
            self._email_host.setText(preset_host)
            self._email_port.setText(str(preset_port))

    def _on_test_email(self) -> None:
        from data.email.imap_client import EmailFetchError, test_connection

        config = self._read_email_form()
        if not config.is_ready:
            missing = (
                "Máy chủ IMAP, Địa chỉ email, Client ID/Secret và đã “Đăng nhập "
                "Google”."
                if config.is_oauth
                else "Máy chủ IMAP, Địa chỉ email và App Password."
            )
            QMessageBox.warning(
                self, "Kiểm tra kết nối", f"Cần nhập đủ: {missing}")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            test_connection(config)
        except EmailFetchError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Kiểm tra kết nối", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        QMessageBox.information(
            self, "Kiểm tra kết nối", "Kết nối hộp thư thành công.")

    def _on_save_email(self) -> None:
        self._email_cfg.save(self._read_email_form())
        QMessageBox.information(
            self, "Đã lưu",
            "Đã lưu cấu hình email. Tự động kiểm tra sẽ áp dụng ở lần mở app sau.")

    def _on_rescan_email(self) -> None:
        """Đặt lại mốc UID về 0 để lần lấy tới quét lại toàn bộ thư từ đầu.

        Cần khi đổi thư mục (vd INBOX → [Gmail]/Sent Mail): UID mỗi thư mục là
        một không gian riêng, mốc cũ có thể khiến bỏ sót thư. Hóa đơn đã nhập
        trước đó không bị trùng vì persist() bỏ qua chứng từ trùng số.
        """
        reply = QMessageBox.question(
            self, "Quét lại từ đầu",
            "Đặt lại mốc quét về đầu hộp thư? Lần lấy hóa đơn tới sẽ duyệt lại "
            "toàn bộ thư trong thư mục (chứng từ đã nhập sẽ được bỏ qua, không "
            "tạo trùng).",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._email_cfg.set_last_uid(0)
        QMessageBox.information(
            self, "Quét lại từ đầu",
            "Đã đặt lại mốc quét. Bấm “Lấy từ email” ở màn hình chứng từ để "
            "quét lại từ đầu.")

    def _field_row_widget(self, label_text: str, field: QLineEdit) -> QWidget:
        """Bọc một field-row trong QWidget để ẩn/hiện theo cách xác thực."""
        w = QWidget()
        layout = self._field_row(label_text, field)
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        return w

    def _on_auth_mode_changed(self) -> None:
        is_oauth = self._email_auth_mode.currentData() == AUTH_OAUTH
        self._password_row_w.setVisible(not is_oauth)
        self._client_id_row_w.setVisible(is_oauth)
        self._client_secret_row_w.setVisible(is_oauth)
        self._oauth_action_w.setVisible(is_oauth)
        self._update_oauth_status()

    def _update_oauth_status(self) -> None:
        if self._oauth_refresh_token:
            self._oauth_status.setText("✅ Đã cấp quyền (đã có refresh token).")
        else:
            self._oauth_status.setText("Chưa cấp quyền — bấm “Đăng nhập Google”.")

    def _on_oauth_login(self) -> None:
        client_id = self._email_client_id.text().strip()
        client_secret = self._email_client_secret.text().strip()
        if not (client_id and client_secret):
            QMessageBox.warning(
                self, "Đăng nhập Google",
                "Cần nhập Client ID và Client Secret trước khi đăng nhập.")
            return
        self._oauth_login_btn.setEnabled(False)
        self._oauth_status.setText("Đang mở trình duyệt để cấp quyền…")
        self._consent_worker = _ConsentWorker(client_id, client_secret, self)
        self._consent_worker.done.connect(self._on_consent_done)
        self._consent_worker.start()

    def _on_consent_done(self, refresh_token: object, error: object) -> None:
        self._oauth_login_btn.setEnabled(True)
        if error is not None:
            self._update_oauth_status()
            QMessageBox.warning(self, "Đăng nhập Google", str(error))
            self._consent_worker = None
            return
        self._oauth_refresh_token = str(refresh_token)
        # Lưu cả cấu hình luôn để token dùng được ngay (cần Client ID/Secret đi kèm).
        self._email_cfg.save(self._read_email_form())
        self._update_oauth_status()
        QMessageBox.information(
            self, "Đăng nhập Google",
            "Đã cấp quyền và lưu. Bấm “Kiểm tra kết nối” để xác nhận.")
        self._consent_worker = None

    # ----- chốt sổ ------------------------------------------------------

    def _refresh_closing(self) -> None:
        self._year_combo.clear()
        closable = self._closing.closable_years()
        for year in reversed(closable):
            self._year_combo.addItem(str(year), year)
        has_closable = bool(closable)
        self._year_combo.setEnabled(has_closable)
        self._close_btn.setEnabled(has_closable)

        closed = sorted(self._closing.closed_years(), reverse=True)
        closed_text = ", ".join(str(y) for y in closed) if closed else "chưa có"
        msg = (
            "Sau khi chốt, mọi bút toán/hóa đơn của năm đó sẽ bị khóa, không thể "
            "thêm, sửa hoặc xóa. Nếu cuối năm không chốt, hệ thống tự động chốt sau "
            "48 giờ.\n"
            f"Các năm đã chốt: {closed_text}."
        )
        if not has_closable:
            msg = "Hiện chưa có năm tài chính nào đã kết thúc để chốt sổ.\n" + msg
        self._close_note.setText(msg)

    def _on_close_year(self) -> None:
        year = self._year_combo.currentData()
        if year is None:
            return
        confirm = QMessageBox.question(
            self,
            "Chốt sổ cuối năm",
            f"Chốt sổ năm {year}?\n"
            "Toàn bộ chứng từ của năm này sẽ bị khóa và không thể chỉnh sửa.",
        )
        if confirm != QMessageBox.Yes:
            return
        self._closing.close_year(year)
        QMessageBox.information(self, "Đã chốt sổ", f"Đã chốt sổ năm {year}.")
        self._refresh_closing()

    @staticmethod
    def _make_input(value: str, placeholder: str) -> QLineEdit:
        edit = QLineEdit(value)
        edit.setPlaceholderText(placeholder)
        edit.setMinimumHeight(32)
        return edit

    @staticmethod
    def _field_row(label_text: str, field: QLineEdit) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        label = QLabel(label_text)
        label.setObjectName("SettingsFieldLabel")
        label.setMinimumWidth(150)
        row.addWidget(label)
        row.addWidget(field, 1)
        return row

    def _on_save_company(self) -> None:
        self._company.save(CompanyProfile(
            name=self._company_name.text(),
            tax_code=self._company_tax.text(),
            address=self._company_addr.text(),
        ))
        QMessageBox.information(
            self, "Đã lưu", "Đã lưu thông tin công ty."
        )

    def _on_theme_changed(self) -> None:
        app = QApplication.instance()
        if app is not None:
            set_mode(app, self._theme.currentData())

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
