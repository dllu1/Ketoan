"""EmailConfigService: cấu hình hộp thư IMAP để lấy hóa đơn điện tử (HĐĐT).

Lưu trong bảng ``settings`` (key/value) — cùng pattern với CompanyService. App
password chỉ obfuscate base64 (đây là máy cục bộ, không phải lớp bảo mật thực sự;
OS keyring để ngoài phạm vi).
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

from data.repositories.settings_repo import SettingsRepository

# Preset máy chủ IMAP theo nhà cung cấp phổ biến.
PROVIDER_PRESETS: dict[str, tuple[str, int]] = {
    "gmail": ("imap.gmail.com", 993),
    "yahoo": ("imap.mail.yahoo.com", 993),
    "custom": ("", 993),
}

_PROVIDER_KEY = "email_provider"
_HOST_KEY = "email_host"
_PORT_KEY = "email_port"
_ADDRESS_KEY = "email_address"
_PASSWORD_KEY = "email_app_password"
_FOLDER_KEY = "email_folder"
_AUTO_KEY = "email_auto_enabled"
_POLL_KEY = "email_poll_minutes"
_LAST_UID_KEY = "email_last_uid"
_AUTH_MODE_KEY = "email_auth_mode"
_OAUTH_CLIENT_ID_KEY = "email_oauth_client_id"
_OAUTH_CLIENT_SECRET_KEY = "email_oauth_client_secret"
_OAUTH_REFRESH_KEY = "email_oauth_refresh_token"

# Cách xác thực IMAP.
AUTH_PASSWORD = "password"  # App Password / mật khẩu IMAP thường (Yahoo, custom)
AUTH_OAUTH = "oauth"  # OAuth2 XOAUTH2 — Gmail/Workspace không cần App Password


def _normalize_password(value: str) -> str:
    """Bỏ mọi khoảng trắng trong App Password.

    Google hiển thị App Password dạng ``abcd efgh ijkl mnop`` và người dùng
    thường dán kèm dấu cách, nhưng IMAP yêu cầu 16 ký tự liền → phải gỡ hết
    khoảng trắng (kể cả ở giữa) nếu không sẽ nhận ``Invalid credentials``.
    """
    return "".join(value.split())


def _obfuscate(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _deobfuscate(value: str) -> str:
    if not value:
        return ""
    try:
        return base64.b64decode(value.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        # Giá trị cũ/không hợp lệ → coi như chưa đặt mật khẩu.
        return ""


@dataclass
class EmailConfig:
    provider: str = "gmail"
    host: str = "imap.gmail.com"
    port: int = 993
    email: str = ""
    app_password: str = ""
    folder: str = "INBOX"
    auto_enabled: bool = False
    poll_minutes: int = 15
    last_uid: int = 0
    auth_mode: str = AUTH_PASSWORD
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_refresh_token: str = ""

    def __post_init__(self) -> None:
        # Chốt chặn duy nhất: mọi EmailConfig (form UI, load DB, test kết nối)
        # đều đi qua đây → App Password luôn sạch khoảng trắng trước khi login.
        self.app_password = _normalize_password(self.app_password)
        if self.auth_mode not in (AUTH_PASSWORD, AUTH_OAUTH):
            self.auth_mode = AUTH_PASSWORD

    @property
    def is_oauth(self) -> bool:
        return self.auth_mode == AUTH_OAUTH

    @property
    def is_ready(self) -> bool:
        """Đủ thông tin để thử kết nối IMAP."""
        if not (self.host and self.email):
            return False
        if self.is_oauth:
            # OAuth: cần Client ID/Secret + refresh token đã cấp quyền.
            return bool(
                self.oauth_client_id
                and self.oauth_client_secret
                and self.oauth_refresh_token
            )
        return bool(self.app_password)


class EmailConfigService:
    def __init__(self, settings: SettingsRepository | None = None) -> None:
        self._settings = settings or SettingsRepository()

    def load(self) -> EmailConfig:
        get = self._settings.get
        provider = get(_PROVIDER_KEY, "gmail") or "gmail"
        preset_host, preset_port = PROVIDER_PRESETS.get(
            provider, PROVIDER_PRESETS["custom"]
        )
        return EmailConfig(
            provider=provider,
            host=get(_HOST_KEY, preset_host) or preset_host,
            port=_to_int(get(_PORT_KEY), preset_port),
            email=get(_ADDRESS_KEY),
            app_password=_deobfuscate(get(_PASSWORD_KEY)),
            folder=get(_FOLDER_KEY, "INBOX") or "INBOX",
            auto_enabled=get(_AUTO_KEY) == "1",
            poll_minutes=_to_int(get(_POLL_KEY), 15),
            last_uid=_to_int(get(_LAST_UID_KEY), 0),
            auth_mode=get(_AUTH_MODE_KEY, AUTH_PASSWORD) or AUTH_PASSWORD,
            oauth_client_id=get(_OAUTH_CLIENT_ID_KEY) or "",
            oauth_client_secret=_deobfuscate(get(_OAUTH_CLIENT_SECRET_KEY)),
            oauth_refresh_token=_deobfuscate(get(_OAUTH_REFRESH_KEY)),
        )

    def save(self, config: EmailConfig) -> None:
        s = self._settings.set
        s(_PROVIDER_KEY, config.provider.strip() or "gmail")
        s(_HOST_KEY, config.host.strip())
        s(_PORT_KEY, str(config.port))
        s(_ADDRESS_KEY, config.email.strip())
        s(_PASSWORD_KEY, _obfuscate(config.app_password))
        s(_FOLDER_KEY, config.folder.strip() or "INBOX")
        s(_AUTO_KEY, "1" if config.auto_enabled else "0")
        s(_POLL_KEY, str(max(1, config.poll_minutes)))
        s(_LAST_UID_KEY, str(max(0, config.last_uid)))
        s(_AUTH_MODE_KEY, config.auth_mode)
        s(_OAUTH_CLIENT_ID_KEY, config.oauth_client_id.strip())
        s(_OAUTH_CLIENT_SECRET_KEY, _obfuscate(config.oauth_client_secret.strip()))
        s(_OAUTH_REFRESH_KEY, _obfuscate(config.oauth_refresh_token.strip()))

    def set_last_uid(self, last_uid: int) -> None:
        """Ghi nhận UID cao nhất đã xử lý để lần sau chỉ lấy thư mới hơn."""
        self._settings.set(_LAST_UID_KEY, str(max(0, last_uid)))

    def set_oauth_refresh_token(self, refresh_token: str) -> None:
        """Lưu refresh token sau khi người dùng cấp quyền OAuth (obfuscate)."""
        self._settings.set(_OAUTH_REFRESH_KEY, _obfuscate(refresh_token.strip()))


def _to_int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default
