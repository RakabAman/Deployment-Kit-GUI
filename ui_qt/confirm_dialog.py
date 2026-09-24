"""
Confirm Deployment dialog - shows everything actually queued to run (each
section gated by whether its matching operation is in the Execution Order,
same fix that was applied to the Tkinter version) with callouts on anything
irreversible or elevation-sensitive.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QDialogButtonBox
)


def op_queued_factory(ops: list[str], op_display: dict[str, str]):
    sel = {op_display.get(internal, internal).strip().lower() for internal in ops}

    def op_queued(*exact_texts):
        return any(t in sel for t in exact_texts)

    return op_queued


class ConfirmDeploymentDialog(QDialog):
    def __init__(self, parent, ops: list[str], op_display: dict[str, str],
                 apps: list[tuple[str, str]],
                 tweaks: list[tuple[str, str, str]],
                 activators: list[tuple[str, str]],
                 ext_scripts: list[dict],
                 backup_info: tuple[str, list | None] | None,
                 choco_needs_elevation: bool):
        super().__init__(parent)
        self.setWindowTitle("Confirm Deployment")
        self.resize(650, 560)
        self.setModal(True)

        layout = QVBoxLayout(self)

        header = QLabel("Review everything queued below before deploying.")
        header.setProperty("role", "heading")
        layout.addWidget(header)

        body = QTextEdit()
        body.setReadOnly(True)
        layout.addWidget(body, stretch=1)

        html = []

        def section(title, warn=False):
            color = "#c0392b" if warn else "#1a1a1a"
            html.append(f'<p style="margin-top:10px;margin-bottom:2px;">'
                        f'<b style="color:{color};">{title}</b></p>')

        def line(text, warn=False):
            color = "color:#c0392b;" if warn else ""
            html.append(f'<div style="margin-left:14px;{color}">&bull; {text}</div>')

        section("Execution order:")
        if ops:
            for i, internal in enumerate(ops, 1):
                html.append(f'<div style="margin-left:14px;">{i}. {op_display.get(internal, internal)}</div>')
        else:
            html.append('<div style="margin-left:14px;">(none)</div>')

        if apps:
            section(f"Apps to install ({len(apps)}):")
            for name, provider in apps:
                line(f"{name} \u2014 via {provider}")

        if tweaks:
            section(f"Tweaks to apply ({len(tweaks)}):")
            for name, action, category in tweaks:
                suffix = f" ({category})" if category else ""
                line(f"{name} \u2014 {action}{suffix}")

        if activators:
            section("\u26a0 Activators to run \u2014 modifies system licensing state:", warn=True)
            for name, switches in activators:
                text = name + (f" (switches: {switches})" if switches else "")
                line(text, warn=True)

        if ext_scripts:
            section(f"\u26a0 External scripts to run ({len(ext_scripts)}) \u2014 "
                    f"arbitrary code, review before deploying:", warn=True)
            for s in ext_scripts:
                line(f"{s.get('name', '(unnamed)')} [{s.get('type', '')}]", warn=True)

        if backup_info is not None:
            backup_file, checked = backup_info
            section("\u26a0 Restore \u2014 overwrites existing files at the restored paths:", warn=True)
            line(f"Backup: {backup_file or '(none selected)'}", warn=True)
            if checked is None:
                line("Scope: full restore (all sources)", warn=True)
            elif checked:
                line(f"Scope: {len(checked)} selected source(s)", warn=True)
                for src in checked:
                    html.append(f'<div style="margin-left:28px;color:#c0392b;">- {src}</div>')
            else:
                line("Scope: none selected (only protected special sources)", warn=True)

        if choco_needs_elevation:
            html.append('<p style="color:#c0392b;">\u26a0 Not running elevated \u2014 Chocolatey installs '
                         'will likely fail without Administrator rights.</p>')

        if not any([apps, tweaks, activators, ext_scripts, backup_info]):
            html.append('<p style="color:#c0392b;">Nothing is selected within these operations \u2014 running '
                         'this will do little or nothing. Consider selecting apps/tweaks/activators/scripts '
                         'first, or Cancel.</p>')

        body.setHtml("".join(html))

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        deploy_btn = QPushButton("Deploy")
        deploy_btn.setObjectName("Primary")
        cancel_btn.clicked.connect(self.reject)
        deploy_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(deploy_btn)
        layout.addLayout(btn_row)
