"""
Deployment Results dialog: summary counts, per-item outcomes, "Open Full
Report", and "Retry Failed" (which re-runs install_engine.start_retry and
refreshes this same table in place).
"""
import os
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QMessageBox
)


class DeploymentResultsDialog(QDialog):
    def __init__(self, parent, install_engine, report_path: str | None,
                 regenerate_report_callback, log_callback):
        super().__init__(parent)
        self.install_engine = install_engine
        self.results = install_engine.results
        self.report_path = report_path
        self._regenerate_report = regenerate_report_callback
        self._log = log_callback

        self.setWindowTitle("Deployment Results")
        self.resize(780, 480)

        layout = QVBoxLayout(self)

        counts = self.results.counts()
        summary = QHBoxLayout()
        total_lbl = QLabel(f"Total: {len(self.results.items)}")
        total_lbl.setProperty("role", "heading")
        summary.addWidget(total_lbl)
        ok_lbl = QLabel(f"Succeeded: {counts.get('success', 0)}")
        ok_lbl.setStyleSheet("color:#2ea043; font-weight:600;")
        summary.addWidget(ok_lbl)
        fail_lbl = QLabel(f"Failed: {counts.get('failed', 0)}")
        fail_lbl.setStyleSheet("color:#c0392b; font-weight:600;")
        summary.addWidget(fail_lbl)
        skip_lbl = QLabel(f"Skipped: {counts.get('skipped', 0)}")
        skip_lbl.setStyleSheet("color:#d29922; font-weight:600;")
        summary.addWidget(skip_lbl)
        summary.addStretch(1)
        layout.addLayout(summary)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Category", "Name", "Status", "Message"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 80)
        layout.addWidget(self.table, stretch=1)

        self._populate()

        btn_row = QHBoxLayout()
        self.retry_btn = QPushButton("Retry Failed")
        self.retry_btn.clicked.connect(self._do_retry)
        self.retry_btn.setEnabled(bool(self.results.retryable_failed_items()))
        btn_row.addWidget(self.retry_btn)

        open_btn = QPushButton("Open Full Report")
        open_btn.clicked.connect(self._open_report)
        btn_row.addWidget(open_btn)

        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _populate(self):
        self.table.setRowCount(0)
        for item in self.results.items:
            label, _ = item.badge()
            one_line_msg = (item.message or "").splitlines()[0] if item.message else ""
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(item.category))
            self.table.setItem(row, 1, QTableWidgetItem(item.name))
            self.table.setItem(row, 2, QTableWidgetItem(label))
            self.table.setItem(row, 3, QTableWidgetItem(one_line_msg))

    def _open_report(self):
        if self.report_path and os.path.exists(self.report_path):
            webbrowser.open(f'file://{os.path.abspath(self.report_path)}')
        else:
            QMessageBox.information(self, "Report", "No report file was generated for this run.")

    def _do_retry(self):
        retryable = self.results.retryable_failed_items()
        if not retryable:
            QMessageBox.information(self, "Retry Failed", "There's nothing retryable to run again.")
            return
        self.retry_btn.setEnabled(False)
        self._log(f"Retrying {len(retryable)} failed item(s)...\n")

        def on_retry_finished():
            def finish_ui():
                self._populate()
                self.retry_btn.setEnabled(True)
                self._log("Retry finished.\n")
                self.report_path = self._regenerate_report()
            from ui_qt.thread_utils import run_on_main_thread
            run_on_main_thread(finish_ui)

        started = self.install_engine.start_retry(retryable, on_finished=on_retry_finished)
        if not started:
            self.retry_btn.setEnabled(True)
            QMessageBox.warning(self, "Retry Failed",
                                 "Couldn't start a retry - a deployment/retry may already be running.")
