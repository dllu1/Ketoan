"""Dashboard — alert strip · KPI grid · trend panel · side widgets."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.charts.aged_bars import AgedBars, AgedBucket
from ui.charts.donut import Donut, DonutSegment
from ui.charts.trend_chart import TrendChart, TrendPoint, TrendView
from ui.primitives.card import Card
from ui.primitives.segmented import Segmented
from ui.widgets.alert_strip import AlertStrip
from ui.widgets.kpi_card import KpiCard, KpiTrend


_KPIS: list[dict] = [
    dict(label_vi="Doanh thu tháng", label_en="Revenue MTD",
         value="3.185.420.000", unit="₫",
         delta="12.4%", trend=KpiTrend.UP, hint="so với 12/2025",
         spark_data=[1.8, 1.9, 2.1, 2.3, 2.0, 2.4, 2.6, 2.7, 2.5, 2.8, 3.0, 3.18]),
    dict(label_vi="Lợi nhuận gộp", label_en="Gross Profit",
         value="1.007.180.000", unit="₫",
         delta="8.2%", trend=KpiTrend.UP, hint="biên 31.6%",
         spark_data=[0.5, 0.6, 0.6, 0.7, 0.65, 0.7, 0.8, 0.85, 0.8, 0.9, 0.95, 1.0]),
    dict(label_vi="Phải thu KH", label_en="Receivables",
         value="1.452.900.000", unit="₫",
         delta="3.1%", trend=KpiTrend.DOWN, hint="23 KH · 7 quá hạn",
         spark_data=[1.6, 1.55, 1.58, 1.50, 1.48, 1.52, 1.50, 1.47, 1.49, 1.46, 1.45, 1.45]),
    dict(label_vi="Phải trả NCC", label_en="Payables",
         value="918.345.000", unit="₫",
         delta="5.4%", trend=KpiTrend.UP, hint="14 NCC",
         spark_data=[0.7, 0.72, 0.78, 0.80, 0.82, 0.85, 0.83, 0.88, 0.89, 0.90, 0.91, 0.92]),
    dict(label_vi="Tiền & tương đương", label_en="Cash & equiv.",
         value="2.140.650.000", unit="₫",
         delta="1.8%", trend=KpiTrend.UP, hint="4 tài khoản",
         spark_data=[1.95, 2.0, 2.02, 2.05, 2.04, 2.08, 2.10, 2.09, 2.11, 2.12, 2.13, 2.14]),
    dict(label_vi="Tồn kho", label_en="Inventory",
         value="3.890.200.000", unit="₫",
         delta="0.6%", trend=KpiTrend.UP, hint="842 SKU",
         spark_data=[3.70, 3.72, 3.75, 3.78, 3.80, 3.82, 3.83, 3.85, 3.86, 3.87, 3.88, 3.89]),
]


_TREND_DATA: list[TrendPoint] = [
    TrendPoint("02/25", 1_880_000_000, 1_310_000_000, 280_000_000),
    TrendPoint("03/25", 2_010_000_000, 1_420_000_000, 305_000_000),
    TrendPoint("04/25", 2_180_000_000, 1_540_000_000, 320_000_000),
    TrendPoint("05/25", 2_350_000_000, 1_690_000_000, 340_000_000),
    TrendPoint("06/25", 2_290_000_000, 1_640_000_000, 335_000_000),
    TrendPoint("07/25", 2_480_000_000, 1_780_000_000, 360_000_000),
    TrendPoint("08/25", 2_660_000_000, 1_900_000_000, 385_000_000),
    TrendPoint("09/25", 2_810_000_000, 2_010_000_000, 400_000_000),
    TrendPoint("10/25", 2_730_000_000, 1_950_000_000, 395_000_000),
    TrendPoint("11/25", 2_950_000_000, 2_120_000_000, 420_000_000),
    TrendPoint("12/25", 3_120_000_000, 2_240_000_000, 440_000_000),
    TrendPoint("01/26", 3_185_420_000, 2_280_000_000, 458_000_000),
]


_EXPENSE_MIX: list[DonutSegment] = [
    DonutSegment("Nguyên vật liệu",      "Raw materials",  48),
    DonutSegment("Lương & phụ cấp",      "Payroll",        22),
    DonutSegment("Vận hành nhà máy",     "Plant ops",      14),
    DonutSegment("Vận chuyển logistics", "Logistics",       8),
    DonutSegment("Quản lý admin",        "Admin",           5),
    DonutSegment("Khác",                 "Other",           3),
]


_AGED: list[AgedBucket] = [
    AgedBucket("Trong hạn",   "0-30",   842_300_000),
    AgedBucket("31-60 ngày",  "31-60",  318_400_000),
    AgedBucket("61-90 ngày",  "61-90",  168_900_000),
    AgedBucket("> 90 ngày",   "90+",    123_300_000),
]


class DashboardScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DashboardScreen")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("DashboardScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        content.setObjectName("DashboardContent")
        grid = QVBoxLayout(content)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setSpacing(12)

        grid.addWidget(self._build_alert())
        grid.addLayout(self._build_kpi_grid())
        grid.addLayout(self._build_trend_row(), 1)
        grid.addLayout(self._build_bottom_widgets())
        grid.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ---- sections ---------------------------------------------------------

    def _build_alert(self) -> QWidget:
        return AlertStrip(
            message_vi="Kỳ kế toán 01/2026 đã mở · Period 01/2026 is open ·  có 7 hóa đơn quá hạn và 1 nghĩa vụ thuế TNDN tạm tính cần xử lý trong tuần này.",
            action_label="Xem nhiệm vụ",
        )

    def _build_kpi_grid(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        for k in _KPIS:
            row.addWidget(KpiCard(**k), 1)
        return row

    def _build_trend_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        # ---- Trend chart panel
        trend_card = Card(title="Doanh thu 12 tháng", subtitle="TRAILING REVENUE")
        trend_card.setMinimumHeight(280)

        seg_row = QHBoxLayout()
        seg_row.setContentsMargins(0, 0, 0, 0)
        legend_lbl = QLabel("— Doanh thu      - - - Giá vốn")
        legend_lbl.setStyleSheet(
            "color: #7e8da3; font-size: 10px; background: transparent;"
        )
        seg = Segmented(
            [("all", "Tổng"), ("rev", "D.thu"), ("cost", "G.vốn"), ("opex", "CP QL")],
            default="all",
        )
        seg_row.addWidget(legend_lbl)
        seg_row.addStretch(1)
        seg_row.addWidget(seg)
        trend_card.add_layout(seg_row)

        self._trend = TrendChart(_TREND_DATA, view=TrendView.ALL)
        seg.selection_changed.connect(
            lambda key: self._trend.set_view(TrendView(key))
        )
        trend_card.add(self._trend, 1)
        row.addWidget(trend_card, 1)

        # ---- Expense mix donut
        donut_card = Card(title="Cơ cấu chi phí", subtitle="EXPENSE MIX · MTD 01/2026")
        donut_card.setMinimumHeight(280)
        donut_card.setFixedWidth(360)

        donut_row = QHBoxLayout()
        donut_row.setSpacing(12)

        donut = Donut(_EXPENSE_MIX, size=150, center_value="2.18 tỷ")
        donut.setFixedSize(150, 150)
        donut_row.addWidget(donut, alignment=Qt.AlignTop)

        legend = QVBoxLayout()
        legend.setSpacing(4)
        legend.setContentsMargins(0, 4, 0, 0)
        for i, seg_data in enumerate(_EXPENSE_MIX):
            row_w = QHBoxLayout()
            row_w.setSpacing(6)
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(
                f"QLabel {{ background-color: {donut.segment_color_hex(i)};"
                " border-radius: 4px; }"
            )
            name = QLabel(seg_data.label_vi)
            name.setStyleSheet(
                "color: #b6c2d2; background: transparent; font-size: 11px;"
            )
            pct_lbl = QLabel(f"{seg_data.pct}%")
            pct_lbl.setStyleSheet(
                "color: #e6edf3; font-weight: 700; background: transparent;"
                " font-size: 11px;"
            )
            pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_w.addWidget(dot, alignment=Qt.AlignVCenter)
            row_w.addWidget(name, 1)
            row_w.addWidget(pct_lbl)
            legend.addLayout(row_w)
        legend.addStretch(1)
        donut_row.addLayout(legend, 1)

        donut_card.add_layout(donut_row)
        row.addWidget(donut_card)
        return row

    def _build_bottom_widgets(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        cash_card = Card(title="Tiền & ngân hàng", subtitle="CASH POSITIONS")
        cash_card.setMinimumHeight(200)
        for code, name, amount in (
            ("1111", "Tiền mặt tại quỹ", "58.400.000 ₫"),
            ("11211", "TK Vietcombank · 0071...442", "1.142.600.000 ₫"),
            ("11212", "TK BIDV · 0028...118", "642.800.000 ₫"),
            ("11213", "TK Techcombank · 1900...210", "296.850.000 ₫"),
        ):
            cash_card.add_layout(_acc_row(code, name, amount))
        row.addWidget(cash_card, 1)

        ar_card = Card(title="Tuổi nợ phải thu", subtitle="AGED RECEIVABLES")
        ar_card.setMinimumHeight(200)
        ar_card.add(AgedBars(_AGED), 1)
        row.addWidget(ar_card, 1)

        qa_card = Card(title="Tác vụ nhanh", subtitle="QUICK ACTIONS · F-KEYS")
        qa_card.setMinimumHeight(200)
        qa_grid = QGridLayout()
        qa_grid.setSpacing(8)
        for i, (vi, en, kbd) in enumerate((
            ("Thêm bút toán", "NEW JOURNAL ENTRY", "Ctrl N"),
            ("Lập hóa đơn GTGT", "NEW VAT INVOICE", "Ctrl I"),
            ("Phiếu thu / chi", "CASH SLIP", "Ctrl R"),
            ("Tìm nhanh", "SEARCH", "Ctrl K"),
        )):
            tile = _quick_action_tile(vi, en, kbd)
            qa_grid.addWidget(tile, i // 2, i % 2)
        qa_card.add_layout(qa_grid)
        row.addWidget(qa_card, 1)

        return row


# ---- small helpers ---------------------------------------------------------


def _acc_row(code: str, name: str, amount: str) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 4, 0, 4)
    row.setSpacing(10)

    code_label = QLabel(code)
    code_label.setStyleSheet(
        "QLabel {"
        " background-color: #1a2333;"
        " color: #a1caff;"
        " border: 1px solid #1c2538;"
        " border-radius: 4px;"
        " padding: 2px 6px;"
        " font-size: 10px;"
        " font-weight: 700;"
        "}"
    )

    name_label = QLabel(name)
    name_label.setStyleSheet("color: #b6c2d2; background: transparent;")

    amount_label = QLabel(amount)
    amount_label.setStyleSheet(
        "color: #e6edf3; font-weight: 600; background: transparent;"
    )
    amount_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    row.addWidget(code_label)
    row.addWidget(name_label, 1)
    row.addWidget(amount_label)
    return row


def _quick_action_tile(vi: str, en: str, kbd: str) -> QWidget:
    from PySide6.QtWidgets import QFrame
    tile = QFrame()
    tile.setStyleSheet(
        "QFrame {"
        " background-color: #1a2333;"
        " border: 1px solid #1c2538;"
        " border-radius: 6px;"
        "}"
        "QFrame:hover { border-color: #5e95d6; }"
    )
    tile.setCursor(Qt.PointingHandCursor)
    tile.setMinimumHeight(64)

    layout = QHBoxLayout(tile)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(8)

    col = QVBoxLayout()
    col.setSpacing(2)
    vi_label = QLabel(vi)
    vi_label.setStyleSheet("color: #e6edf3; font-weight: 600; background: transparent;")
    en_label = QLabel(en)
    en_label.setStyleSheet(
        "color: #7e8da3; font-size: 10px; background: transparent;"
    )
    col.addWidget(vi_label)
    col.addWidget(en_label)
    layout.addLayout(col, 1)

    kbd_label = QLabel(kbd)
    kbd_label.setStyleSheet(
        "QLabel {"
        " background-color: #161e2c;"
        " color: #b6c2d2;"
        " border: 1px solid #1c2538;"
        " border-bottom: 2px solid #2a3953;"
        " border-radius: 4px;"
        " padding: 1px 6px;"
        " font-size: 10px;"
        " font-weight: 700;"
        "}"
    )
    layout.addWidget(kbd_label, alignment=Qt.AlignTop)
    return tile
