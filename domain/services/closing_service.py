"""Year-end book closing (chốt sổ cuối năm).

While a fiscal year is open the user may freely create / edit / delete any
document dated in it. Closing the year — manually, or automatically 48h after
it ends if the user never did — locks every document of that year.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from data.repositories.closing_repo import ClosingRepository

# Grace period after 31/12 before a still-open year is closed automatically.
AUTO_CLOSE_GRACE = timedelta(hours=48)

# Only look this far back when scanning for years to close / remind about.
# Two years covers "the year just ended" even if the app wasn't opened for a
# while, without sweeping in a decade of empty historical years on first run.
_SCAN_YEARS = 2


class ClosingError(Exception):
    """Raised when an operation targets a fiscal year that is already closed."""


class ClosingService:
    def __init__(self, repo: ClosingRepository | None = None) -> None:
        self._repo = repo or ClosingRepository()

    # ----- queries ---------------------------------------------------------

    def is_closed(self, year: int) -> bool:
        return self._repo.is_closed(year)

    def closed_years(self) -> set[int]:
        return self._repo.closed_years()

    def is_locked(self, when: date) -> bool:
        return self._repo.is_closed(when.year)

    def ensure_open(self, when: date) -> None:
        """Guard for create / edit / delete; raises if the year is closed."""
        if self._repo.is_closed(when.year):
            raise ClosingError(
                f"Năm {when.year} đã chốt sổ — không thể thêm, sửa hoặc xóa "
                "chứng từ của năm này."
            )

    # ----- commands --------------------------------------------------------

    def close_year(self, year: int, *, auto: bool = False) -> None:
        self._repo.close(year, auto=auto)

    def reopen_year(self, year: int) -> None:
        self._repo.reopen(year)

    # ----- year-end automation --------------------------------------------

    def closable_years(self, today: date | None = None) -> list[int]:
        """Fully-ended years (strictly before this year) not yet closed."""
        today = today or date.today()
        return [
            y for y in range(today.year - _SCAN_YEARS, today.year)
            if not self._repo.is_closed(y)
        ]

    def auto_close_overdue(self, now: datetime | None = None) -> list[int]:
        """Close every year that ended over 48h ago and is still open.

        Returns the years closed on this run (for a startup notification).
        """
        now = now or datetime.now()
        closed: list[int] = []
        for year in range(now.year - _SCAN_YEARS, now.year):
            if self._repo.is_closed(year):
                continue
            year_end = datetime(year + 1, 1, 1)
            if now - year_end >= AUTO_CLOSE_GRACE:
                self._repo.close(year, auto=True, when=now)
                closed.append(year)
        return closed

    def years_awaiting_close(self, now: datetime | None = None) -> list[int]:
        """Ended years still inside the 48h grace — remind, don't auto-close yet."""
        now = now or datetime.now()
        out: list[int] = []
        for year in range(now.year - _SCAN_YEARS, now.year):
            if self._repo.is_closed(year):
                continue
            year_end = datetime(year + 1, 1, 1)
            if timedelta(0) <= now - year_end < AUTO_CLOSE_GRACE:
                out.append(year)
        return out
