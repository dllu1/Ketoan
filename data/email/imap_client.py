"""Client IMAP: lấy email chứa hóa đơn điện tử (XML + PDF đính kèm).

Chỉ làm việc mạng — KHÔNG đụng tới database. Trả về các ``FetchedEmail`` đã bóc
attachment để tầng trên (InvoiceImportService) phân tích & ghi sổ trên main thread.
Mọi lỗi mạng/đăng nhập gói lại thành ``EmailFetchError`` với thông điệp tiếng Việt.
"""
from __future__ import annotations

import email
import imaplib
import io
import re
import ssl
import unicodedata
import zipfile
from collections.abc import Callable
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


def _utf7_decode(name: str) -> str:
    """Giải mã tên thư mục IMAP (modified UTF-7, RFC 3501) về Unicode.

    Gmail đặt tên thư mục theo ngôn ngữ tài khoản, nên hộp thư tiếng Việt trả về
    ``[Gmail]/Th&AbA- &AREA4w- g&HuU-i`` thay vì ``[Gmail]/Sent Mail``. Modified
    UTF-7 khác UTF-7 chuẩn ở chỗ dùng ``&`` thay ``+`` và ``,`` thay ``/``.
    """
    out: list[str] = []
    i = 0
    while i < len(name):
        char = name[i]
        if char != "&":
            out.append(char)
            i += 1
            continue
        end = name.find("-", i + 1)
        if end == -1:  # ``&`` lạc lõng không có dấu đóng → giữ nguyên
            out.append(name[i:])
            break
        chunk = name[i + 1 : end]
        if not chunk:  # "&-" là cách escape dấu & thật
            out.append("&")
        else:
            try:
                out.append(
                    ("+" + chunk.replace(",", "/") + "-").encode("ascii").decode("utf-7")
                )
            except (UnicodeDecodeError, UnicodeEncodeError):
                out.append(name[i : end + 1])  # không giải được → giữ nguyên
        i = end + 1
    return "".join(out)


def _utf7_encode(name: str) -> str:
    """Mã hoá tên thư mục Unicode về modified UTF-7 để gửi lên máy chủ IMAP."""
    out: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        encoded = "".join(buffer).encode("utf-7").decode("ascii")
        # utf-7 chuẩn: "+xxx-" (đôi khi không có "-" ở cuối) → đổi sang "&xxx-".
        out.append("&" + encoded[1:].rstrip("-").replace("/", ",") + "-")
        buffer.clear()

    for char in name:
        if char == "&":
            flush()
            out.append("&-")
        elif "\x20" <= char <= "\x7e":
            flush()
            out.append(char)
        else:
            buffer.append(char)
    flush()
    return "".join(out)


def _imap_folder(name: str) -> str:
    """Chuẩn hoá tên thư mục thành literal IMAP: modified UTF-7 + bọc nháy kép.

    imaplib KHÔNG tự trích dẫn tên thư mục, nên tên có dấu cách như
    ``[Gmail]/Sent Mail`` (thư Đã gửi — nơi chứa hóa đơn BÁN RA tự soạn gửi
    khách) sẽ khiến ``EXAMINE`` sai cú pháp. Gỡ nháy sẵn có (nếu người dùng tự
    gõ) rồi bọc lại + escape ``\\`` và ``"`` để mọi tên đều hợp lệ.
    """
    stripped = _utf7_encode(name.strip().strip('"'))
    escaped = stripped.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# Thư mục "đã gửi" theo cờ special-use và theo tên ở các ngôn ngữ hay gặp.
_SENT_ALIASES = {
    "sent", "sent mail", "sent items", "sent messages",
    "thu da gui", "da gui", "thu di", "gui di",
}


def _fold_ascii(text: str) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường để so khớp tên thư mục dễ dãi hơn."""
    decomposed = unicodedata.normalize("NFD", text.strip().strip('"').lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.replace("đ", "d")


@dataclass
class MailFolder:
    name: str  # tên đã giải mã, hiển thị được cho người dùng
    flags: str = ""  # vd "\\HasNoChildren \\Sent"

    @property
    def is_sent(self) -> bool:
        return "\\sent" in self.flags.lower()


def _parse_list_line(line: bytes | str) -> MailFolder:
    """Bóc cờ + tên thư mục từ 1 dòng trả về của lệnh ``LIST``.

    Dạng dòng: ``(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"`` — tên nằm ở
    cuối, có thể bọc nháy (khi chứa dấu cách) hoặc không.
    """
    text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
    text = text.strip()
    flags = ""
    if text.startswith("("):
        close = text.find(")")
        if close != -1:
            flags = text[1:close]
    if text.endswith('"'):
        start = text.rfind('"', 0, len(text) - 1)
        if start != -1:
            raw = text[start + 1 : -1].replace('\\"', '"').replace("\\\\", "\\")
            return MailFolder(_utf7_decode(raw), flags)
    return MailFolder(_utf7_decode(text.rsplit(" ", 1)[-1]), flags)


def _match_folder(wanted: str, available: list[MailFolder]) -> str | None:
    """Tìm thư mục thật khớp tên người dùng nhập (bỏ qua hoa thường & dấu).

    Người dùng hay gõ ``Sent Mail`` hoặc ``Thư đã gửi`` trong khi máy chủ đặt tên
    khác hẳn (Gmail tiếng Việt: ``[Gmail]/Thư đã gửi``) → thử lần lượt: khớp
    nguyên tên, khớp đoạn cuối sau dấu phân cách, khớp cờ ``\\Sent`` khi tên nhập
    mang nghĩa "đã gửi", cuối cùng mới khớp chuỗi con.
    """
    target = _fold_ascii(wanted)
    if not target:
        return None
    # Đoạn cuối: "[Gmail]/Sent Mail" → "sent mail" (bỏ tiền tố namespace).
    leaf = target.rsplit("/", 1)[-1]
    for folder in available:
        if _fold_ascii(folder.name) == target:
            return folder.name
    for folder in available:
        if _fold_ascii(folder.name).rsplit("/", 1)[-1] == leaf:
            return folder.name
    if leaf in _SENT_ALIASES:
        for folder in available:
            if folder.is_sent:
                return folder.name
    for folder in available:
        if target in _fold_ascii(folder.name):
            return folder.name
    return None


def _list_folders(conn: imaplib.IMAP4_SSL) -> list[MailFolder]:
    try:
        status, data = conn.list()
    except imaplib.IMAP4.error:
        return []
    if status != "OK" or not data:
        return []
    return [_parse_list_line(line) for line in data if line]


def list_folders(config: EmailConfig) -> list[MailFolder]:
    """Liệt kê thư mục có thật trên hộp thư (để UI cho người dùng chọn)."""
    conn = _connect(config)
    try:
        return _list_folders(conn)
    finally:
        _safe_logout(conn)


def _select_folder(conn: imaplib.IMAP4_SSL, folder: str) -> None:
    """Mở thư mục ở chế độ chỉ đọc; tự dò tên đúng nếu tên nhập không khớp."""
    try:
        status, _ = conn.select(_imap_folder(folder), readonly=True)
    except imaplib.IMAP4.error:
        status = "NO"
    if status == "OK":
        return

    available = _list_folders(conn)
    resolved = _match_folder(folder, available)
    if resolved and resolved != folder:
        try:
            status, _ = conn.select(_imap_folder(resolved), readonly=True)
        except imaplib.IMAP4.error:
            status = "NO"
        if status == "OK":
            return

    listing = "\n".join(f"  • {f.name}" for f in available)
    raise EmailFetchError(
        f"Không mở được thư mục '{folder}'.\n"
        "Vào Hệ thống → Cài đặt → Email, bấm “Chọn thư mục…” rồi chọn đúng tên.\n"
        + (f"Các thư mục hiện có:\n{listing}" if listing else "")
    )


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
        _select_folder(conn, config.folder)
    finally:
        _safe_logout(conn)


def _looks_like_invoice(structure: str) -> bool:
    """Đoán từ BODYSTRUCTURE xem thư có đính kèm XML/ZIP đáng tải về không.

    Chỉ đọc cấu trúc thư (vài trăm byte) thay vì tải cả email (thường vài MB vì
    PDF + ảnh chữ ký) → bỏ qua sớm phần lớn thư thường. Nguyên tắc an toàn: chỉ
    loại khi CHẮC CHẮN không có; tên file mã hoá (RFC 2047 ``=?..?=`` hoặc RFC
    2231 ``name*0*``) thì vẫn tải vì không đọc được đuôi file.
    """
    lowered = structure.lower()
    if ".xml" in lowered or ".zip" in lowered:
        return True
    if "=?" in structure or "*0*" in lowered or "*1*" in lowered:
        return True  # tên file mã hoá → không dám kết luận
    return False


def _candidate_uids(conn: imaplib.IMAP4_SSL, uids: list[int]) -> list[int]:
    """Lọc trước danh sách UID bằng MỘT lệnh FETCH BODYSTRUCTURE duy nhất.

    Lỗi/không đọc được → trả nguyên danh sách (thà tải thừa còn hơn sót hóa đơn).
    """
    if not uids:
        return []
    try:
        status, data = conn.uid(
            "fetch", ",".join(str(u) for u in uids), "(BODYSTRUCTURE)"
        )
    except imaplib.IMAP4.error:
        return uids
    if status != "OK" or not data:
        return uids

    # Gom mọi mảnh phản hồi về đúng UID của nó. Máy chủ có thể trả cấu trúc dưới
    # dạng literal — imaplib khi đó đưa về tuple (tiền tố, nội dung) và phần tên
    # file nằm ở mảnh SAU; đọc thiếu mảnh này sẽ loại nhầm thư có hóa đơn.
    chunks: dict[int, list[str]] = {}
    current: int | None = None
    for raw in data:
        parts = raw if isinstance(raw, tuple) else (raw,)
        for part in parts:
            if not isinstance(part, (bytes, bytearray)):
                continue
            text = bytes(part).decode("utf-8", errors="replace")
            match = re.search(r"UID (\d+)", text)
            if match is not None:
                current = int(match.group(1))
                chunks.setdefault(current, [])
            if current is not None:
                chunks[current].append(text)

    keep = [
        uid for uid, pieces in chunks.items() if _looks_like_invoice("".join(pieces))
    ]
    # UID nào máy chủ không trả cấu trúc → giữ lại để tải đầy đủ cho chắc.
    keep.extend(u for u in uids if u not in chunks)
    return sorted(set(keep))


def fetch_invoice_messages(
    config: EmailConfig,
    since_uid: int = 0,
    progress: Callable[[int, int], None] | None = None,
) -> list[FetchedEmail]:
    """Lấy các email (UID > since_uid) có đính kèm XML hóa đơn, kèm PDF nếu có.

    ``progress(done, total)`` được gọi sau mỗi thư tải xong (nếu truyền vào) để
    UI hiện tiến độ thay vì đứng hình.
    """
    conn = _connect(config)
    try:
        _select_folder(conn, config.folder)

        # Chỉ lấy thư mới hơn UID đã xử lý lần trước (1 = từ đầu hộp thư).
        criteria = f"UID {since_uid + 1}:*"
        status, data = conn.uid("search", None, criteria)
        if status != "OK" or not data or not data[0]:
            return []

        # search "N:*" luôn trả ít nhất 1 UID kể cả khi không có thư mới hơn.
        uids = [u for u in (int(r) for r in data[0].split()) if u > since_uid]
        uids = _candidate_uids(conn, uids)

        results: list[FetchedEmail] = []
        total = len(uids)
        for done, uid in enumerate(uids, start=1):
            fetched = _fetch_one(conn, uid)
            if fetched is not None and fetched.xml_bytes is not None:
                results.append(fetched)
            if progress is not None:
                progress(done, total)
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
