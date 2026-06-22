"""Entry point: Hung Phat Accounting Suite."""
from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.config import APP_NAME, ORG_NAME
from app.theme import apply_theme
from data.database import init_database
from data.repositories.account_repo import AccountRepository
from domain.services.account_service import AccountService
from ui.chrome.chrome_window import ChromeWindow


def _install_sigint_handler(app: QApplication) -> QTimer:
    """Quit the event loop cleanly when the process is interrupted.

    Stopping the app (PyCharm's Stop button, or Ctrl+C) sends SIGINT. Without a
    handler, Python raises ``KeyboardInterrupt`` inside whatever Qt event
    override happens to be running at that moment (e.g. ``mouseMoveEvent``),
    which Shiboken surfaces as a noisy "Error calling Python override". Asking
    Qt to quit instead lets ``app.exec()`` return normally.
    """
    signal.signal(signal.SIGINT, lambda _signum, _frame: app.quit())
    # Qt's C++ event loop otherwise starves Python of CPU time, so the pending
    # signal isn't delivered until some other Python callback runs. A periodic
    # no-op timer hands control back to the interpreter often enough to react.
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(200)
    return timer


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    apply_theme(app)
    init_database()
    AccountService(AccountRepository()).ensure_seeded()

    # Kept alive for the lifetime of app.exec() so SIGINT stays responsive.
    _sigint_timer = _install_sigint_handler(app)

    window = ChromeWindow()
    window.resize(1440, 900)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
