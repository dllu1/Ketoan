"""Tests cho imap_client: bọc nháy tên thư mục + giải nén XML/PDF trong ZIP.

Không chạm mạng: dùng ZIP/email dựng trong bộ nhớ và một kết nối IMAP giả lập.
"""
from __future__ import annotations

import io
import zipfile
from email.message import EmailMessage

from data.email.imap_client import (
    FetchedEmail,
    _absorb_zip,
    _fetch_one,
    _imap_folder,
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
