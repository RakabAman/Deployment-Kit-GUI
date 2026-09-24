"""
General / Operations / Command Templates settings tabs - port of
settings_dialog.py's _build_general_tab / _build_operations_tab /
_build_commands_tab. These three are the simplest sub-tabs (no CRUD dialogs).
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QScrollArea
)


class GeneralSettingsTab(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        general = self.config.settings.setdefault('general', {})

        layout = QGridLayout(self)
        layout.addWidget(QLabel("Default Online Provider:"), 0, 0)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(['winget', 'chocolatey'])
        idx = self.provider_combo.findText(general.get('default_provider', 'winget'))
        self.provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addWidget(self.provider_combo, 0, 1)

        layout.addWidget(QLabel("Log Level:"), 1, 0)
        self.log_combo = QComboBox()
        self.log_combo.addItems(['verbose', 'normal', 'errors'])
        idx = self.log_combo.findText(general.get('log_level', 'verbose'))
        self.log_combo.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addWidget(self.log_combo, 1, 1)

        layout.addWidget(QLabel("Archive Format:"), 2, 0)
        self.archive_combo = QComboBox()
        self.archive_combo.addItems(['zip', '7z'])
        idx = self.archive_combo.findText(general.get('archive_format', 'zip'))
        self.archive_combo.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addWidget(self.archive_combo, 2, 1)

        layout.addWidget(QLabel("Backup Destination:"), 3, 0)
        self.backup_edit = QLineEdit(general.get('backup_destination', 'backups'))
        layout.addWidget(self.backup_edit, 3, 1)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_backup)
        layout.addWidget(browse_btn, 3, 2)

        save_btn = QPushButton("Save General Settings")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn, 4, 0, 1, 2)
        layout.setRowStretch(5, 1)

    def _browse_backup(self):
        path = QFileDialog.getExistingDirectory(self, "Select backup destination")
        if path:
            self.backup_edit.setText(path)

    def _save(self):
        general = self.config.settings.setdefault('general', {})
        general['default_provider'] = self.provider_combo.currentText()
        general['log_level'] = self.log_combo.currentText()
        general['archive_format'] = self.archive_combo.currentText()
        general['backup_destination'] = self.backup_edit.text()
        self.config.save_settings()
        QMessageBox.information(self, "Saved", "General settings saved.")


class OperationsSettingsTab(QWidget):
    def __init__(self, config, on_saved, parent=None):
        super().__init__(parent)
        self.config = config
        self.on_saved = on_saved
        self.checkboxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        ops = self.config.settings.get('available_operations', [])
        for op in ops:
            cb = QCheckBox(op.get('display', op.get('internal')))
            cb.setChecked(op.get('enabled', True))
            self.checkboxes[op['internal']] = cb
            layout.addWidget(cb)

        save_btn = QPushButton("Save Operations")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)
        layout.addStretch(1)

    def _save(self):
        ops = self.config.settings.get('available_operations', [])
        for op in ops:
            if op['internal'] in self.checkboxes:
                op['enabled'] = self.checkboxes[op['internal']].isChecked()
        self.config.save_settings()
        QMessageBox.information(self, "Saved", "Operations configuration saved.")
        if self.on_saved:
            self.on_saved()


class CommandTemplatesTab(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.entries: dict[str, QLineEdit] = {}

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QGridLayout(inner)
        scroll.setWidget(inner)
        outer.addWidget(scroll, stretch=1)

        templates = self.config.settings.get('command_templates', {})
        row = 0
        for key, value in templates.items():
            layout.addWidget(QLabel(key.replace('_', ' ').title() + ":"), row, 0)
            edit = QLineEdit(value)
            layout.addWidget(edit, row, 1)
            self.entries[key] = edit
            row += 1
        layout.setRowStretch(row, 1)

        save_btn = QPushButton("Save Templates")
        save_btn.clicked.connect(self._save)
        outer.addWidget(save_btn)

    def _save(self):
        templates = {key: edit.text() for key, edit in self.entries.items()}
        self.config.settings['command_templates'] = templates
        self.config.save_settings()
        QMessageBox.information(self, "Saved", "Command templates saved.")
