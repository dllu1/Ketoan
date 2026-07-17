"""Invoice repository: SQLite access for sales invoices + their lines."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from data.database import get_connection
from domain.models.invoice import (
    Invoice,
    InvoiceKind,
    InvoiceLine,
    InvoiceStatus,
    PaymentMethod,
)


def _row_to_invoice(row: sqlite3.Row) -> Invoice:
    return Invoice(
        id=row["id"],
        ref=row["ref"],
        invoice_no=row["invoice_no"],
        serial=row["serial"],
        invoice_date=date.fromisoformat(str(row["invoice_date"])),
        kind=InvoiceKind(row["kind"]),
        status=InvoiceStatus(row["status"]),
        payment_method=PaymentMethod(row["payment_method"]),
        partner_code=row["partner_code"],
        partner_name=row["partner_name"],
        partner_tax_code=row["partner_tax_code"],
        partner_address=row["partner_address"],
        description=row["description"],
        debit_account=row["debit_account"],
        credit_account=row["credit_account"],
        source=row["source"],
        attachment_path=row["attachment_path"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _row_to_line(row: sqlite3.Row) -> InvoiceLine:
    return InvoiceLine(
        id=row["id"],
        invoice_id=row["invoice_id"],
        line_no=row["line_no"],
        item_code=row["item_code"],
        item_name=row["item_name"],
        unit=row["unit"],
        quantity=Decimal(str(row["quantity"])),
        unit_price=Decimal(str(row["unit_price"])),
        vat_rate=Decimal(str(row["vat_rate"])),
        account_code=row["account_code"],
        debit_account=row["debit_account"],
        credit_account=row["credit_account"],
    )


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class InvoiceRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_all(self, kind: InvoiceKind | None = None) -> list[Invoice]:
        sql = "SELECT * FROM invoice"
        params: tuple = ()
        if kind is not None:
            sql += " WHERE kind = ?"
            params = (kind.value,)
        sql += " ORDER BY invoice_date DESC, id DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return self._attach_lines([_row_to_invoice(r) for r in rows])

    def search(self, query: str, kind: InvoiceKind | None = None) -> list[Invoice]:
        if not query:
            return self.list_all(kind)
        like = f"%{query}%"
        sql = (
            "SELECT * FROM invoice WHERE (ref LIKE ? OR invoice_no LIKE ? "
            "OR partner_name LIKE ? OR partner_code LIKE ?)"
        )
        params: tuple = (like, like, like, like)
        if kind is not None:
            sql += " AND kind = ?"
            params += (kind.value,)
        sql += " ORDER BY invoice_date DESC, id DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return self._attach_lines([_row_to_invoice(r) for r in rows])

    def list_lines(self, invoice_id: int) -> list[InvoiceLine]:
        rows = self._conn.execute(
            "SELECT * FROM invoice_line WHERE invoice_id = ? ORDER BY line_no",
            (invoice_id,),
        ).fetchall()
        return [_row_to_line(r) for r in rows]

    def find_by_ref(self, ref: str) -> Invoice | None:
        row = self._conn.execute(
            "SELECT * FROM invoice WHERE ref = ?", (ref,)
        ).fetchone()
        return self._hydrate(_row_to_invoice(row)) if row else None

    def insert(self, invoice: Invoice) -> Invoice:
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO invoice (
                    ref, invoice_no, serial, invoice_date, kind, status,
                    payment_method, partner_code, partner_name,
                    partner_tax_code, partner_address, description,
                    debit_account, credit_account, source, attachment_path,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    invoice.ref, invoice.invoice_no, invoice.serial,
                    invoice.invoice_date.isoformat(), invoice.kind.value,
                    invoice.status.value,
                    invoice.payment_method.value, invoice.partner_code,
                    invoice.partner_name, invoice.partner_tax_code,
                    invoice.partner_address, invoice.description,
                    invoice.debit_account, invoice.credit_account,
                    invoice.source, invoice.attachment_path,
                    invoice.created_at.isoformat(),
                    invoice.updated_at.isoformat(),
                ),
            )
            invoice.id = cursor.lastrowid
            self._insert_lines(invoice)
        return invoice

    def update(self, invoice: Invoice) -> Invoice:
        with self._conn:
            self._conn.execute(
                """
                UPDATE invoice SET
                    ref = ?, invoice_no = ?, serial = ?, invoice_date = ?,
                    kind = ?, status = ?, payment_method = ?, partner_code = ?,
                    partner_name = ?, partner_tax_code = ?, partner_address = ?,
                    description = ?, debit_account = ?, credit_account = ?,
                    source = ?, attachment_path = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    invoice.ref, invoice.invoice_no, invoice.serial,
                    invoice.invoice_date.isoformat(), invoice.kind.value,
                    invoice.status.value,
                    invoice.payment_method.value, invoice.partner_code,
                    invoice.partner_name, invoice.partner_tax_code,
                    invoice.partner_address, invoice.description,
                    invoice.debit_account, invoice.credit_account,
                    invoice.source, invoice.attachment_path,
                    invoice.updated_at.isoformat(), invoice.id,
                ),
            )
            self._conn.execute(
                "DELETE FROM invoice_line WHERE invoice_id = ?", (invoice.id,)
            )
            self._insert_lines(invoice)
        return invoice

    def delete(self, invoice_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM invoice WHERE id = ?", (invoice_id,))

    # ----- helpers ----------------------------------------------------------

    def _hydrate(self, invoice: Invoice) -> Invoice:
        invoice.lines = self.list_lines(invoice.id)
        return invoice

    def _attach_lines(self, invoices: list[Invoice]) -> list[Invoice]:
        """Nạp dòng cho nhiều hóa đơn bằng truy vấn gộp (tránh N+1).

        Báo cáo thuế GTGT duyệt mọi hóa đơn đã ghi sổ; nạp từng dòng cho từng hóa
        đơn (cũ) tạo 1+N query. Gộp lại còn 2 query, chia lô IN(...) cho an toàn.
        """
        by_id = {inv.id: inv for inv in invoices}
        for invoice in invoices:
            invoice.lines = []
        ids = list(by_id)
        for start in range(0, len(ids), 900):
            chunk = ids[start:start + 900]
            placeholders = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                f"SELECT * FROM invoice_line WHERE invoice_id IN ({placeholders}) "
                "ORDER BY invoice_id, line_no",
                tuple(chunk),
            ).fetchall()
            for line_row in rows:
                by_id[line_row["invoice_id"]].lines.append(_row_to_line(line_row))
        return invoices

    def _insert_lines(self, invoice: Invoice) -> None:
        for index, line in enumerate(invoice.lines):
            line.invoice_id = invoice.id
            line.line_no = index
            self._conn.execute(
                """
                INSERT INTO invoice_line (
                    invoice_id, line_no, item_code, item_name, unit,
                    quantity, unit_price, vat_rate, account_code,
                    debit_account, credit_account
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    invoice.id, index, line.item_code, line.item_name,
                    line.unit, str(line.quantity), str(line.unit_price),
                    str(line.vat_rate), line.account_code,
                    line.debit_account, line.credit_account,
                ),
            )
