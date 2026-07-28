"""Thuần logic cây tài khoản tổng hợp (cha–con).

Một tài khoản có thể trỏ tới một *tài khoản cha* qua ``parent_code``. Số dư của
tài khoản cha được hiểu là số dư riêng của nó cộng dồn toàn bộ số dư các con
(đệ quy). Các hàm ở đây không chạm cơ sở dữ liệu — chúng nhận vào một map
``{code: parent_code}`` đã chuẩn hoá và một map số dư, nên rất dễ kiểm thử và
được dùng chung bởi :class:`AccountService` (validate, hiển thị) lẫn
:class:`ReportService` (cộng gộp báo cáo).
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Mapping

_ZERO = Decimal("0")


def normalize_parents(
    parents: Mapping[str, str], known: Iterable[str]
) -> dict[str, str]:
    """Giữ lại các liên kết cha hợp lệ, loại bỏ tự trỏ, cha lạ và vòng lặp.

    ``known`` là tập mã tài khoản đang tồn tại — một liên kết trỏ tới cha không
    có trong tập này (vd cha đã bị ẩn) bị bỏ để con được coi như gốc, tránh làm
    "mất" số dư khỏi tổng. Nếu chuỗi cha tạo thành vòng, mắt xích gây vòng bị cắt.
    """
    known_set = set(known)
    clean: dict[str, str] = {}
    for code, parent in parents.items():
        if parent and parent != code and parent in known_set:
            clean[code] = parent
    for code in list(clean):
        seen: set[str] = set()
        cur = code
        while cur in clean:
            if cur in seen:
                clean.pop(code, None)
                break
            seen.add(cur)
            cur = clean[cur]
    return clean


def children_map(parents: Mapping[str, str]) -> dict[str, list[str]]:
    """Đảo map cha → danh sách con (giữ thứ tự mã tăng dần cho ổn định)."""
    kids: dict[str, list[str]] = defaultdict(list)
    for code in sorted(parents):
        kids[parents[code]].append(code)
    return dict(kids)


def depth(code: str, parents: Mapping[str, str]) -> int:
    """Số cấp cha phía trên ``code`` (gốc = 0). An toàn với vòng lặp."""
    level = 0
    seen: set[str] = set()
    cur = code
    while cur in parents and cur not in seen:
        seen.add(cur)
        cur = parents[cur]
        level += 1
    return level


def descendants(code: str, parents: Mapping[str, str]) -> set[str]:
    """Toàn bộ con cháu của ``code`` (không gồm chính nó)."""
    kids = children_map(parents)
    out: set[str] = set()
    stack = list(kids.get(code, ()))
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(kids.get(cur, ()))
    return out


def aggregate(
    base: Mapping[str, Decimal], parents: Mapping[str, str]
) -> dict[str, Decimal]:
    """Cộng gộp số dư con vào cha (đệ quy).

    Trả về map cho mọi mã trong ``base`` và mọi mã cha xuất hiện trong
    ``parents``. Với mã có con, giá trị = số dư riêng (``base[code]``, có thể 0)
    cộng tổng đã gộp của các con. Vì cây phân hoạch mọi node vào đúng một gốc,
    tổng các gốc bằng tổng toàn bộ ``base`` — không cộng trùng.
    """
    kids = children_map(parents)
    memo: dict[str, Decimal] = {}

    def total(code: str) -> Decimal:
        if code in memo:
            return memo[code]
        memo[code] = base.get(code, _ZERO)  # chốt trước để chặn vòng lặp còn sót
        result = base.get(code, _ZERO)
        for child in kids.get(code, ()):
            result += total(child)
        memo[code] = result
        return result

    codes = set(base) | set(parents) | set(kids)
    return {code: total(code) for code in codes}
