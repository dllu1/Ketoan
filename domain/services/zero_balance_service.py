"""Tài khoản không có số dư cuối kỳ: danh sách do người dùng khai + kiểm tra.

Sau khi kết chuyển, các tài khoản kết quả kinh doanh phải hết số dư. Còn dư là
dấu hiệu có gì đó chưa xong — thiếu quy tắc kết chuyển, khai sai chiều Nợ/Có,
hoặc có bút toán ghi thêm sau khi đã kết chuyển.

Service này **chỉ báo**, không tự sửa sổ: việc xử lý là quyết định của kế toán.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from data.repositories.account_repo import AccountRepository
from data.repositories.journal_repo import JournalRepository
from data.repositories.settings_repo import SettingsRepository
from data.repositories.zero_balance_repo import ZeroBalanceRepository
from domain.models.zero_balance import (
    ZeroBalanceIssue,
    ZeroBalanceReport,
    ZeroBalanceRule,
)
from domain.services.report_service import ReportService

_ZERO = Decimal("0")

# Đã từng lưu danh sách hay chưa — phân biệt "chưa cấu hình lần nào" (nạp mặc
# định) với "người dùng chủ ý xóa hết" (tôn trọng, không nạp lại).
_KEY_SAVED = "zero_balance.configured"

# (mã TK, diễn giải) — bộ mặc định: đúng những tài khoản mà chế độ kế toán VN
# yêu cầu không còn số dư sau khi kết chuyển xác định kết quả kinh doanh.
# Cố ý KHÔNG có 154/155/156 (dở dang, hàng tồn kho được phép còn dư) và 242.
_DEFAULTS: tuple[tuple[str, str], ...] = (
    ("511", "Doanh thu bán hàng và cung cấp dịch vụ"),
    ("512", "Doanh thu nội bộ"),
    ("515", "Doanh thu hoạt động tài chính"),
    ("521", "Các khoản giảm trừ doanh thu"),
    ("632", "Giá vốn hàng bán"),
    ("635", "Chi phí tài chính"),
    ("641", "Chi phí bán hàng"),
    ("642", "Chi phí quản lý doanh nghiệp"),
    ("711", "Thu nhập khác"),
    ("811", "Chi phí khác"),
    ("821", "Chi phí thuế thu nhập doanh nghiệp"),
    ("911", "Xác định kết quả kinh doanh"),
)


class ZeroBalanceError(ValueError):
    pass


def parse_tolerance(text: str) -> Decimal:
    """Đọc dung sai người dùng gõ; chấp nhận '1.000', '1,000' và ô để trống."""
    cleaned = (text or "").strip().replace(" ", "").replace(".", "").replace(",", "")
    if not cleaned:
        return _ZERO
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise ZeroBalanceError(f"Dung sai '{text}' không phải là số.") from exc
    if value < _ZERO:
        raise ZeroBalanceError("Dung sai không được âm.")
    return value


class ZeroBalanceService:
    def __init__(
        self,
        repo: ZeroBalanceRepository | None = None,
        journal_repo: JournalRepository | None = None,
        accounts: AccountRepository | None = None,
        settings: SettingsRepository | None = None,
    ) -> None:
        self._repo = repo or ZeroBalanceRepository()
        self._journal_repo = journal_repo
        self._accounts = accounts
        self._settings = settings

    # ----- danh sách -------------------------------------------------------

    def default_rules(self) -> list[ZeroBalanceRule]:
        return [
            ZeroBalanceRule(
                account_code=code, note=note, include_children=True,
                tolerance=_ZERO, sort_order=(order + 1) * 10,
            )
            for order, (code, note) in enumerate(_DEFAULTS)
        ]

    def ensure_seeded(self) -> list[ZeroBalanceRule]:
        """Nạp bộ mặc định lần đầu; lần sau trả về đúng danh sách đang lưu.

        Khác ``TransferRuleService``: bảng rỗng ở đây là trạng thái hợp lệ — kế
        toán có thể chủ ý tắt hết việc kiểm tra. Nên chỉ nạp mặc định khi chưa
        từng lưu lần nào (cờ ``zero_balance.configured``).
        """
        if self._repo.count() == 0 and not self._settings_repo().get(_KEY_SAVED, ""):
            return self._repo.replace_all(self.default_rules())
        return self._repo.list_all()

    def list_rules(self, *, active_only: bool = False) -> list[ZeroBalanceRule]:
        self.ensure_seeded()
        return self._repo.list_all(active_only=active_only)

    def save_rules(self, rules: list[ZeroBalanceRule]) -> list[ZeroBalanceRule]:
        self._validate(rules)
        self._settings_repo().set(_KEY_SAVED, "1")
        return self._repo.replace_all(rules)

    def restore_defaults(self) -> list[ZeroBalanceRule]:
        self._settings_repo().set(_KEY_SAVED, "1")
        return self._repo.replace_all(self.default_rules())

    # ----- kiểm tra --------------------------------------------------------

    def check(self, as_of: date) -> ZeroBalanceReport:
        """Soi số dư đến hết ngày ``as_of``, trả về các tài khoản còn treo số dư.

        Số dư dùng ở đây là **lũy kế đến ngày đó** (gồm cả số dư đầu kỳ đã khai),
        đúng nghĩa "cuối kỳ tài khoản này còn dư không" trên Cân đối kế toán —
        không phải chỉ số phát sinh trong một khoảng.
        """
        rules = self.list_rules(active_only=True)
        report = ZeroBalanceReport(as_of=as_of, checked_accounts=len(rules))
        if not rules:
            return report
        names = self._account_names()
        for code, balance in self._reporter().net_balances(as_of).items():
            code = code.strip()
            rule = self.rule_for(rules, code)
            if rule is None or not rule.is_violation(balance):
                continue
            report.issues.append(ZeroBalanceIssue(
                account_code=code,
                account_name=names.get(code, ""),
                balance=balance,
                tolerance=rule.tolerance,
                note=rule.note,
            ))
        report.issues.sort(key=lambda i: i.account_code)
        return report

    @staticmethod
    def rule_for(rules: list[ZeroBalanceRule], code: str) -> ZeroBalanceRule | None:
        """Quy tắc áp cho một mã TK — mã dài nhất (cụ thể nhất) thắng.

        Nhờ vậy khai 511 (gồm TK con) rồi khai riêng 5118 với dung sai khác vẫn
        tách được, thay vì hai dòng tranh nhau.
        """
        best: ZeroBalanceRule | None = None
        for rule in rules:
            if not rule.active or not rule.matches(code):
                continue
            if best is None or rule.specificity > best.specificity:
                best = rule
        return best

    # ----- helpers ---------------------------------------------------------

    def _reporter(self) -> ReportService:
        # Dựng mới mỗi lần kiểm tra: ReportService cache sổ theo instance nên
        # dùng lại một đối tượng cũ sẽ đọc số liệu trước lúc kết chuyển.
        return ReportService(
            self._journal_repo or JournalRepository(), self._accounts
        )

    def _settings_repo(self) -> SettingsRepository:
        if self._settings is None:
            self._settings = SettingsRepository()
        return self._settings

    def _account_names(self) -> dict[str, str]:
        repo = self._accounts or AccountRepository()
        return {a.code: a.name for a in repo.list_all()}

    @staticmethod
    def _validate(rules: list[ZeroBalanceRule]) -> None:
        seen: set[tuple[str, bool]] = set()
        for rule in rules:
            code = rule.account_code.strip()
            if not code:
                raise ZeroBalanceError("Mỗi dòng phải có mã tài khoản.")
            if rule.tolerance < _ZERO:
                raise ZeroBalanceError(f"TK {code}: dung sai không được âm.")
            key = (code, rule.include_children)
            if key in seen:
                raise ZeroBalanceError(f"Tài khoản '{code}' bị khai trùng hai lần.")
            seen.add(key)
