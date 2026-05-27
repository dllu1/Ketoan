"""KPI tile: compact VI/EN label, big tabular value, delta, footer hint, spark."""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.charts.spark import Spark


class KpiTrend(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class KpiCard(QFrame):
    def __init__(
        self,
        *,
        label_vi: str,
        label_en: str,
        value: str,
        unit: str | None = None,
        delta: str = "",
        trend: KpiTrend = KpiTrend.FLAT,
        hint: str = "",
        spark_data: list[float] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("KpiCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(108)
        self.setMinimumWidth(150)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(4)

        # ---- label row (VI · EN · spark)
        label_row = QHBoxLayout()
        label_row.setContentsMargins(0, 0, 0, 0)
        label_row.setSpacing(4)

        labels_col = QVBoxLayout()
        labels_col.setContentsMargins(0, 0, 0, 0)
        labels_col.setSpacing(0)
        vi = QLabel(label_vi.upper())
        vi.setObjectName("KpiLabelVi")
        en = QLabel(label_en.upper())
        en.setObjectName("KpiLabelEn")
        labels_col.addWidget(vi)
        labels_col.addWidget(en)

        label_row.addLayout(labels_col, 1)

        if spark_data:
            spark = Spark(
                spark_data,
                width=60,
                height=22,
                positive=(trend != KpiTrend.DOWN),
            )
            label_row.addWidget(spark, alignment=Qt.AlignTop | Qt.AlignRight)
        root.addLayout(label_row)

        root.addStretch(1)

        # ---- value row
        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(3)
        val = QLabel(value)
        val.setObjectName("KpiValue")
        value_row.addWidget(val)
        if unit:
            u = QLabel(unit)
            u.setObjectName("KpiUnit")
            value_row.addWidget(u, alignment=Qt.AlignBottom)
        value_row.addStretch(1)
        root.addLayout(value_row)

        # ---- footer
        if delta or hint:
            foot = QHBoxLayout()
            foot.setContentsMargins(0, 0, 0, 0)
            foot.setSpacing(6)
            if delta:
                arrow = {"up": "↑", "down": "↓", "flat": "·"}[trend.value]
                d = QLabel(f"{arrow} {delta}")
                d.setObjectName("KpiDelta")
                d.setProperty("trend", trend.value)
                foot.addWidget(d)
            if hint:
                h = QLabel(hint)
                h.setObjectName("KpiHint")
                foot.addWidget(h)
            foot.addStretch(1)
            root.addLayout(foot)
