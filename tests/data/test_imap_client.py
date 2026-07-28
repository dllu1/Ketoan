"""Tests cho imap_client: bọc nháy tên thư mục + giải nén XML/PDF trong ZIP.

Không chạm mạng: dùng ZIP/email dựng trong bộ nhớ và một kết nối IMAP giả lập.
"""
from __future__ import annotations

import io
import zipfile
from email.message import EmailMessage

import pytest

from data.email.imap_client import (
    EmailFetchError,
    FetchedEmail,
    MailFolder,
    _absorb_zip,
    _candidate_uids,
    _fetch_one,
    _looks_like_invoice,
    _imap_folder,
    _match_folder,
    _parse_list_line,
    _select_folder,
    _utf7_decode,
    _utf7_encode,
)


# ----- _imap_folder: bọc nháy kép cho tên thư mục có dấu cách -----------------

def test_imap_folder_quotes_plain_name():
    assert _imap_folder("INBOX") == '"INBOX"'


def test_imap_folder_quotes_name_with_space():
    # [Gmail]/Sent Mail có dấu cách → phải bọc nháy, nếu không EXAMINE sai cú pháp.
    assert _imap_folder("[Gmail]/Sent Mail") == '"[Gmail]/Sent Mail"'


def test_imap_folder_strips_existing_quotes_and_whitespace():
    assert _imap_folder('  "[Gmail]/Sent Mail"  ') == '"[Gmail]/Sent Mail"'


def test_imap_folder_escapes_embedded_quote_and_backslash():
    assert _imap_folder('a"b\\c') == '"a\\"b\\\\c"'


# ----- dò tên thư mục thật khi tên người dùng nhập không khớp ----------------

# Gmail tiếng Việt trả về tên thư mục mã hóa modified UTF-7.
_VN_SENT_RAW = "[Gmail]/Th&AbA- &AREA4w- g&Hu0-i"
_VN_SENT = "[Gmail]/Thư đã gửi"


def test_utf7_decode_vietnamese_gmail_folder():
    assert _utf7_decode(_VN_SENT_RAW) == _VN_SENT


def test_utf7_roundtrip_keeps_ascii_untouched():
    assert _utf7_encode("[Gmail]/Sent Mail") == "[Gmail]/Sent Mail"
    assert _utf7_decode(_utf7_encode(_VN_SENT)) == _VN_SENT


def test_imap_folder_encodes_vietnamese_name():
    # imaplib chỉ gửi được ASCII → tên tiếng Việt phải thành modified UTF-7.
    quoted = _imap_folder(_VN_SENT)
    assert quoted.strip('"').isascii()
    assert _utf7_decode(quoted.strip('"')) == _VN_SENT


def test_parse_list_line_reads_quoted_name_and_flags():
    line = b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"'
    folder = _parse_list_line(line)
    assert folder.name == "[Gmail]/Sent Mail"
    assert folder.is_sent


def test_parse_list_line_decodes_vietnamese_name():
    line = f'(\\HasNoChildren \\Sent) "/" "{_VN_SENT_RAW}"'.encode()
    assert _parse_list_line(line).name == _VN_SENT


def test_parse_list_line_reads_unquoted_name():
    folder = _parse_list_line(b'(\\HasNoChildren) "/" INBOX')
    assert folder.name == "INBOX"
    assert not folder.is_sent


def _folders(*names: str) -> list[MailFolder]:
    return [
        MailFolder(n, "\\HasNoChildren \\Sent" if "gửi" in n or "Sent" in n else "")
        for n in names
    ]


def test_match_folder_prefers_exact_case_insensitive():
    assert _match_folder("inbox", _folders("INBOX", _VN_SENT)) == "INBOX"


def test_match_folder_matches_vietnamese_name_without_accents():
    assert _match_folder("Thu da gui", _folders("INBOX", _VN_SENT)) == _VN_SENT


def test_match_folder_uses_sent_flag_for_english_alias():
    # Người dùng gõ "Sent Mail" nhưng hộp thư tiếng Việt đặt tên khác hẳn.
    assert _match_folder("Sent Mail", _folders("INBOX", _VN_SENT)) == _VN_SENT


def test_match_folder_returns_none_when_nothing_similar():
    assert _match_folder("Hoa don", _folders("INBOX", _VN_SENT)) is None


class _FakeSelectConn:
    """Giả lập IMAP4_SSL: chỉ chấp nhận SELECT đúng các thư mục có thật."""

    def __init__(self, folders: list[str], sent: str = "") -> None:
        self._folders = folders
        self._sent = sent  # thư mục mang cờ \Sent (nếu có)
        self.selected: str | None = None

    def select(self, mailbox, readonly=False):
        assert mailbox.isascii(), "imaplib chỉ gửi được ASCII"
        name = mailbox.strip('"')
        if name in self._folders:
            self.selected = name
            return "OK", [b"1"]
        return "NO", [b"[NONEXISTENT] Unknown Mailbox"]

    def list(self, *args):
        data = []
        for f in self._folders:
            flags = "\\HasNoChildren \\Sent" if f == self._sent else "\\HasNoChildren"
            data.append(f'({flags}) "/" "{f}"'.encode())
        return "OK", data


def test_select_folder_falls_back_to_vietnamese_sent_folder():
    # Cấu hình cũ ghi "[Gmail]/Sent Mail" nhưng hộp thư tiếng Việt tên khác →
    # phải nhận ra qua cờ \Sent.
    conn = _FakeSelectConn(["INBOX", _VN_SENT_RAW], sent=_VN_SENT_RAW)
    _select_folder(conn, "[Gmail]/Sent Mail")
    assert conn.selected == _VN_SENT_RAW


def test_select_folder_error_lists_available_folders_decoded():
    conn = _FakeSelectConn(["INBOX", _VN_SENT_RAW])
    with pytest.raises(EmailFetchError) as exc:
        _select_folder(conn, "Hoa don")
    message = str(exc.value)
    assert "Hoa don" in message
    assert _VN_SENT in message  # hiển thị tên đọc được, không phải UTF-7


# ----- _absorb_zip: bóc file .xml/.pdf đầu tiên trong ZIP ---------------------

def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buf.getvalue()


def test_absorb_zip_extracts_xml_and_pdf():
    fetched = FetchedEmail(uid=1, message_id="m", subject="s")
    _absorb_zip(
        _zip_bytes({"HD_0001.xml": b"<HDon>x</HDon>", "HD_0001.pdf": b"%PDF-1.4"}),
        fetched,
    )
    assert fetched.xml_bytes == b"<HDon>x</HDon>"
    assert fetched.pdf_bytes == b"%PDF-1.4"
    assert fetched.pdf_filename == "hd_0001.pdf"


def test_absorb_zip_reads_file_in_subfolder():
    fetched = FetchedEmail(uid=1, message_id="m", subject="s")
    _absorb_zip(_zip_bytes({"folder/inv.xml": b"<HDon>nested</HDon>"}), fetched)
    assert fetched.xml_bytes == b"<HDon>nested</HDon>"


def test_absorb_zip_ignores_corrupt_archive():
    fetched = FetchedEmail(uid=1, message_id="m", subject="s")
    _absorb_zip(b"this is not a zip", fetched)  # không được raise
    assert fetched.xml_bytes is None
    assert fetched.pdf_bytes is None


def test_absorb_zip_does_not_overwrite_existing_xml():
    # File lấy trực tiếp từ email được ưu tiên; ZIP chỉ điền field còn trống.
    fetched = FetchedEmail(uid=1, message_id="m", subject="s", xml_bytes=b"<direct/>")
    _absorb_zip(_zip_bytes({"other.xml": b"<from_zip/>"}), fetched)
    assert fetched.xml_bytes == b"<direct/>"


def test_absorb_zip_takes_first_xml_only():
    fetched = FetchedEmail(uid=1, message_id="m", subject="s")
    _absorb_zip(_zip_bytes({"a.xml": b"<first/>", "b.xml": b"<second/>"}), fetched)
    assert fetched.xml_bytes == b"<first/>"


# ----- lọc trước bằng BODYSTRUCTURE (tránh tải cả hộp thư) -------------------

def test_looks_like_invoice_accepts_xml_and_zip():
    assert _looks_like_invoice('("application" "xml" ("NAME" "HD_001.xml")')
    assert _looks_like_invoice('("application" "zip" ("NAME" "hoadon.ZIP")')


def test_looks_like_invoice_rejects_plain_and_pdf_only_mail():
    assert not _looks_like_invoice('("text" "plain" ("CHARSET" "utf-8") NIL')
    assert not _looks_like_invoice('("application" "pdf" ("NAME" "bao gia.pdf")')


def test_looks_like_invoice_keeps_encoded_filenames():
    # Tên file mã hóa RFC 2047/2231 → không đọc được đuôi, phải tải để chắc chắn.
    assert _looks_like_invoice('("NAME" "=?utf-8?B?SEQwMDEueG1s?=")')
    assert _looks_like_invoice('("NAME*0*" "utf-8\'\'%48%44")')


class _FakeStructureConn:
    """Giả lập UID FETCH BODYSTRUCTURE: trả cấu trúc theo từng UID."""

    def __init__(self, structures: dict[int, str], status: str = "OK") -> None:
        self._structures = structures
        self._status = status
        self.fetch_calls = 0

    def uid(self, command, *args):
        assert command == "fetch"
        self.fetch_calls += 1
        data = [
            f"{i} (UID {uid} BODYSTRUCTURE {struct})".encode()
            for i, (uid, struct) in enumerate(self._structures.items(), start=1)
        ]
        return self._status, data


def test_candidate_uids_drops_mail_without_xml_in_one_roundtrip():
    conn = _FakeStructureConn({
        1: '("text" "plain" NIL)',
        2: '("application" "xml" ("NAME" "HD_002.xml"))',
        3: '("application" "pdf" ("NAME" "don dat hang.pdf"))',
    })
    assert _candidate_uids(conn, [1, 2, 3]) == [2]
    assert conn.fetch_calls == 1  # một lệnh cho cả lô, không phải mỗi thư một lệnh


def test_candidate_uids_keeps_uid_missing_from_response():
    # Máy chủ không trả cấu trúc cho UID 9 → giữ lại, thà tải thừa còn hơn sót.
    conn = _FakeStructureConn({1: '("application" "xml" ("NAME" "a.xml"))'})
    assert _candidate_uids(conn, [1, 9]) == [1, 9]


class _FakeLiteralConn:
    """Máy chủ trả BODYSTRUCTURE dạng literal → imaplib đưa về tuple nhiều mảnh."""

    def uid(self, command, *args):
        assert command == "fetch"
        return "OK", [
            (b'1 (UID 7 BODYSTRUCTURE ("application" "octet-stream" ("NAME" {10}',
             b"HD_007.xml"),
            b'))',
            (b'2 (UID 8 BODYSTRUCTURE ("application" "pdf" ("NAME" {9}',
             b"bao_gia.pdf"),
            b'))',
        ]


def test_candidate_uids_reads_filename_from_literal_chunk():
    # Tên file nằm ở mảnh SAU của tuple; đọc thiếu sẽ loại nhầm thư có hóa đơn.
    assert _candidate_uids(_FakeLiteralConn(), [7, 8]) == [7]


def test_candidate_uids_falls_back_when_server_refuses():
    conn = _FakeStructureConn({1: '("text" "plain" NIL)'}, status="NO")
    assert _candidate_uids(conn, [1, 2]) == [1, 2]


# ----- _fetch_one: đọc email có ZIP đính kèm qua kết nối IMAP giả -------------

class _FakeConn:
    """Giả lập IMAP4_SSL.uid('fetch', ...) trả về một email RFC822 dựng sẵn."""

    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def uid(self, command, *args):
        assert command == "fetch"
        return "OK", [(b"1 (RFC822 {%d}" % len(self._raw), self._raw)]


def _email_with_zip_attachment(zip_bytes: bytes) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = "HD test"
    msg["Message-ID"] = "<abc@local>"
    msg.set_content("noi dung")
    msg.add_attachment(
        zip_bytes, maintype="application", subtype="zip", filename="hoadon.zip"
    )
    return msg.as_bytes()


def test_fetch_one_extracts_xml_from_zip_attachment():
    raw = _email_with_zip_attachment(_zip_bytes({"hd.xml": b"<HDon>real</HDon>"}))
    fetched = _fetch_one(_FakeConn(raw), uid=1)
    assert fetched is not None
    assert fetched.subject == "HD test"
    assert fetched.xml_bytes == b"<HDon>real</HDon>"
