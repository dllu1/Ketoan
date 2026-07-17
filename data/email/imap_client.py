"""Client IMAP: lấy email chứa hóa đơn điện tử (XML + PDF đính kèm).

Chỉ làm việc mạng — KHÔNG đụng tới database. Trả về các ``FetchedEmail`` đã bóc
attachment để tầng trên (InvoiceImportService) phân tích & ghi sổ trên main thread.
Mọi lỗi mạng/đăng nhập gói lại thành ``EmailFetchError`` với thông điệp tiếng Việt.
"""
from __future__ import annotations

import email
import imaplib
import io
import ssl
import zipfile
from dataclasses import dataclass
from email.header import decode_header
from email.message import Message

from domain.services.email_config_service import EmailConfig


class EmailFetchError(Exception):
    """Không kết nối / đăng nhập / đọc được hộp thư."""


@dataclass
class FetchedEmail:
    uid: int
    message_id: str
    subject: str
    xml_bytes: bytes | None = None
    pdf_bytes: bytes | None = None
    pdf_filename: str = ""


def _imap_folder(name: str) -> str:
    """Bọc tên thư mục IMAP trong nháy kép.

    imaplib KHÔNG tự trích dẫn tên thư mục, nên tên có dấu cách như
    ``[Gmail]/Sent Mail`` (thư Đã gửi — nơi chứa hóa đơn BÁN RA tự soạn gửi
    khách) sẽ khiến ``EXAMINE`` sai cú pháp. Gỡ nháy sẵn có (nếu người dùng tự
    gõ) rồi bọc lại + escape ``\\`` và ``"`` để mọi tên đều hợp lệ.
    """
    stripped = name.strip().strip('"')
    escaped = stripped.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _decode_str(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for text, charset in decode_header(value):
        if isinstance(text, bytes):
            parts.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(text)
    return "".join(parts)


def _connect(config: EmailConfig) -> imaplib.IMAP4_SSL:
    try:
        conn = imaplib.IMAP4_SSL(
            config.host, config.port, ssl_context=ssl.create_default_context()
        )
    except (OSError, ssl.SSLError) as exc:
        raise EmailFetchError(
            f"Không kết nối được tới máy chủ {config.host}:{config.port}.\n{exc}"
        ) from exc
    try:
        if config.is_oauth:
            _login_oauth(conn, config)
        else:
            conn.login(config.email, config.app_password)
    except imaplib.IMAP4.error as exc:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001 — best effort khi đóng
            pass
        hint = (
            "Kiểm tra quyền OAuth (thử 'Đăng nhập Google' lại) và IMAP đã bật."
            if config.is_oauth
            else "Kiểm tra địa chỉ và App Password."
        )
        raise EmailFetchError(f"Đăng nhập email thất bại. {hint}\n{exc}") from exc
    except EmailFetchError:
        # Lỗi lấy access token (đã gói sẵn thông điệp) → đóng kết nối rồi ném tiếp.
        try:
            conn.logout()
        except Exception:  # noqa: BLE001 — best effort khi đóng
            pass
        raise
    return conn


def _login_oauth(conn: imaplib.IMAP4_SSL, config: EmailConfig) -> None:
    """Đăng nhập IMAP bằng XOAUTH2: đổi refresh token → access token rồi auth."""
    from data.email.oauth import (
        OAuthError,
        build_xoauth2_bytes,
        get_access_token,
    )

    try:
        access_token = get_access_token(
            config.oauth_client_id,
            config.oauth_client_secret,
            config.oauth_refresh_token,
        )
    except OAuthError as exc:
        # Gói về EmailFetchError để tầng trên hiển thị thống nhất.
        raise EmailFetchError(str(exc)) from exc
    auth_bytes = build_xoauth2_bytes(config.email, access_token)
    conn.authenticate("XOAUTH2", lambda _challenge: auth_bytes)


def test_connection(config: EmailConfig) -> None:
    """Thử kết nối + đăng nhập + chọn thư mục. Raise EmailFetchError nếu lỗi."""
    conn = _connect(config)
    try:
        status, _ = conn.select(_imap_folder(config.folder), readonly=True)
        if status != "OK":
            raise EmailFetchError(f"Không mở được thư mục '{config.folder}'.")
    finally:
        _safe_logout(conn)


def fetch_invoice_messages(
    config: EmailConfig, since_uid: int = 0
) -> list[FetchedEmail]:
    """Lấy các email (UID > since_uid) có đính kèm XML hóa đơn, kèm PDF nếu có."""
    conn = _connect(config)
    try:
        status, _ = conn.select(_imap_folder(config.folder), readonly=True)
        if status != "OK":
            raise EmailFetchError(f"Không mở được thư mục '{config.folder}'.")

        # Chỉ lấy thư mới hơn UID đã xử lý lần trước (1 = từ đầu hộp thư).
        criteria = f"UID {since_uid + 1}:*"
        status, data = conn.uid("search", None, criteria)
        if status != "OK" or not data or not data[0]:
            return []

        results: list[FetchedEmail] = []
        for raw_uid in data[0].split():
            uid = int(raw_uid)
            # search "N:*" luôn trả ít nhất 1 UID kể cả khi không có thư mới hơn.
            if uid <= since_uid:
                continue
            fetched = _fetch_one(conn, uid)
            if fetched is not None and fetched.xml_bytes is not None:
                results.append(fetched)
        results.sort(key=lambda f: f.uid)
        return results
    except imaplib.IMAP4.error as exc:
        raise EmailFetchError(f"Lỗi khi đọc hộp thư.\n{exc}") from exc
    finally:
        _safe_logout(conn)


def _fetch_one(conn: imaplib.IMAP4_SSL, uid: int) -> FetchedEmail | None:
    status, data = conn.uid("fetch", str(uid), "(RFC822)")
    if status != "OK" or not data or not isinstance(data[0], tuple):
        return None
    message: Message = email.message_from_bytes(data[0][1])
    fetched = FetchedEmail(
        uid=uid,
        message_id=_decode_str(message.get("Message-ID")),
        subject=_decode_str(message.get("Subject")),
    )
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = _decode_str(part.get_filename())
        if not filename:
            continue
        lower = filename.lower()
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        if lower.endswith(".xml") and fetched.xml_bytes is None:
            fetched.xml_bytes = payload
        elif lower.endswith(".pdf") and fetched.pdf_bytes is None:
            fetched.pdf_bytes = payload
            fetched.pdf_filename = filename
        elif lower.endswith(".zip"):
            # Nhiều nhà cung cấp HĐĐT nén XML (+PDF) trong 1 file .zip.
            _absorb_zip(payload, fetched)
    return fetched


def _absorb_zip(payload: bytes, fetched: FetchedEmail) -> None:
    """Bóc file .xml/.pdf đầu tiên bên trong ZIP vào ``fetched`` (nếu còn trống).

    Bỏ qua ZIP hỏng/không đọc được — coi như không có đính kèm. Chỉ điền field
    còn thiếu để không đè lên file đã lấy trực tiếp từ email.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        return
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            lower = name.rsplit("/", 1)[-1].lower()
            if lower.endswith(".xml") and fetched.xml_bytes is None:
                try:
                    fetched.xml_bytes = archive.read(info)
                except (zipfile.BadZipFile, OSError):
                    continue
            elif lower.endswith(".pdf") and fetched.pdf_bytes is None:
                try:
                    fetched.pdf_bytes = archive.read(info)
                    fetched.pdf_filename = lower
                except (zipfile.BadZipFile, OSError):
                    continue


def _safe_logout(conn: imaplib.IMAP4_SSL) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001 — thư mục có thể chưa mở
        pass
    try:
        conn.logout()
    except Exception:  # noqa: BLE001 — best effort
        pass
