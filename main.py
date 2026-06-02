"""Entry point: Hung Phat Accounting Suite."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.config import APP_NAME, ORG_NAME
from app.theme import apply_theme
from data.database import init_database
from data.repositories.account_repo import AccountRepository
from domain.services.account_service import AccountService
from ui.chrome.chrome_window import ChromeWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    apply_theme(app)
    init_database()
    AccountService(AccountRepository()).ensure_seeded()

    window = ChromeWindow()
    window.resize(1440, 900)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
