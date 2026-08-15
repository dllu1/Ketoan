"""Cấu hình kết chuyển: bộ quy tắc TK nguồn → TK đích do người dùng làm chủ.

Bộ mặc định dưới đây tái lập đúng cách kết chuyển cũ (511/515/711 sang Có 911,
632/641/642… sang Nợ 911) nhưng nay chỉ là **dữ liệu**: người dùng thêm, bớt,
đổi tài khoản đích hay đảo chiều ngay trong màn hình Kết chuyển.
"""
from __future__ import annotations

from data.repositories.settings_repo import SettingsRepository
from data.repositories.transfer_rule_repo import TransferRuleRepository
from domain.models.transfer_rule import TransferDirection, TransferRule

# Số chứng từ của bút toán kết chuyển giá vốn (CogsService) — không được dùng
# lại làm nhóm quy tắc, nếu không hai bút toán sẽ tranh nhau một số chứng từ.
COGS_GROUP_REF = "KC-GV"
# Nhóm dành riêng cho bút toán kết chuyển lãi/lỗ sang 4212, sinh tự động.
RESULT_GROUP_REF = "KC-LN"

_KEY_RESULT_ACCOUNT = "transfer.result_account"
_KEY_PROFIT_ACCOUNT = "transfer.profit_account"

DEFAULT_RESULT_ACCOUNT = "911"      # Xác định kết quả kinh doanh
DEFAULT_PROFIT_ACCOUNT = "4212"     # Lợi nhuận sau thuế chưa phân phối — năm nay

_D = TransferDirection

# (mã nguồn, nhóm, chiều, diễn giải)
_DEFAULTS: tuple[tuple[str, str, TransferDirection, str], ...] = (
    ("511", "KC-DT", _D.DEBIT_SOURCE,  "Doanh thu bán hàng"),
    ("512", "KC-DT", _D.DEBIT_SOURCE,  "Doanh thu nội bộ"),
    ("515", "KC-DT", _D.DEBIT_SOURCE,  "Doanh thu tài chính"),
    ("711", "KC-DT", _D.DEBIT_SOURCE,  "Thu nhập khác"),
    ("632", "KC-CP", _D.CREDIT_SOURCE, "Giá vốn hàng bán"),
    ("635", "KC-CP", _D.CREDIT_SOURCE, "Chi phí tài chính"),
    ("641", "KC-CP", _D.CREDIT_SOURCE, "Chi phí bán hàng"),
    ("642", "KC-CP", _D.CREDIT_SOURCE, "Chi phí quản lý doanh nghiệp"),
    ("811", "KC-CP", _D.CREDIT_SOURCE, "Chi phí khác"),
    ("812", "KC-CP", _D.CREDIT_SOURCE, "Chi phí khác"),
    ("821", "KC-CP", _D.CREDIT_SOURCE, "Chi phí thuế TNDN"),
)


class TransferRuleError(ValueError):
    pass


class TransferRuleService:
    def __init__(
        self,
        repo: TransferRuleRepository | None = None,
        settings: SettingsRepository | None = None,
    ) -> None:
        self._repo = repo or TransferRuleRepository()
        self._settings = settings or SettingsRepository()

    # ----- tài khoản xác định kết quả -------------------------------------

    def result_account(self) -> str:
        return self._settings.get(_KEY_RESULT_ACCOUNT, "") or DEFAULT_RESULT_ACCOUNT

    def profit_account(self) -> str:
        return self._settings.get(_KEY_PROFIT_ACCOUNT, "") or DEFAULT_PROFIT_ACCOUNT

    def set_result_accounts(self, result: str, profit: str) -> int:
        """Đổi TK xác định kết quả / TK lợi nhuận.

        Trả về số quy tắc được trỏ lại sang TK kết quả mới: đổi 911 thành 9111 mà
        để nguyên đích của các quy tắc thì kết chuyển sẽ đổ vào một tài khoản
        không ai dọn, nên phần đó được cập nhật theo luôn.
        """
        result, profit = result.strip(), profit.strip()
        if not result or not profit:
            raise TransferRuleError("Phải khai cả TK xác định kết quả và TK lợi nhuận.")
        if result == profit:
            raise TransferRuleError(
                "TK xác định kết quả và TK lợi nhuận không được trùng nhau."
            )
        previous = self.result_account()
        self._settings.set(_KEY_RESULT_ACCOUNT, result)
        self._settings.set(_KEY_PROFIT_ACCOUNT, profit)
        if result == previous:
            return 0
        rules = self.ensure_seeded()
        retargeted = [r for r in rules if r.target_account.strip() == previous]
        for rule in retargeted:
            rule.target_account = result
        if retargeted:
            self._repo.replace_all(rules)
        return len(retargeted)

    # ----- quy tắc ---------------------------------------------------------

    def default_rules(self) -> list[TransferRule]:
        return [
            TransferRule(
                source_account=code, target_account=DEFAULT_RESULT_ACCOUNT,
                direction=direction, group_ref=group, label=label,
                include_children=True, sort_order=(order + 1) * 10,
            )
            for order, (code, group, direction, label) in enumerate(_DEFAULTS)
        ]

    def ensure_seeded(self) -> list[TransferRule]:
        """Nạp bộ mặc định lần đầu tiên; lần sau trả về đúng cấu hình đang lưu.

        Bảng rỗng có hai nghĩa khác nhau — chưa từng cấu hình, hoặc người dùng
        đã xóa hết quy tắc. Ở đây coi rỗng là *chưa cấu hình*: kết chuyển mà
        không có quy tắc nào thì vô nghĩa, nên nạp lại mặc định an toàn hơn.
        """
        if self._repo.count() == 0:
            return self._repo.replace_all(self.default_rules())
        return self._repo.list_all()

    def list_rules(self, *, active_only: bool = False) -> list[TransferRule]:
        self.ensure_seeded()
        return self._repo.list_all(active_only=active_only)

    def save_rules(self, rules: list[TransferRule]) -> list[TransferRule]:
        self._validate(rules)
        return self._repo.replace_all(rules)

    def restore_defaults(self) -> list[TransferRule]:
        return self._repo.replace_all(self.default_rules())

    # ----- kiểm tra --------------------------------------------------------

    def _validate(self, rules: list[TransferRule]) -> None:
        if not rules:
            raise TransferRuleError("Phải có ít nhất một quy tắc kết chuyển.")
        result_account = self.result_account()
        seen: set[tuple[str, bool]] = set()
        for rule in rules:
            source = rule.source_account.strip()
            target = rule.target_account.strip()
            group = rule.group_ref.strip()
            if not source:
                raise TransferRuleError("Mỗi quy tắc phải có TK nguồn.")
            if not target:
                raise TransferRuleError(f"Quy tắc TK {source}: thiếu TK đích.")
            if source == target:
                raise TransferRuleError(
                    f"Quy tắc TK {source}: TK nguồn và TK đích không được trùng nhau."
                )
            if not group:
                raise TransferRuleError(
                    f"Quy tắc TK {source}: thiếu số chứng từ (nhóm bút toán)."
                )
            if "/" in group:
                raise TransferRuleError(
                    f"Nhóm bút toán '{group}' không được chứa dấu '/' — "
                    "hệ thống tự thêm '/kỳ' vào sau."
                )
            if group.upper() in (COGS_GROUP_REF, RESULT_GROUP_REF):
                raise TransferRuleError(
                    f"Nhóm '{group}' do hệ thống dùng cho kết chuyển giá vốn / "
                    "lãi lỗ — hãy đặt tên khác."
                )
            if source == result_account:
                raise TransferRuleError(
                    f"TK {source} là tài khoản xác định kết quả — số dư của nó "
                    "được kết chuyển sang TK lợi nhuận tự động, không khai quy tắc."
                )
            key = (source, rule.include_children)
            if key in seen:
                raise TransferRuleError(f"TK nguồn '{source}' bị khai trùng hai lần.")
            seen.add(key)

    # ----- tra cứu khi kết chuyển -----------------------------------------

    @staticmethod
    def rule_for(rules: list[TransferRule], code: str) -> TransferRule | None:
        """Quy tắc áp cho một mã TK — mã nguồn dài nhất (cụ thể nhất) thắng.

        Nhờ vậy khai 511 (gồm TK con) rồi khai riêng 5111 vẫn tách được 5111 ra
        nhóm khác, thay vì cả hai cùng nuốt số phát sinh.
        """
        best: TransferRule | None = None
        for rule in rules:
            if not rule.active or not rule.matches(code):
                continue
            if best is None or rule.specificity > best.specificity:
                best = rule
        return best
