"""Presentation-neutral report documents shared by the UI and the exporters.

A cell is one of:

* ``str``     — text, rendered verbatim;
* ``Decimal`` — a money amount, right-aligned and thousands-grouped;
* ``None``    — a blank numeric cell (so zeros read as empty, accounting-style).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from domain.money import format_money
from domain.models.report import (
    BalanceSheet,
    CashFlow,
    DebtSummary,
    GeneralJournal,
    GeneralLedger,
    IncomeStatement,
    TrialBalance,
)
from domain.models.tax import CitReport, VatReport

Cell = "str | Decimal | None"

_ZERO = Decimal("0")


@dataclass(frozen=True)
class Column:
    header: str
    numeric: bool = False


@dataclass
class ReportTable:
    columns: list[Column]
    rows: list[list] = field(default_factory=list)
    total_row: list | None = None
    caption: str | None = None


@dataclass
class ReportDocument:
    title: str
    subtitle: str
    tables: list[ReportTable] = field(default_factory=list)


def format_cell(cell) -> str:
    """Render one cell to display text (used by the UI and the PDF exporter)."""
    if cell is None:
        return ""
    if isinstance(cell, Decimal):
        return format_money(cell)
    return str(cell)


def _money(value: Decimal):
    """Blank a zero amount; keep non-zero as Decimal for downstream formatting."""
    return value if value else None


# --- builders -------------------------------------------------------------


def build_general_journal(report: GeneralJournal) -> ReportDocument:
    table = ReportTable(
        columns=[
            Column("Ngày"),
            Column("Số CT"),
            Column("Diễn giải"),
            Column("TK"),
            Column("Tên tài khoản"),
            Column("Nợ", numeric=True),
            Column("Có", numeric=True),
        ],
        rows=[
            [
                r.entry_date.strftime("%d/%m/%Y"),
                r.ref,
                r.description,
                r.account_code,
                r.account_name,
                _money(r.debit),
                _money(r.credit),
            ]
            for r in report.rows
        ],
        total_row=["", "", "", "", "Cộng phát sinh",
                   report.total_debit, report.total_credit],
    )
    return ReportDocument(
        title="SỔ NHẬT KÝ CHUNG",
        subtitle=f"Kỳ báo cáo: {report.period.label}",
        tables=[table],
    )


def build_general_ledger(report: GeneralLedger) -> ReportDocument:
    """Sổ cái — one captioned section per account, under one shared header bar.

    Every section shares the same columns, so the viewer renders a single header
    and stacks accounts as captioned blocks; each block opens with its "Số dư
    đầu kỳ" line and closes with a "Cộng phát sinh / Số dư cuối kỳ" total row.
    """
    columns = [
        Column("Ngày"),
        Column("Số CT"),
        Column("Diễn giải"),
        Column("TK Đ/Ư"),
        Column("Tên KH/NCC"),
        Column("Nợ", numeric=True),
        Column("Có", numeric=True),
        Column("Số dư", numeric=True),
    ]
    tables: list[ReportTable] = []
    for account in report.accounts:
        rows: list[list] = [
            ["", "", "Số dư đầu kỳ", "", "", None, None,
             _money(account.opening_balance)]
        ]
        for r in account.rows:
            rows.append([
                r.entry_date.strftime("%d/%m/%Y"),
                r.ref,
                r.description,
                r.counter_account,
                r.partner_name,
                _money(r.debit),
                _money(r.credit),
                _money(r.balance),
            ])
        tables.append(ReportTable(
            columns=columns,
            rows=rows,
            total_row=["", "", "Cộng phát sinh / Số dư cuối kỳ", "", "",
                       account.total_debit, account.total_credit,
                       account.closing_balance],
            caption=f"{account.code} — {account.name}",
        ))
    return ReportDocument(
        title="SỔ CÁI",
        subtitle=f"Kỳ báo cáo: {report.period.label}",
        tables=tables,
    )


def build_trial_balance(report: TrialBalance) -> ReportDocument:
    table = ReportTable(
        columns=[
            Column("TK"),
            Column("Tên tài khoản"),
            Column("Dư đầu Nợ", numeric=True),
            Column("Dư đầu Có", numeric=True),
            Column("PS Nợ", numeric=True),
            Column("PS Có", numeric=True),
            Column("Dư cuối Nợ", numeric=True),
            Column("Dư cuối Có", numeric=True),
        ],
        rows=[
            [
                r.code, r.name,
                _money(r.opening_debit), _money(r.opening_credit),
                _money(r.period_debit), _money(r.period_credit),
                _money(r.closing_debit), _money(r.closing_credit),
            ]
            for r in report.rows
        ],
        total_row=[
            "", "Cộng",
            report.total_opening_debit, report.total_opening_credit,
            report.total_period_debit, report.total_period_credit,
            report.total_closing_debit, report.total_closing_credit,
        ],
    )
    return ReportDocument(
        title="BẢNG CÂN ĐỐI TÀI KHOẢN",
        subtitle=f"Kỳ báo cáo: {report.period.label}",
        tables=[table],
    )


def build_income_statement(report: IncomeStatement) -> ReportDocument:
    columns = [Column("TK"), Column("Chỉ tiêu"), Column("Số tiền", numeric=True)]
    rows: list[list] = []
    rows.append(["", "DOANH THU", None])
    for line in report.revenue_lines:
        rows.append([line.code, line.label, _money(line.amount)])
    rows.append(["", "Cộng doanh thu", report.total_revenue])
    rows.append(["", "CHI PHÍ", None])
    for line in report.expense_lines:
        rows.append([line.code, line.label, _money(line.amount)])
    rows.append(["", "Cộng chi phí", report.total_expense])
    table = ReportTable(
        columns=columns,
        rows=rows,
        total_row=["", "LỢI NHUẬN TRƯỚC THUẾ", report.profit_before_tax],
    )
    return ReportDocument(
        title="BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH",
        subtitle=f"Kỳ báo cáo: {report.period.label}",
        tables=[table],
    )


def build_balance_sheet(report: BalanceSheet) -> ReportDocument:
    columns = [Column("TK"), Column("Chỉ tiêu"), Column("Số tiền", numeric=True)]

    asset_rows: list[list] = [[l.code, l.label, _money(l.amount)]
                              for l in report.asset_lines]
    assets = ReportTable(
        columns=columns,
        rows=asset_rows,
        total_row=["", "TỔNG CỘNG TÀI SẢN", report.total_assets],
        caption="TÀI SẢN",
    )

    capital_rows: list[list] = [["", "Nợ phải trả", None]]
    capital_rows += [[l.code, l.label, _money(l.amount)] for l in report.liability_lines]
    capital_rows.append(["", "Vốn chủ sở hữu", None])
    capital_rows += [[l.code, l.label, _money(l.amount)] for l in report.equity_lines]
    if report.result_profit:
        capital_rows.append(["", "Lợi nhuận chưa phân phối", report.result_profit])
    capital = ReportTable(
        columns=columns,
        rows=capital_rows,
        total_row=["", "TỔNG CỘNG NGUỒN VỐN", report.total_capital],
        caption="NGUỒN VỐN",
    )
    return ReportDocument(
        title="BẢNG CÂN ĐỐI KẾ TOÁN",
        subtitle=f"Tại ngày: {report.as_of.strftime('%d/%m/%Y')}",
        tables=[assets, capital],
    )


def build_debt_summary(report: DebtSummary) -> ReportDocument:
    """Bảng tổng hợp công nợ phải thu (131) / phải trả (331) theo đối tượng.

    AR balances read debit-positive, AP credit-positive; ``debit_positive``
    flips the opening/closing sign so both print outstanding balances as positive
    (số dư cuối kỳ = số họ còn nợ mình, hoặc mình còn phải trả). Phát sinh Nợ/Có
    are gross and always shown as-is.
    """
    sign = Decimal(1) if report.debit_positive else Decimal(-1)
    receivable = report.debit_positive

    def signed(value: Decimal) -> Decimal:
        # Normalize away negative zero from the AP sign flip (−1 × 0 → "-0").
        return value * sign or _ZERO
    columns = [
        Column("Mã đối tượng"),
        Column("Tên khách hàng / NCC"),
        Column("Dư đầu kỳ", numeric=True),
        Column("PS Nợ", numeric=True),
        Column("PS Có", numeric=True),
        Column("Dư cuối kỳ", numeric=True),
    ]
    rows = [
        [
            r.partner_code,
            r.partner_name,
            _money(signed(r.opening)),
            _money(r.debit),
            _money(r.credit),
            _money(signed(r.closing)),
        ]
        for r in report.rows
    ]
    table = ReportTable(
        columns=columns,
        rows=rows,
        total_row=[
            "", "Cộng",
            signed(report.total_opening),
            report.total_debit,
            report.total_credit,
            signed(report.total_closing),
        ],
        caption=report.account_label,
    )
    title = ("BẢNG TỔNG HỢP CÔNG NỢ PHẢI THU" if receivable
             else "BẢNG TỔNG HỢP CÔNG NỢ PHẢI TRẢ")
    return ReportDocument(
        title=title,
        subtitle=f"Kỳ báo cáo: {report.period.label}",
        tables=[table],
    )


def build_cash_flow(report: CashFlow) -> ReportDocument:
    columns = [
        Column("Ngày"),
        Column("Số CT"),
        Column("Diễn giải"),
        Column("Tiền thu", numeric=True),
        Column("Tiền chi", numeric=True),
    ]
    rows: list[list] = [["", "", "Số dư đầu kỳ", _money(report.opening_balance), None]]
    rows += [
        [r.entry_date.strftime("%d/%m/%Y"), r.ref, r.description,
         _money(r.inflow), _money(r.outflow)]
        for r in report.rows
    ]
    table = ReportTable(
        columns=columns,
        rows=rows,
        total_row=["", "", "Cộng phát sinh trong kỳ",
                   report.total_inflow, report.total_outflow],
    )
    table.rows.append(["", "", "Số dư cuối kỳ (tồn quỹ)",
                       _money(report.closing_balance), None])
    return ReportDocument(
        title="BÁO CÁO LƯU CHUYỂN TIỀN TỆ",
        subtitle=f"Kỳ báo cáo: {report.period.label}",
        tables=[table],
    )


# --- Báo cáo thuế (Tax) ---------------------------------------------------


def _vat_invoice_table(rows, total_taxable, total_vat, caption: str) -> ReportTable:
    return ReportTable(
        columns=[
            Column("Ngày HĐ"),
            Column("Số HĐ"),
            Column("Ký hiệu"),
            Column("Tên người mua/bán"),
            Column("MST"),
            Column("Giá trị chưa thuế", numeric=True),
            Column("Thuế GTGT", numeric=True),
        ],
        rows=[
            [
                r.invoice_date.strftime("%d/%m/%Y"),
                r.invoice_no, r.serial, r.partner_name, r.partner_tax_code,
                _money(r.taxable), _money(r.vat),
            ]
            for r in rows
        ],
        total_row=["", "", "", "", "Cộng", total_taxable, total_vat],
        caption=caption,
    )


def build_vat_report(report: VatReport) -> ReportDocument:
    payable = report.vat_payable
    if payable >= 0:
        summary_label = "Thuế GTGT phải nộp trong kỳ"
        summary_value = payable
    else:
        summary_label = "Thuế GTGT còn được khấu trừ chuyển kỳ sau"
        summary_value = -payable

    summary = ReportTable(
        columns=[Column("Chỉ tiêu"), Column("Số tiền", numeric=True)],
        rows=[
            ["Thuế GTGT đầu ra (hàng bán ra)", _money(report.output_vat)],
            ["Thuế GTGT đầu vào được khấu trừ", _money(report.input_vat)],
        ],
        total_row=[summary_label, summary_value],
        caption="TỔNG HỢP THUẾ GTGT",
    )
    return ReportDocument(
        title="BÁO CÁO THUẾ GIÁ TRỊ GIA TĂNG",
        subtitle=f"Kỳ báo cáo: {report.period.label}",
        tables=[
            _vat_invoice_table(
                report.output_rows, report.output_taxable, report.output_vat,
                "HÀNG HÓA, DỊCH VỤ BÁN RA (ĐẦU RA)",
            ),
            _vat_invoice_table(
                report.input_rows, report.input_taxable, report.input_vat,
                "HÀNG HÓA, DỊCH VỤ MUA VÀO (ĐẦU VÀO)",
            ),
            summary,
        ],
    )


def _group_totals(groups, predicate) -> tuple[Decimal, Decimal]:
    """Sum (taxable, vat) over rate groups whose rate satisfies ``predicate``.

    ``VatRateGroup.rate`` is a percentage number (0, 5, 8, 10), matching
    ``InvoiceLine.vat_rate``.
    """
    taxable = sum((g.taxable for g in groups if predicate(g.rate)), _ZERO)
    vat = sum((g.vat for g in groups if predicate(g.rate)), _ZERO)
    return taxable, vat


def build_vat_declaration(report: VatReport, company=None) -> ReportDocument:
    """Tờ khai thuế GTGT mẫu 01/GTGT (TT80/2021/TT-BTC), chỉ tiêu [21]–[43].

    A presentation-only re-layout of the existing :class:`VatReport`. No tax is
    re-computed here: indicator values are taken straight from the report's
    already-aggregated rate groups and VAT totals. Indicators the data model
    does not track (kỳ trước chuyển sang [22], hàng nhập khẩu [23a]/[24a]…) are
    left blank for the user to complete in the exported file.

    ``company`` is an optional :class:`~domain.models.company.CompanyProfile`;
    when filled, its name/MST/address prefill the taxpayer header [04]/[05].
    """
    _D = Decimal

    in_taxable, in_vat = report.input_taxable, report.input_vat
    out_taxable, out_vat = report.output_taxable, report.output_vat

    base_0, _ = _group_totals(report.output_groups, lambda r: r == _D("0"))
    base_5, vat_5 = _group_totals(report.output_groups, lambda r: r == _D("5"))
    # Thuế suất giảm 8% (NQ 204/2025) là mức giảm của 10% → khai chung dòng [32]/[33].
    base_10, vat_10 = _group_totals(
        report.output_groups, lambda r: r in (_D("8"), _D("10"))
    )

    payable = report.vat_payable           # [36] = [35] − [25]
    must_pay = payable if payable > 0 else _ZERO          # [40a]/[40]
    carry_forward = -payable if payable < 0 else _ZERO    # [43]

    cols = [
        Column("Chỉ tiêu"),
        Column("Mã số"),
        Column("Giá trị HHDV (chưa thuế GTGT)", numeric=True),
        Column("Thuế GTGT", numeric=True),
    ]

    rows: list[list] = []
    if company is not None and getattr(company, "is_filled", False):
        rows.append([f"Tên người nộp thuế: {company.name}", "[04]", None, None])
        rows.append([f"Mã số thuế: {company.tax_code}", "[05]", None, None])
        if company.address.strip():
            rows.append([f"Địa chỉ: {company.address}", "", None, None])
    rows += [
        ["A. Không phát sinh hoạt động mua, bán trong kỳ", "[21]", None, None],
        ["B. Thuế GTGT còn được khấu trừ kỳ trước chuyển sang", "[22]", None, None],
        ["C. Kê khai thuế GTGT phải nộp ngân sách nhà nước", "", None, None],
        ["  I. Hàng hóa, dịch vụ mua vào trong kỳ", "", None, None],
        ["    1. Giá trị và thuế GTGT của HHDV mua vào", "[23]/[24]",
         _money(in_taxable), _money(in_vat)],
        ["        Trong đó: HHDV nhập khẩu", "[23a]/[24a]", None, None],
        ["    2. Thuế GTGT mua vào được khấu trừ kỳ này", "[25]",
         None, _money(in_vat)],
        ["  II. Hàng hóa, dịch vụ bán ra trong kỳ", "", None, None],
        ["    1. HHDV bán ra không chịu thuế GTGT", "[26]", None, None],
        ["    2. HHDV bán ra chịu thuế GTGT", "[27]/[28]",
         _money(out_taxable), _money(out_vat)],
        ["        a. HHDV bán ra chịu thuế suất 0%", "[29]", _money(base_0), None],
        ["        b. HHDV bán ra chịu thuế suất 5%", "[30]/[31]",
         _money(base_5), _money(vat_5)],
        ["        c. HHDV bán ra chịu thuế suất 10%", "[32]/[33]",
         _money(base_10), _money(vat_10)],
        ["        d. HHDV bán ra không tính thuế", "[32a]", None, None],
        ["    3. Tổng doanh thu và thuế GTGT bán ra", "[34]/[35]",
         _money(out_taxable), _money(out_vat)],
        ["  III. Thuế GTGT phát sinh trong kỳ ([36]=[35]−[25])", "[36]",
         None, _money(payable)],
        ["  VI. Xác định nghĩa vụ thuế GTGT phải nộp trong kỳ", "", None, None],
        ["    1. Thuế GTGT phải nộp của HĐSXKD trong kỳ", "[40a]",
         None, _money(must_pay)],
        ["    3. Thuế GTGT còn phải nộp trong kỳ", "[40]", None, _money(must_pay)],
        ["    4. Thuế GTGT chưa khấu trừ hết kỳ này", "[41]",
         None, _money(-carry_forward if carry_forward else _ZERO)],
        ["    4.2. Thuế GTGT còn được khấu trừ chuyển kỳ sau", "[43]",
         None, _money(carry_forward)],
    ]

    declaration = ReportTable(columns=cols, rows=rows)
    tables = [declaration]

    # Phụ lục giảm thuế GTGT 8% theo NQ 204/2025/QH15 — chỉ khi có hàng bán 8%.
    red_base, red_vat = _group_totals(report.output_groups, lambda r: r == _D("8"))
    if red_base:
        reduction = (red_base * _D("2") / Decimal("100")).quantize(Decimal("1"))
        appendix = ReportTable(
            columns=[
                Column("Tên hàng hóa, dịch vụ"),
                Column("Giá trị chưa thuế GTGT", numeric=True),
                Column("Thuế suất theo quy định"),
                Column("Thuế suất sau giảm"),
                Column("Thuế GTGT được giảm", numeric=True),
            ],
            rows=[[
                "Hàng hóa, dịch vụ bán ra áp dụng thuế suất giảm",
                _money(red_base), "10%", "8%", _money(reduction),
            ]],
            total_row=["Tổng cộng", red_base, "", "", reduction],
            caption="PHỤ LỤC: GIẢM THUẾ GTGT THEO NGHỊ QUYẾT SỐ 204/2025/QH15",
        )
        tables.append(appendix)

    return ReportDocument(
        title="TỜ KHAI THUẾ GIÁ TRỊ GIA TĂNG (Mẫu 01/GTGT)",
        subtitle=f"Kỳ tính thuế: {report.period.label}   ·   "
                 "Ban hành kèm theo TT 80/2021/TT-BTC",
        tables=tables,
    )


def build_cit_report(report: CitReport) -> ReportDocument:
    table = ReportTable(
        columns=[Column("Chỉ tiêu"), Column("Số tiền", numeric=True)],
        rows=[
            ["Doanh thu trong kỳ", _money(report.revenue)],
            ["Lợi nhuận trước thuế (lãi chịu thuế)", _money(report.profit_before_tax)],
            ["Thuế suất TNDN áp dụng", report.rate_label],
            ["Lợi nhuận sau thuế", _money(report.profit_after_tax)],
        ],
        total_row=["Thuế TNDN phải nộp", report.tax_amount],
    )
    return ReportDocument(
        title="TỜ KHAI QUYẾT TOÁN THUẾ TNDN",
        subtitle=f"Kỳ báo cáo: {report.period.label}",
        tables=[table],
    )
