"""
Main tab - direct port of gui_main.py's _build_main_tab / _start_deployment /
_show_predeploy_confirmation / _poll_logs / _deployment_finished /
_show_deployment_results.

Deploy needs to know what's checked on the Apps/Backup/Activators/External
Scripts tabs, which live in sibling widgets. Rather than importing those tabs
directly (tight coupling both ways), MainWindow hands this tab a small
`context` object exposing getter callables after all tabs are constructed -
see main_window.py's _wire_context().
"""
from __future__ import annotations
import datetime
import logging
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QMessageBox,
    QAbstractItemView, QDialog
)

from ui_qt.confirm_dialog import ConfirmDeploymentDialog, op_queued_factory
from ui_qt.results_dialog import DeploymentResultsDialog

STATUS_ICONS = {'pending': '\u23f3', 'running': '\u25b6\ufe0f', 'success': '\u2705',
                 'failed': '\u274c', 'skipped': '\u23ed\ufe0f'}


class MainTab(QWidget):
    def __init__(self, config, catalog, install_engine, log_bus, is_admin: bool, context, parent=None):
        super().__init__(parent)
        self.config = config
        self.catalog = catalog
        self.install_engine = install_engine
        self.log_bus = log_bus
        self.is_admin = is_admin
        self.context = context  # AppContext, populated later by MainWindow

        self.selected_operations: list[str] = []
        self.available_ops = self.config.get_operations()

        self._build_ui()
        self.log_bus.message.connect(self._append_log)

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_logs)
        self._poll_timer.start(100)

    # ---------------- UI ----------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- operations queue ---
        ops_row = QHBoxLayout()

        avail_col = QVBoxLayout()
        avail_col.addWidget(QLabel("Available Operations"))
        self.list_available = QListWidget()
        self.list_available.setMaximumHeight(180)
        avail_col.addWidget(self.list_available)
        ops_row.addLayout(avail_col, stretch=1)

        btn_col = QVBoxLayout()
        btn_col.addStretch(1)
        add_all_btn = QPushButton("Add All")
        remove_all_btn = QPushButton("Remove All")
        add_btn = QPushButton("Add ->")
        remove_btn = QPushButton("<- Remove")
        up_btn = QPushButton("Move Up")
        down_btn = QPushButton("Move Down")
        for b in (add_all_btn, remove_all_btn, add_btn, remove_btn, up_btn, down_btn):
            b.setFixedWidth(110)
            btn_col.addWidget(b)
        btn_col.addStretch(1)
        ops_row.addLayout(btn_col, stretch=0)

        sel_col = QVBoxLayout()
        sel_col.addWidget(QLabel("Execution Order"))
        self.list_selected = QListWidget()
        self.list_selected.setMaximumHeight(180)
        sel_col.addWidget(self.list_selected)
        ops_row.addLayout(sel_col, stretch=1)

        layout.addLayout(ops_row)

        add_all_btn.clicked.connect(self._add_all_operations)
        remove_all_btn.clicked.connect(self._remove_all_operations)
        add_btn.clicked.connect(self._add_operation)
        remove_btn.clicked.connect(self._remove_operation)
        up_btn.clicked.connect(self._move_up)
        down_btn.clicked.connect(self._move_down)

        # --- deployment status ---
        status_label = QLabel("Deployment Status")
        status_label.setProperty("role", "heading")
        layout.addWidget(status_label)

        status_line = QHBoxLayout()
        cur_lbl = QLabel("Current Operation:")
        cur_lbl.setStyleSheet("font-weight:600;")
        status_line.addWidget(cur_lbl)
        self.current_op_label = QLabel("None")
        status_line.addWidget(self.current_op_label)
        status_line.addStretch(1)
        next_lbl = QLabel("Next Operation:")
        next_lbl.setStyleSheet("font-weight:600;")
        status_line.addWidget(next_lbl)
        self.next_op_label = QLabel("None")
        status_line.addWidget(self.next_op_label)
        layout.addLayout(status_line)

        self.status_table = QTableWidget(0, 3)
        self.status_table.setHorizontalHeaderLabels(["Status", "Operation", "Message"])
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.status_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.status_table.setMaximumHeight(160)
        header = self.status_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.status_table.setColumnWidth(0, 70)
        self.status_table.setColumnWidth(1, 200)
        layout.addWidget(self.status_table)

        # --- deploy / cancel ---
        deploy_row = QHBoxLayout()
        self.btn_deploy = QPushButton("Deploy")
        self.btn_deploy.setObjectName("Primary")
        self.btn_deploy.clicked.connect(self._start_deployment)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_deployment)
        deploy_row.addWidget(self.btn_deploy)
        deploy_row.addWidget(self.btn_cancel)
        deploy_row.addStretch(1)
        layout.addLayout(deploy_row)

        # --- log ---
        layout.addWidget(QLabel("Detailed Log"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text, stretch=1)

        self._refresh_available_list()
        self._refresh_selected_list()

    # ---------------- operations list ----------------
    def _refresh_available_list(self):
        self.list_available.clear()
        for op in self.available_ops:
            self.list_available.addItem(op.get('display', op.get('internal')))

    def _refresh_selected_list(self):
        self.list_selected.clear()
        display_by_internal = {op['internal']: op.get('display', op['internal']) for op in self.available_ops}
        for internal in self.selected_operations:
            self.list_selected.addItem(display_by_internal.get(internal, internal))

    def _add_operation(self):
        row = self.list_available.currentRow()
        if row < 0:
            return
        internal = self.available_ops[row]['internal']
        if internal not in self.selected_operations:
            self.selected_operations.append(internal)
            self._refresh_selected_list()

    def _remove_operation(self):
        row = self.list_selected.currentRow()
        if row < 0:
            return
        del self.selected_operations[row]
        self._refresh_selected_list()

    def _move_up(self):
        row = self.list_selected.currentRow()
        if row <= 0:
            return
        ops = self.selected_operations
        ops[row], ops[row - 1] = ops[row - 1], ops[row]
        self._refresh_selected_list()
        self.list_selected.setCurrentRow(row - 1)

    def _move_down(self):
        row = self.list_selected.currentRow()
        if row < 0 or row >= len(self.selected_operations) - 1:
            return
        ops = self.selected_operations
        ops[row], ops[row + 1] = ops[row + 1], ops[row]
        self._refresh_selected_list()
        self.list_selected.setCurrentRow(row + 1)

    def _add_all_operations(self):
        for op in self.available_ops:
            if op['internal'] not in self.selected_operations:
                self.selected_operations.append(op['internal'])
        self._refresh_selected_list()

    def _remove_all_operations(self):
        self.selected_operations.clear()
        self._refresh_selected_list()

    def refresh_operations_from_config(self):
        """Called after Settings closes, mirrors self.available_ops =
        self.config.get_operations(); self._refresh_available_list()."""
        self.available_ops = self.config.get_operations()
        self._refresh_available_list()

    # ---------------- logging & status polling ----------------
    def _append_log(self, text: str):
        self.log_text.moveCursor(QTextCursor.End)
        self.log_text.insertPlainText(text)
        self.log_text.ensureCursorVisible()

    def _update_status_panel(self):
        status_list = self.install_engine.status_list
        current_idx = self.install_engine.current_index
        next_idx = self.install_engine.next_index

        self.status_table.setRowCount(0)
        for item in status_list:
            icon = STATUS_ICONS.get(item['status'], '?')
            row = self.status_table.rowCount()
            self.status_table.insertRow(row)
            self.status_table.setItem(row, 0, QTableWidgetItem(icon))
            self.status_table.setItem(row, 1, QTableWidgetItem(item['display']))
            self.status_table.setItem(row, 2, QTableWidgetItem(item['message']))

        if 0 <= current_idx < len(status_list):
            d = status_list[current_idx]
            self.current_op_label.setText(f"{d['display']} ({d['status']})")
        else:
            self.current_op_label.setText("None")

        if 0 <= next_idx < len(status_list):
            self.next_op_label.setText(status_list[next_idx]['display'])
        else:
            self.next_op_label.setText("None")

    def _poll_logs(self):
        logs = self.install_engine.get_logs()
        for msg, level in logs:
            if level == 'STATUS':
                self._update_status_panel()
            else:
                prefix = ""
                if level == 'ERROR':
                    prefix = "[ERROR] "
                elif level == 'WARNING':
                    prefix = "[WARN] "
                self._append_log(prefix + msg + "\n")

    # ---------------- deployment controls ----------------
    def _start_deployment(self):
        if not self.selected_operations:
            QMessageBox.warning(self, "No Operations", "Please add operations to the execution order.")
            return

        if not self._show_predeploy_confirmation():
            return

        ctx = self.context
        self.install_engine.set_selected_activators(ctx.get_selected_activators())
        self.install_engine.set_external_scripts(ctx.get_checked_external_scripts())

        if ctx.get_restore_selected_only():
            checked_sources = ctx.get_checked_backup_sources()
            self.install_engine.restore_sources = checked_sources if checked_sources else None
        else:
            self.install_engine.restore_sources = None

        self.btn_deploy.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        self._append_log("Deployment started.\n")
        self.install_engine.set_operations(self.selected_operations)
        self.install_engine.start_deployment(on_finished=self._deployment_finished)
        self._update_status_panel()

    def _show_predeploy_confirmation(self) -> bool:
        op_display = {op['internal']: op.get('display', op['internal']) for op in self.available_ops}
        ops = self.selected_operations[:]
        op_queued = op_queued_factory(ops, op_display)
        ctx = self.context

        apps = []
        for a in self.catalog.apps:
            if not a.selected_provider:
                continue
            provider = a.selected_provider
            if provider == 'winget':
                if not op_queued('install winget apps'):
                    continue
            elif provider == 'choco':
                if not op_queued('install chocolatey apps'):
                    continue
            elif provider == 'offline':
                itype = (getattr(a, 'install_type', '') or '').lower()
                if itype == 'silent':
                    if not op_queued('install silent apps'):
                        continue
                elif itype in ('non_silent', 'non-silent', 'nonsilent', 'non silent'):
                    if not op_queued('install non-silent apps'):
                        continue
                elif itype == 'driver':
                    if not op_queued('install drivers'):
                        continue
                else:
                    if not op_queued('install silent apps', 'install non-silent apps', 'install drivers'):
                        continue
            apps.append((a.display_name, provider))

        tweaks = []
        if op_queued('apply tweaks'):
            tweaks = [
                (t.get('name', ''), t.get('selected_action'), t.get('category', ''))
                for t in self.config.tweaks.get('tweaks', [])
                if t.get('selected_action')
            ]

        activators = []
        if op_queued('run activators'):
            activators = [(a['name'], a.get('switches', '')) for a in ctx.get_selected_activators()]

        ext_scripts = []
        if op_queued('run external scripts'):
            ext_scripts = ctx.get_checked_external_scripts()

        is_restore = op_queued('restore backup')
        backup_info = None
        if is_restore:
            backup_file = ctx.get_backup_filename()
            if ctx.get_restore_selected_only():
                checked = ctx.get_checked_backup_sources()
                backup_info = (backup_file, checked)
            else:
                backup_info = (backup_file, None)

        choco_needs_elevation = not self.is_admin and any(p == 'choco' for _, p in apps)

        dlg = ConfirmDeploymentDialog(
            self, ops, op_display, apps, tweaks, activators, ext_scripts,
            backup_info, choco_needs_elevation
        )
        return dlg.exec() == QDialog.Accepted

    def _deployment_finished(self):
        from ui_qt.thread_utils import run_on_main_thread

        def finish():
            self.btn_deploy.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self._append_log("Deployment finished.\n")
            self._update_status_panel()
            self._show_deployment_results()

        run_on_main_thread(finish)

    def _generate_report(self, title="Deployment Report"):
        from modules.report_builder import build_deployment_report
        if self.install_engine.results.is_empty():
            return None
        reports_dir = os.path.join(self.config.base_dir, 'reports')
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
        report_path = os.path.join(reports_dir, f'report_{timestamp}.html')
        session_logger = logging.getLogger('DeploymentKit')
        json_log_path = getattr(session_logger, 'log_file_path', None)
        return build_deployment_report(
            self.install_engine.results, report_path,
            json_log_path=json_log_path, title=title,
        )

    def _show_deployment_results(self):
        results = self.install_engine.results
        if results.is_empty():
            return
        report_path = self._generate_report()
        dlg = DeploymentResultsDialog(
            self, self.install_engine, report_path,
            regenerate_report_callback=lambda: self._generate_report(
                title="Deployment Report (includes retries)"),
            log_callback=self._append_log,
        )
        dlg.exec()

    def _cancel_deployment(self):
        self.install_engine.cancel()
        self._append_log("Cancel requested. Waiting for current task to finish...\n")
        self.btn_cancel.setEnabled(False)
