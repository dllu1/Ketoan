"""Tests cho EmailConfigService — lưu/nạp cấu hình, chuẩn hoá, và reset mốc UID.

``set_last_uid(0)`` là lõi của nút "Quét lại từ đầu" ở màn hình Cấu hình.
"""
from __future__ import annotations

import pytest

from domain.services.email_config_service import (
    AUTH_OAUTH,
    EmailConfig,
    EmailConfigService,
)


@pytest.fixture
def config_service(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("data.database.DB_PATH", db_file)

    import data.database as db_mod
    from data.repositories.settings_repo import SettingsRepository

    db_mod._conn = None
    db_mod.init_database()
    yield EmailConfigService(SettingsRepository(db_mod.get_connection()))
    db_mod.close_connection()


def test_rescan_resets_last_uid_to_zero(config_service):
    # Người dùng đã quét trước đó (mốc = 500), rồi bấm "Quét lại từ đầu".
    config_service.save(EmailConfig(email="me@gmail.com", app_password="x", last_uid=500))
    assert config_service.load().last_uid == 500

    config_service.set_last_uid(0)   # nút "Quét lại từ đầu"

    assert config_service.load().last_uid == 0


def test_set_last_uid_never_negative(config_service):
    config_service.set_last_uid(-5)
    assert config_service.load().last_uid == 0


def test_save_load_roundtrip_sent_folder(config_service):
    # Thư mục hóa đơn bán ra có dấu cách phải lưu/nạp nguyên vẹn.
    config_service.save(EmailConfig(
        email="me@gmail.com", app_password="pw", folder="[Gmail]/Sent Mail",
    ))
    loaded = config_service.load()
    assert loaded.folder == "[Gmail]/Sent Mail"


def test_app_password_whitespace_stripped(config_service):
    # Google hiển thị App Password dạng "abcd efgh ijkl mnop"; phải gỡ khoảng trắng.
    config_service.save(EmailConfig(email="me@gmail.com", app_password="abcd efgh ijkl mnop"))
    assert config_service.load().app_password == "abcdefghijklmnop"


def test_oauth_secrets_roundtrip_and_readiness(config_service):
    config_service.save(EmailConfig(
        email="me@gmail.com", auth_mode=AUTH_OAUTH,
        oauth_client_id="cid", oauth_client_secret="secret",
        oauth_refresh_token="refresh",
    ))
    loaded = config_service.load()
    assert loaded.is_oauth is True
    assert loaded.oauth_client_secret == "secret"
    assert loaded.oauth_refresh_token == "refresh"
    assert loaded.is_ready is True
