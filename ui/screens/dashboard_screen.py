"""Dashboard — alert strip · KPI grid · trend panel · side widgets (live data)."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from domain.money import format_money
from domain.services.dashboard_service import DashboardData, DashboardService
from ui.charts.aged_bars import AgedBars, AgedBucket
from ui.charts.donut import Donut, DonutSegment
from ui.charts.trend_chart import TrendChart, TrendPoint, TrendView
from ui.primitives.card import Card
from ui.primitives.segmented import Segmented
from ui.tokens import active_tokens
from ui.widgets.alert_strip import AlertStrip
from ui.widgets.kpi_card import KpiCard, KpiTrend


class DashboardScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DashboardScreen")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("DashboardScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(self._scroll)

        self._populate()

    def on_activated(self) -> None:
        """Rebuild from the live ledger each time the tab is shown."""
        self._populate()

    def _populate(self) -> None:
        self._data = DashboardService().build()

        content = QWidget()
        content.setObjectName("DashboardContent")
        grid = QVBoxLayout(content)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setSpacing(12)

        if not self._data.has_data:
            grid.addWidget(self._build_empty_state())
            grid.addStretch(1)
        else:
            grid.addWidget(self._build_alert())
            grid.addLayout(self._build_kpi_grid())
            grid.addLayout(self._build_trend_row(), 1)
            grid.addLayout(self._build_bottom_widgets())
            grid.addStretch(1)

        self._scroll.setWidget(content)

    # ---- sections ---------------------------------------------------------

    def _build_empty_state(self) -> QWidget:
        card = Card(title="Chưa có dữ liệu", subtitle="NO LEDGER DATA YET")
        msg = QLabel(
            "Sổ kế toán đang trống. Hãy bắt đầu nhập số liệu thực tế ở các module\n"
            "Bán hàng / Mua hàng / Sổ nhật ký — Dashboard sẽ tự cập nhật.\n\n"
            "(Muốn xem thử với dữ liệu mẫu: python seed_demo.py)"
        )
        msg.setStyleSheet("color: #b6c2d2; background: transparent; font-size: 12px;")
        card.add(msg, 1)
        return card

    def _build_alert(self) -> QWidget:
        overdue = self._data.overdue_count
        period = self._data.period_label
        tail = (
            f" có {overdue} hóa đơn quá hạn cần thu hồi trong tuần này."
            if overdue else " không có hóa đơn quá hạn."
        )
        strip = AlertStrip(
            message_vi=f"Kỳ kế toán {period} · Period {period} ·{tail}",
            action_label="Xem nhiệm vụ",
        )
        strip.action_clicked.connect(self._show_overdue_tasks)
        strip.dismissed.connect(strip.hide)
        return strip

    def _show_overdue_tasks(self) -> None:
        period = self._data.period_label
        details = self._data.overdue_details
        if not details:
            QMessageBox.information(
                self, "Nhiệm vụ kỳ kế toán",
                f"Kỳ kế toán {period}: không có hóa đơn quá hạn cần xử lý.",
            )
            return

        total = sum((d.amount for d in details), Decimal("0"))
        lines = [
            f"Kỳ kế toán {period} — {len(details)} hóa đơn quá hạn "
            f"cần thu hồi (tổng {format_money(total)} ₫):\n"
        ]
        for d in details:
            lines.append(
                f"• {d.invoice_no} · {d.partner_name} · "
                f"{format_money(d.amount)} ₫ · quá hạn {d.days_overdue} ngày"
            )
        QMessageBox.information(self, "Nhiệm vụ kỳ kế toán", "\n".join(lines))

    def _build_kpi_grid(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        for k in self._data.kpis:
            card = KpiCard(
                label_vi=k.label_vi,
                label_en=k.label_en,
                value=format_money(k.value),
                unit="₫",
                delta=f"{k.delta_pct}%",
                trend=KpiTrend(k.trend),
                hint=k.hint,
                spark_data=k.spark or None,
            )
            row.addWidget(card, 1)
        return row

    def _build_trend_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

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

        points = [
            TrendPoint(t.label, float(t.revenue), float(t.cost), float(t.opex))
            for t in self._data.trend
        ]
        self._trend = TrendChart(points, view=TrendView.ALL)
        seg.selection_changed.connect(
            lambda key: self._trend.set_view(TrendView(key))
        )
        trend_card.add(self._trend, 1)
        row.addWidget(trend_card, 1)

        row.addWidget(self._build_expense_card())
        return row

    def _build_expense_card(self) -> QWidget:
        mix = self._data.expense_mix
        donut_card = Card(
            title="Cơ cấu chi phí",
            subtitle=f"EXPENSE MIX · 12M · {self._data.period_label}",
        )
        donut_card.setMinimumHeight(280)
        donut_card.setFixedWidth(360)

        segments = [DonutSegment(s.label_vi, s.label_en, s.pct) for s in mix]
        if not segments:
            empty = QLabel("Chưa có chi phí phát sinh.")
            empty.setStyleSheet("color: #7e8da3; background: transparent;")
            donut_card.add(empty, 1)
            return donut_card

        donut_row = QHBoxLayout()
        donut_row.setSpacing(12)

        center = f"{self._data.expense_total / Decimal('1e9'):.2f} tỷ"
        donut = Donut(segments, size=150, center_value=center)
        donut.setFixedSize(150, 150)
        donut_row.addWidget(donut, alignment=Qt.AlignTop)

        legend = QVBoxLayout()
        legend.setSpacing(4)
        legend.setContentsMargins(0, 4, 0, 0)
        for i, seg_data in enumerate(segments):
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
            pct_lbl = QLabel(f"{seg_data.pct:g}%")
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
        return donut_card

    def _build_bottom_widgets(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        cash_card = Card(title="Tiền & ngân hàng", subtitle="CASH POSITIONS")
        cash_card.setMinimumHeight(200)
        if self._data.cash_positions:
            for pos in self._data.cash_positions:
                cash_card.add_layout(
                    _acc_row(pos.code, pos.name, f"{format_money(pos.amount)} ₫")
                )
        else:
            cash_card.add_layout(_acc_row("—", "Chưa có số dư tiền", "0 ₫"))
        row.addWidget(cash_card, 1)

        ar_card = Card(title="Tuổi nợ phải thu", subtitle="AGED RECEIVABLES")
        ar_card.setMinimumHeight(200)
        buckets = [
            AgedBucket(a.bucket_vi, a.bucket_en, float(a.amount))
            for a in self._data.aged
        ]
        ar_card.add(AgedBars(buckets), 1)
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
    t = active_tokens()
    row = QHBoxLayout()
    row.setContentsMargins(0, 4, 0, 4)
    row.setSpacing(10)

    code_label = QLabel(code)
    code_label.setStyleSheet(
        "QLabel {"
        f" background-color: {t.brand_tint};"
        f" color: {t.brand_700};"
        f" border: 1px solid {t.line};"
        " border-radius: 4px;"
        " padding: 2px 6px;"
        " font-size: 10px;"
        " font-weight: 700;"
        "}"
    )

    name_label = QLabel(name)
    name_label.setStyleSheet(f"color: {t.txt}; background: transparent;")

    amount_label = QLabel(amount)
    amount_label.setStyleSheet(
        f"color: {t.txt}; font-weight: 600; background: transparent;"
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
