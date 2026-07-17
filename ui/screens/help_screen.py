"""HelpScreen — "Hướng dẫn sử dụng": searchable guide to every feature.

A small search box at the top filters the guide live (accent-insensitive)
as the user types — no need to press Enter. Each section carries the module
key of the tab it documents, so the guide can offer a one-click "Mở …" link
that jumps straight to that phân hệ.
"""
from __future__ import annotations

import unicodedata

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.primitives.card import Card
from ui.primitives.icon_input import IconInput


# Friendly tab name per module key — used for the "Mở …" quick-jump link.
# Keys must match ChromeWindow._screens / ui.chrome.sidebar module keys.
_TAB_LABELS: dict[str, str] = {
    "dashboard": "Tổng quan",
    "journal": "Sổ nhật ký chung",
    "sales": "Bán hàng",
    "purchase": "Mua hàng",
    "inventory": "Kho hàng",
    "cash": "Quỹ & Ngân hàng",
    "assets": "Tài sản cố định",
    "reports": "Báo cáo tài chính",
    "tax": "Báo cáo thuế",
    "directory": "Danh mục",
    "settings": "Cấu hình",
}


def _normalize(text: str) -> str:
    """Lower-case and strip Vietnamese diacritics so "tai san" matches "Tài sản"."""
    text = text.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


# Guide content: (section title, module key | None, [(feature, shortcut, [steps]), ...]).
# The module key drives the "Mở …" quick-jump link; None = no single tab.
# Keep this in sync with the modules in ui/chrome/sidebar.py.
_GUIDE: tuple[tuple[str, str | None, tuple[tuple[str, str, tuple[str, ...]], ...]], ...] = (
    (
        "Bắt đầu / Cơ bản",
        None,
        (
            (
                "Quy trình làm việc tổng quát", "",
                (
                    "1) Khai báo Danh mục: tài khoản, đối tác (KH/NCC) và vật tư/hàng hóa.",
                    "2) Nhập chứng từ hằng ngày ở các phân hệ Bán hàng, Mua hàng, Quỹ & Ngân hàng…",
                    "3) Ghi sổ chứng từ — khi đó bút toán mới lên Sổ nhật ký, Sổ cái và trừ/nhập kho.",
                    "4) Cuối kỳ: xem Báo cáo tài chính, lập Báo cáo thuế, rồi Chốt sổ ở Cấu hình.",
                    "Mẹo: chứng từ còn “nháp” chưa ảnh hưởng sổ sách — phải Ghi sổ mới được ghi nhận.",
                ),
            ),
            (
                "Chuyển phân hệ", "F2–F10",
                (
                    "Bấm vào một mục ở thanh bên trái để mở phân hệ tương ứng.",
                    "Hoặc dùng phím tắt F2 (Tổng quan) đến F10 để chuyển nhanh.",
                    "Trong hướng dẫn này, bấm nút “Mở …” ở mỗi mục để nhảy thẳng tới tab đó.",
                    "Mở lại Hướng dẫn sử dụng này bất cứ lúc nào bằng phím F1.",
                ),
            ),
            (
                "Tìm kiếm toàn cục", "Ctrl K",
                (
                    "Bấm Ctrl+K hoặc nhấp ô tìm kiếm trên thanh công cụ.",
                    "Gõ số tài khoản, tên khách hàng hoặc số phiếu rồi Enter.",
                    "Kết quả mở trong Sổ nhật ký chung đã được lọc sẵn.",
                ),
            ),
            (
                "Chọn kỳ kế toán", "",
                (
                    "Bấm nút kỳ kế toán trên thanh công cụ phía trên.",
                    "Chọn tháng/quý/năm cần xem; mọi báo cáo và danh sách lọc theo kỳ này.",
                    "Kỳ đang chọn hiển thị ở thanh trạng thái dưới cùng.",
                ),
            ),
            (
                "Giao diện sáng / tối", "",
                (
                    "Vào Cấu hình (biểu tượng bánh răng dưới thanh bên).",
                    "Tại thẻ Giao diện, chọn Sáng (mặc định) hoặc Tối.",
                    "Thay đổi áp dụng ngay, không cần khởi động lại.",
                ),
            ),
        ),
    ),
    (
        "Tổng quan / Dashboard",
        "dashboard",
        (
            (
                "Xem nhanh tình hình tài chính", "F2",
                (
                    "Các thẻ KPI tóm tắt doanh thu, chi phí, tiền mặt và công nợ trong kỳ.",
                    "Biểu đồ thể hiện xu hướng theo thời gian.",
                    "Số liệu tự cập nhật theo kỳ kế toán đang chọn.",
                ),
            ),
        ),
    ),
    (
        "Sổ nhật ký chung",
        "journal",
        (
            (
                "Tạo bút toán mới", "Ctrl N",
                (
                    "Mở Sổ nhật ký chung (F3) rồi bấm nút Bút toán mới, hoặc bấm Ctrl+N ở bất cứ đâu.",
                    "Chọn ngày và nhập diễn giải chung cho bút toán.",
                    "Tại lưới Nợ/Có, gõ mã tài khoản ở cột TK (có gợi ý tự động), nhập số tiền vào cột Nợ hoặc Có.",
                    "Bấm thêm dòng cho mỗi tài khoản đối ứng; tổng Nợ phải bằng tổng Có.",
                    "Bấm Ghi sổ (Ctrl+S) để lưu, hoặc Esc để đóng.",
                ),
            ),
            (
                "Sửa hoặc xóa bút toán", "",
                (
                    "Chọn một dòng trong bảng rồi bấm Sửa, hoặc nháy đúp vào dòng đó.",
                    "Muốn xóa: chọn dòng rồi bấm Xóa và xác nhận.",
                    "Khi chọn một bút toán, lưới Nợ/Có bên dưới hiện chi tiết các tài khoản.",
                    "Bút toán thuộc năm đã chốt sổ sẽ bị khóa, không sửa/xóa được.",
                ),
            ),
            (
                "Tìm bút toán", "",
                (
                    "Gõ số chứng từ hoặc diễn giải vào ô tìm kiếm — danh sách lọc ngay khi gõ.",
                    "Bảng chỉ hiện các bút toán thuộc kỳ kế toán đang chọn.",
                ),
            ),
        ),
    ),
    (
        "Bán hàng",
        "sales",
        (
            (
                "Lập hóa đơn bán hàng", "Ctrl I",
                (
                    "Mở Bán hàng (F4) và bấm Hóa đơn mới (hoặc Ctrl+I) để mở phiếu hóa đơn GTGT đầu ra.",
                    "Nhập Số CT (bắt buộc), số hóa đơn, ký hiệu, ngày và cách thanh toán (Công nợ / Tiền mặt / Chuyển khoản).",
                    "Gõ Mã KH ở ô khách hàng (để trống = khách lẻ); tên, MST, địa chỉ tự điền nếu KH đã có trong danh mục.",
                    "Ở bảng DÒNG HÀNG, bấm “+ Thêm dòng”, gõ mã hàng (tên/ĐVT/đơn giá/VAT tự điền), nhập số lượng.",
                    "Dòng thừa thì chọn rồi bấm “− Xóa dòng”. Tiền hàng, thuế GTGT và tổng tính tự động phía dưới.",
                ),
            ),
            (
                "Lưu nháp hay Ghi sổ?", "",
                (
                    "Bấm Lưu nháp để giữ hóa đơn chờ xử lý (chưa lên sổ cái, chưa trừ kho).",
                    "Bấm Ghi sổ để ghi nhận chính thức: lên bút toán doanh thu và tự động xuất kho mặt hàng.",
                    "Với đơn đang nháp trong danh sách, chọn rồi bấm Ghi sổ ở thanh công cụ để ghi sổ sau.",
                ),
            ),
            (
                "Sửa, xóa, theo dõi đơn", "",
                (
                    "Nháy đúp một hóa đơn để mở sửa; chọn rồi bấm Xóa để xóa.",
                    "Khi ghi sổ hóa đơn có khách hàng mới, hệ thống hỏi có lưu vào Danh mục không.",
                    "Số đơn còn nháp hiển thị bằng huy hiệu trên mục Bán hàng ở thanh bên và ở chuông thông báo.",
                ),
            ),
        ),
    ),
    (
        "Mua hàng",
        "purchase",
        (
            (
                "Nhập hóa đơn mua vào", "F5",
                (
                    "Mở Mua hàng (F5) và bấm Hóa đơn mua để mở phiếu hóa đơn GTGT đầu vào.",
                    "Nhập Số CT, ngày, cách thanh toán và gõ Mã NCC (để trống = NCC vãng lai).",
                    "Thêm các dòng hàng/dịch vụ mua vào giống như ở Bán hàng.",
                ),
            ),
            (
                "Ghi sổ hàng mua → nhập kho", "",
                (
                    "Bấm Ghi sổ để ghi nhận hóa đơn mua: lên bút toán và tự động nhập kho các mặt hàng.",
                    "Thuế GTGT đầu vào được tổng hợp sang Báo cáo thuế.",
                    "Có thể Lưu nháp trước rồi chọn đơn và bấm Ghi sổ sau.",
                ),
            ),
        ),
    ),
    (
        "Kho hàng",
        "inventory",
        (
            (
                "Nhập kho thủ công", "F6",
                (
                    "Mở Kho hàng (F6) và bấm nút Nhập kho.",
                    "Chọn Mặt hàng, đặt Loại = “Nhập kho”, nhập Ngày, Số lượng (bắt buộc > 0) và Đơn giá.",
                    "Bấm Save để lưu; bảng Nhập–Xuất–Tồn cập nhật ngay.",
                    "Nếu kho chưa có mặt hàng nào, ứng dụng nhắc mở Danh mục → Vật tư & Hàng hóa để khai báo trước.",
                ),
            ),
            (
                "Khai báo tồn đầu kỳ", "",
                (
                    "Bấm Nhập kho, chọn Loại = “Tồn đầu kỳ” thay vì “Nhập kho”.",
                    "Nhập số lượng và đơn giá tồn có sẵn để làm số dư đầu cho mặt hàng.",
                ),
            ),
            (
                "Xuất kho", "",
                (
                    "Có hai nguồn xuất kho, đều diễn ra TỰ ĐỘNG — không nhập phiếu xuất thủ công tại đây:",
                    "• Xuất bán: khi Ghi sổ một hóa đơn ở phân hệ Bán hàng, mặt hàng tự trừ khỏi kho.",
                    "• Xuất NVL cho sản xuất: khi Lưu Bảng tính giá thành, nguyên vật liệu (152) tự trừ theo mã từng loại, dựa trên định mức (BOM) × số lượng sản xuất.",
                    "Cụm cột “Xuất” (ĐG · SL · TT) trong báo cáo Nhập–Xuất–Tồn gộp cả hai nguồn xuất trên.",
                ),
            ),
            (
                "Xem báo cáo Nhập–Xuất–Tồn", "",
                (
                    "Trong Kho hàng (F6) dùng dải nút trên cùng để chọn: Nhập–Xuất–Tồn, Bảng kê NVL chính, Giá thành SP, Bảng kê TP (155).",
                    "Chọn Mã kho (152/153/155/156) và khoảng ngày Từ … đến để lọc.",
                    "Mỗi mặt hàng hiện đủ Đơn giá · Số lượng · Thành tiền cho cả bốn giai đoạn: Tồn đầu kỳ, Nhập, Xuất và Tồn cuối kỳ.",
                    "Số liệu gom nhóm theo tài khoản kho (152/153/155/156) kèm dòng “Cộng nhóm”.",
                    "Gõ mã hoặc tên hàng vào ô tìm kiếm để lọc nhanh; dòng cuối hiển thị tổng giá trị tồn cuối kỳ.",
                ),
            ),
            (
                "Bảng kê Nhập–Xuất–Tồn NVL chính", "",
                (
                    "Trong Kho hàng (F6) chọn thẻ “Bảng kê NVL chính”.",
                    "Bấm “+ Thêm dòng”, nhập Mã VT, loại vật tư, ĐVT và số liệu Đầu kỳ / Nhập / Xuất (đơn giá, số lượng, thành tiền).",
                    "Cột Tồn cuối kỳ (SL & TT) tự tính = Đầu kỳ + Nhập − Xuất, cập nhật ngay khi gõ.",
                    "Nếu tồn cuối kỳ ra số ÂM, ô được tô đỏ và nút Lưu bị khóa — tồn kho không thể âm; hãy sửa lại số liệu trước khi lưu.",
                    "Bấm Lưu để lưu bảng kê cho kỳ kế toán đang chọn.",
                ),
            ),
            (
                "Bảng tính giá thành sản phẩm", "",
                (
                    "Trong Kho hàng (F6) chọn thẻ “Giá thành SP”.",
                    "Nhập ba khoản chi phí chung của kỳ: Nhân công (15402), SX chung (154032), Chi phí khác (154033).",
                    "Với mỗi sản phẩm, nhập Mã, tên và Số lượng sản xuất. Cột NVL (15401) tự tính cho sản phẩm ĐÃ khai định mức (Danh mục → Định mức): NVL = định mức × số lượng × đơn giá xuất bình quân của kỳ.",
                    "Sản phẩm chưa có định mức thì tự nhập tay số tiền NVL (nhưng sẽ không tách được theo mã và không phát sinh xuất kho).",
                    "Hệ thống phân bổ nhân công / SX chung / chi phí khác cho từng sản phẩm theo tỷ lệ NVL, rồi tính Tổng giá thành và Đơn giá (= tổng ÷ số lượng).",
                    "Bấm Lưu: bảng giá thành được lưu cho kỳ, ĐỒNG THỜI nguyên vật liệu tiêu hao tự trừ vào cột Xuất kho 152 theo mã từng loại (xem ở Nhập–Xuất–Tồn). Lưu lại là làm mới, không cộng dồn.",
                ),
            ),
            (
                "Bảng kê Nhập–Xuất–Tồn thành phẩm (155)", "",
                (
                    "Trong Kho hàng (F6) chọn thẻ “Bảng kê TP (155)”.",
                    "Bấm “+ Thêm dòng”, nhập Mã TP, tên, ĐVT và số liệu Đầu kỳ (SL·TT), Nhập (SL·TT) cùng SL xuất.",
                    "Nhanh hơn: bấm “Lấy nhập từ giá thành” để tự điền SL & TT nhập từ Bảng tính giá thành của kỳ — khỏi gõ tay.",
                    "Đơn giá xuất tự tính theo bình quân gia quyền = (TT đầu kỳ + TT nhập) ÷ (SL đầu kỳ + SL nhập); TT xuất và tồn cuối kỳ suy ra theo đó, cập nhật ngay khi gõ.",
                    "Tồn đầu kỳ tự kết chuyển từ tồn cuối kỳ trước. Dòng màu xám là đồng bộ tự động từ sổ kho (chỉ đọc, không sửa).",
                    "Nếu tồn cuối kỳ ra ÂM, ô bị tô đỏ và nút Lưu bị khóa — hãy sửa lại số liệu trước khi lưu.",
                ),
            ),
        ),
    ),
    (
        "Quỹ & Ngân hàng",
        "cash",
        (
            (
                "Lập phiếu thu (tiền vào)", "F7",
                (
                    "Mở Quỹ & Ngân hàng (F7) và bấm nút Phiếu thu.",
                    "Nhập Số phiếu (vd PT-0001), ngày, chọn TK tiền (111 quỹ tiền mặt hoặc 112 ngân hàng).",
                    "Gõ TK đối ứng (vd 131 phải thu, 511 doanh thu…) — tên tài khoản hiện ngay bên dưới.",
                    "Nhập Số tiền và diễn giải rồi bấm Save.",
                ),
            ),
            (
                "Lập phiếu chi (tiền ra)", "",
                (
                    "Bấm nút Phiếu chi và điền tương tự (vd PC-0001).",
                    "Chọn TK tiền chi ra và TK đối ứng (vd 331 phải trả, 642 chi phí…).",
                    "Số dư quỹ cập nhật ngay; cột Tồn hiển thị số dư lũy kế sau mỗi phiếu.",
                ),
            ),
            (
                "Lọc và xóa phiếu", "",
                (
                    "Dùng ô chọn Tài khoản trên thanh công cụ để xem riêng từng quỹ/ngân hàng.",
                    "Muốn xóa: chọn dòng phiếu rồi bấm Xóa và xác nhận.",
                    "Dòng tổng dưới cùng hiển thị số dư từng tài khoản tiền.",
                ),
            ),
        ),
    ),
    (
        "Tài sản cố định",
        "assets",
        (
            (
                "Khai báo tài sản mới", "F8",
                (
                    "Mở Tài sản cố định (F8) và bấm nút Tài sản mới.",
                    "Nhập mã, tên, tài khoản, nguyên giá và số kỳ khấu hao (số tháng).",
                    "Hệ thống tính mức khấu hao mỗi tháng theo phương pháp đường thẳng.",
                    "Nháy đúp một tài sản hoặc bấm Sửa để chỉnh sửa.",
                ),
            ),
            (
                "Ghi khấu hao theo kỳ", "",
                (
                    "Chọn Năm và Tháng cần tính trên thanh công cụ.",
                    "Bấm Ghi khấu hao kỳ để lập bút toán khấu hao cho tháng đó.",
                    "Nếu tháng không có tài sản phát sinh khấu hao, hệ thống sẽ báo và không tạo bút toán.",
                ),
            ),
            (
                "Xem lưới khấu hao 12 tháng", "",
                (
                    "Chọn một tài sản ở bảng trên để xem lịch khấu hao 12 tháng bên dưới.",
                    "Lưới hiển thị khấu hao từng tháng, lũy kế và giá trị còn lại.",
                ),
            ),
        ),
    ),
    (
        "Báo cáo tài chính",
        "reports",
        (
            (
                "Chọn và xem báo cáo", "F9",
                (
                    "Mở Báo cáo tài chính (F9). Dùng dải nút để chọn: Nhật ký chung, Cân đối TK, KQ kinh doanh, Cân đối kế toán, Lưu chuyển tiền.",
                    "Đặt khoảng ngày Từ … đến; báo cáo dựng lại tự động.",
                    "Dòng tóm tắt dưới cùng cho biết số dòng dữ liệu trong kỳ.",
                ),
            ),
            (
                "Xuất Excel / PDF", "",
                (
                    "Bấm Xuất Excel hoặc Xuất PDF rồi chọn nơi lưu file.",
                    "Lần đầu xuất có thể cần cài thư viện: pip install openpyxl reportlab.",
                ),
            ),
        ),
    ),
    (
        "Báo cáo thuế",
        "tax",
        (
            (
                "Tờ khai thuế GTGT và TNDN", "F10",
                (
                    "Mở Báo cáo thuế (F10) và dùng dải nút để chọn Thuế GTGT hoặc Thuế TNDN.",
                    "Đặt khoảng ngày để tổng hợp thuế đầu ra/đầu vào từ hóa đơn bán và mua.",
                    "Bấm Xuất Excel / Xuất PDF để xuất tờ khai. Nhớ lập tờ khai GTGT cuối mỗi kỳ.",
                ),
            ),
        ),
    ),
    (
        "Danh mục",
        "directory",
        (
            (
                "Thêm khách hàng / nhà cung cấp", "",
                (
                    "Mở Danh mục → thẻ Đối tác (KH/NCC) và bấm Đối tác mới.",
                    "Nhập mã, tên, loại (khách hàng/NCC), MST, điện thoại, email rồi lưu.",
                    "Nháy đúp một đối tác hoặc bấm Sửa để chỉnh sửa.",
                ),
            ),
            (
                "Thêm vật tư / hàng hóa", "",
                (
                    "Mở Danh mục → thẻ Vật tư / Hàng hóa và bấm Vật tư mới.",
                    "Khai báo mã, tên, nhóm tài khoản (152/153/155/156), ĐVT, đơn giá, thuế suất VAT.",
                    "Phải khai báo mặt hàng ở đây trước khi nhập kho hoặc lên dòng hàng trong hóa đơn.",
                ),
            ),
            (
                "Khai định mức nguyên vật liệu (BOM)", "",
                (
                    "Mở Danh mục → thẻ Định mức. Chọn thành phẩm ở ô trên cùng.",
                    "Bấm “+ Thêm dòng”, gõ Mã NVL (kho 152) — tên và ĐVT tự điền — rồi nhập Định mức trên một đơn vị sản phẩm.",
                    "Bấm Lưu để lưu định mức cho thành phẩm đó.",
                    "Định mức là dữ liệu bắt buộc để Bảng tính giá thành tự tính tiền NVL và tự xuất kho 152 theo mã từng loại khi lưu.",
                ),
            ),
            (
                "Quản lý hệ thống tài khoản", "",
                (
                    "Mở Danh mục → thẻ Hệ thống tài khoản để xem/sửa các tài khoản.",
                    "Bấm Tài khoản mới để thêm tài khoản chi tiết khi cần.",
                    "Đổi thông tư (TT133/TT200) ở Cấu hình sẽ nạp thêm các tài khoản tương ứng.",
                ),
            ),
        ),
    ),
    (
        "Cấu hình",
        "settings",
        (
            (
                "Chọn chế độ kế toán (Thông tư)", "",
                (
                    "Vào Cấu hình › Chế độ kế toán và chọn Thông tư 133 hoặc 200.",
                    "Khi đổi, hệ thống chỉ nạp thêm tài khoản mới, không xóa dữ liệu cũ.",
                    "Bấm Áp dụng để xác nhận.",
                ),
            ),
            (
                "Chốt sổ cuối năm", "",
                (
                    "Vào Cấu hình › Chốt sổ cuối năm, chọn năm cần chốt rồi bấm Chốt sổ.",
                    "Sau khi chốt, mọi chứng từ của năm đó bị khóa, không thể sửa/xóa.",
                    "Nếu không chốt, hệ thống tự động chốt sau 48 giờ kể từ cuối năm.",
                ),
            ),
            (
                "Khai thông tin công ty (điền sẵn tờ khai thuế)", "",
                (
                    "Vào Cấu hình › Thông tin công ty ở đầu trang.",
                    "Nhập Tên người nộp thuế, Mã số thuế (MST) và Địa chỉ trụ sở rồi bấm Lưu thông tin.",
                    "Các thông tin này tự điền sẵn phần đầu các tờ khai thuế GTGT/TNDN khi xuất.",
                    "MST còn dùng để tự phân loại hóa đơn điện tử lấy từ email thành hóa đơn mua hay bán.",
                ),
            ),
            (
                "Tự động lấy hóa đơn điện tử (HĐĐT) từ email", "",
                (
                    "Vào Cấu hình › Email / Hóa đơn điện tử.",
                    "Chọn nhà cung cấp (Gmail, Yahoo hoặc IMAP tùy chỉnh) — máy chủ và cổng tự điền sẵn cho Gmail/Yahoo.",
                    "Xác thực: với Gmail nên chọn OAuth (bấm “Đăng nhập Google”) hoặc dùng “App Password” 16 ký tự (bật Xác minh 2 bước rồi tạo trong phần bảo mật của Google). KHÔNG dùng mật khẩu đăng nhập thường. Thông tin chỉ lưu trên máy này.",
                    "Chọn Thư mục cần quét: để INBOX nếu lấy hóa đơn MUA VÀO (cổng HĐĐT gửi về hộp thư); đổi thành [Gmail]/Sent Mail nếu lấy hóa đơn BÁN RA do bạn tự soạn email gửi khách.",
                    "App tự phân loại mua/bán theo MST đã khai ở Thông tin công ty (MST người bán trùng công ty → hóa đơn bán ra) — nhớ khai MST trước.",
                    "Bấm Kiểm tra kết nối để chắc chắn đăng nhập được, rồi bấm Lưu cấu hình.",
                    "Lấy thủ công: mở Bán hàng / Mua hàng rồi bấm “Lấy từ email”. Hoặc tích “Tự động kiểm tra hộp thư định kỳ” + đặt Chu kỳ (phút) để app tự tải nền.",
                    "App đọc file XML hóa đơn (kể cả khi XML nằm trong file .zip); PDF đính kèm được lưu để tra cứu. Email chỉ có PDF (vd đơn đặt hàng) sẽ bị bỏ qua.",
                    "Hóa đơn tải về là chứng từ nháp; đối tác/mặt hàng chưa có trong danh mục được gắn mã tạm và báo đỏ để bạn ánh xạ lại trước khi Ghi sổ.",
                    "Nút “Quét lại từ đầu” (trong Cấu hình email): đặt lại mốc quét về đầu hộp thư — dùng khi vừa đổi Thư mục. Chứng từ đã nhập sẽ được bỏ qua, không tạo trùng.",
                ),
            ),
            (
                "Dữ liệu mẫu (Demo) và làm sạch dữ liệu", "",
                (
                    "Vào Cấu hình › Dữ liệu mẫu (Demo).",
                    "Bấm “Nạp dữ liệu mẫu” để tạo sẵn một năm số liệu (khách hàng, NCC, hóa đơn mua/bán, tồn kho, tài sản, giá thành) — rồi mở Tổng quan / Báo cáo / Kho hàng để xem chương trình tính toán và tự kiểm chứng.",
                    "Bấm “Xóa toàn bộ dữ liệu” khi muốn bắt đầu nhập số liệu thật.",
                    "Cả hai thao tác đều xóa sạch dữ liệu đang có trước khi chạy, nhưng luôn GIỮ hệ thống tài khoản và thông tư đang chọn.",
                    "Sau khi nạp hoặc xóa, chỉ cần chuyển sang phân hệ khác là thấy số liệu cập nhật ngay.",
                ),
            ),
        ),
    ),
)


class _SectionBlock(QWidget):
    """A guide section: header row (label + "Mở …" link) + a stack of cards."""

    navigate = Signal(str)  # emits the module key when the quick-jump link is bấm

    def __init__(self, title: str, module_key: str | None = None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self._header = QLabel(title.upper())
        self._header.setObjectName("HelpSectionLabel")
        header_row.addWidget(self._header)
        header_row.addStretch(1)

        # A section tied to a tab gets a one-click jump straight to that phân hệ.
        if module_key and module_key in _TAB_LABELS:
            link = QPushButton(f"Mở {_TAB_LABELS[module_key]}  →")
            link.setObjectName("HelpOpenLink")
            link.setCursor(Qt.PointingHandCursor)
            link.clicked.connect(lambda: self.navigate.emit(module_key))
            header_row.addWidget(link)

        layout.addLayout(header_row)

        self._cards_layout = QVBoxLayout()
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        layout.addLayout(self._cards_layout)

        # (card widget, normalized haystack)
        self._entries: list[tuple[QWidget, str]] = []

    def add_entry(self, title: str, shortcut: str, steps: tuple[str, ...]) -> None:
        card = Card(title=title, subtitle=f"Phím tắt: {shortcut}" if shortcut else None)
        for step in steps:
            line = QLabel(f"•  {step}")
            line.setObjectName("HelpStep")
            line.setWordWrap(True)
            card.add(line)
        self._cards_layout.addWidget(card)

        haystack = _normalize(" ".join((title, shortcut, *steps)))
        self._entries.append((card, haystack))

    def filter(self, needle: str) -> bool:
        """Show/hide entries by match; return True if any remain visible."""
        any_visible = False
        for card, haystack in self._entries:
            visible = not needle or needle in haystack
            card.setVisible(visible)
            any_visible = any_visible or visible
        self.setVisible(any_visible)
        return any_visible


class HelpScreen(QWidget):
    # Forwarded from a section's "Mở …" link → ChromeWindow switches phân hệ.
    navigate_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("HelpScreen")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("Hướng dẫn sử dụng")
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Tra cứu cách dùng mọi tính năng. Gõ vào ô tìm kiếm để lọc ngay."
        )
        subtitle.setObjectName("ScreenSubtitle")
        root.addWidget(subtitle)

        self._search = IconInput(
            placeholder="Tìm tính năng… (vd: hóa đơn, chốt sổ, khấu hao)",
            icon_name="search",
        )
        self._search.text_changed.connect(self._on_search)
        root.addWidget(self._search)

        # Scrollable guide body.
        scroll = QScrollArea()
        scroll.setObjectName("HelpScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        container.setObjectName("HelpBody")
        body = QVBoxLayout(container)
        body.setContentsMargins(0, 4, 8, 4)
        body.setSpacing(18)

        self._sections: list[_SectionBlock] = []
        for section_title, module_key, entries in _GUIDE:
            block = _SectionBlock(section_title, module_key)
            block.navigate.connect(self.navigate_requested)
            for entry_title, shortcut, steps in entries:
                block.add_entry(entry_title, shortcut, steps)
            body.addWidget(block)
            self._sections.append(block)

        self._empty = QLabel("Không tìm thấy tính năng phù hợp.")
        self._empty.setObjectName("HelpEmpty")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.hide()
        body.addWidget(self._empty)

        body.addStretch(1)
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    def _on_search(self, text: str) -> None:
        needle = _normalize(text.strip())
        any_visible = False
        for section in self._sections:
            any_visible = section.filter(needle) or any_visible
        self._empty.setVisible(not any_visible)

    def on_activated(self) -> None:
        """Focus the search box each time the guide is opened."""
        self._search.setFocus()
        self._search.line_edit().selectAll()
