"""Reporting & export layer (Phase 4).

:mod:`report_tables` turns the value objects from
:mod:`domain.models.report` into a presentation-neutral :class:`ReportDocument`
(title, subtitle, tables). The same document drives the on-screen table view and
both the Excel and PDF exporters, so a report is laid out in exactly one place.
"""
