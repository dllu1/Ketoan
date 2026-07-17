"""OAuth2 (XOAUTH2) cho IMAP Gmail/Google Workspace.

Không cần App Password: người dùng cấp quyền MỘT LẦN qua trình duyệt (consent
flow chạy server loopback tạm trên localhost) → nhận *refresh token* lưu vào
``settings``. Mỗi lần lấy thư, đổi refresh token sang *access token* ngắn hạn để
đăng nhập IMAP theo cơ chế XOAUTH2.

Chỉ làm việc mạng/xác thực — KHÔNG đụng database. Mọi lỗi gói lại thành
``OAuthError`` với thông điệp tiếng Việt.

Scope bắt buộc cho IMAP đầy đủ: ``https://mail.google.com/`` (readonly KHÔNG đủ
để đăng nhập IMAP).
"""
from __future__ import annotations

# IMAP XOAUTH2 yêu cầu scope mail đầy đủ; các scope gmail.readonly/metadata
# không cho phép đăng nhập IMAP.
GMAIL_IMAP_SCOPE = "https://mail.google.com/"
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"


class OAuthError(Exception):
    """Lỗi khi cấp quyền hoặc làm mới access token."""


def _client_config(client_id: str, client_secret: str) -> dict:
    """Cấu hình client kiểu 'Desktop app' cho InstalledAppFlow (không cần file JSON)."""
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": _AUTH_URI,
            "token_uri": _TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }


def run_consent_flow(client_id: str, client_secret: str) -> str:
    """Mở trình duyệt để người dùng đăng nhập & cấp quyền. Trả về *refresh token*.

    Chạy server loopback tạm trên localhost nhận authorization code, nên PHẢI gọi
    trên máy có trình duyệt (không chạy được trong shell headless của agent).
    """
    if not client_id or not client_secret:
        raise OAuthError("Thiếu Client ID hoặc Client Secret.")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise OAuthError(
            "Chưa cài thư viện google-auth-oauthlib.\n"
            "Chạy: pip install google-auth-oauthlib"
        ) from exc

    flow = InstalledAppFlow.from_client_config(
        _client_config(client_id, client_secret),
        scopes=[GMAIL_IMAP_SCOPE],
    )
    try:
        # access_type=offline + prompt=consent → Google luôn trả refresh token,
        # kể cả khi tài khoản đã từng cấp quyền trước đó.
        flow.run_local_server(
            port=0,
            open_browser=True,
            access_type="offline",
            prompt="consent",
            authorization_prompt_message="",
            success_message=(
                "Đã cấp quyền. Bạn có thể đóng tab này và quay lại ứng dụng."
            ),
        )
    except Exception as exc:  # noqa: BLE001 — gói mọi lỗi mạng/hủy vào OAuthError
        raise OAuthError(f"Cấp quyền thất bại hoặc bị hủy.\n{exc}") from exc

    refresh_token = getattr(flow.credentials, "refresh_token", None)
    if not refresh_token:
        raise OAuthError(
            "Không nhận được refresh token. Hãy thu hồi quyền cũ tại "
            "myaccount.google.com/permissions rồi đăng nhập lại."
        )
    return refresh_token


def get_access_token(
    client_id: str, client_secret: str, refresh_token: str
) -> str:
    """Đổi refresh token → access token ngắn hạn để đăng nhập IMAP XOAUTH2."""
    if not (client_id and client_secret and refresh_token):
        raise OAuthError("Thiếu thông tin OAuth (client id / secret / refresh token).")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise OAuthError(
            "Chưa cài thư viện google-auth.\nChạy: pip install google-auth"
        ) from exc

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri=_TOKEN_URI,
        scopes=[GMAIL_IMAP_SCOPE],
    )
    try:
        creds.refresh(Request())
    except Exception as exc:  # noqa: BLE001 — token hỏng/hết hạn → cần cấp quyền lại
        raise OAuthError(
            "Không làm mới được access token. Có thể cần cấp quyền lại "
            "(Client Secret sai, quyền đã bị thu hồi, hoặc IMAP bị chặn).\n"
            f"{exc}"
        ) from exc
    return creds.token


def build_xoauth2_bytes(email: str, access_token: str) -> bytes:
    """Chuỗi SASL XOAUTH2 (raw) cho imaplib.authenticate — imaplib tự base64."""
    return f"user={email}\x01auth=Bearer {access_token}\x01\x01".encode("utf-8")
