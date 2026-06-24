"""
DeploymentGUI - Main window with tabs: Main (orchestration), Install Selection, Backup/Restore.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import os
import datetime
from modules.config_manager import ConfigManager
from modules.app_catalog import AppCatalog
from modules.backup_engine import BackupEngine
from modules.install_engine import InstallEngine
from modules.settings_dialog import SettingsDialog

class DeploymentGUI:
    def __init__(self, root, is_admin):
        self.root = root
        self.is_admin = is_admin

        self.config = ConfigManager()
        self.catalog = AppCatalog(self.config)
        self.catalog.refresh()

        self.backup_engine = BackupEngine(self.config)
        self.install_engine = InstallEngine(self.catalog, self.backup_engine, self.config)

        self.selected_operations = []
        self.available_ops = self.config.get_operations()
        
        self.external_scripts = []  # list of script dicts

        self._build_ui()
        self._poll_logs()

    def _build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.tab_main = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_main, text="Main")

        self.tab_install = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_install, text="Apps")

        self.tab_backup = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_backup, text="Backup / Restore")

        self.tab_tweaks = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_tweaks, text="Tweaks")

        self.tab_activators = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_activators, text="Activators")

        self.tab_external = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_external, text="External Scripts")
        
        
        self._build_main_tab()
        self._build_install_tab()
        self._build_backup_tab()
        self._build_tweaks_tab()
        self._build_activators_tab()
        self._build_external_tab()

        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Settings", command=self._open_settings)
        menubar.add_cascade(label="Settings", menu=settings_menu)

        self.root.config(menu=menubar)

        status = "Administrator" if self.is_admin else "Lower Rights"
        self.status_label = ttk.Label(self.root, text=f"Running with: {status}")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    # ------------------ Main Tab ------------------
    def _build_main_tab(self):
        frame = self.tab_main

        paned = ttk.PanedWindow(frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.X, expand=False, padx=5, pady=5)

        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        ttk.Label(left_frame, text="Available Operations").pack(anchor='w')
        LISTBOX_HEIGHT = 10
        self.list_available = tk.Listbox(left_frame, selectmode=tk.SINGLE, height=LISTBOX_HEIGHT)
        self.list_available.pack(fill=tk.X, expand=False, pady=5)
        self._refresh_available_list()

        center_frame = ttk.Frame(paned, width=80)
        paned.add(center_frame, weight=0)
        ttk.Button(center_frame, text="Add All", command=self._add_all_operations).pack(pady=(20,2))
        ttk.Button(center_frame, text="Remove All", command=self._remove_all_operations).pack(pady=2)
        ttk.Button(center_frame, text="Add ->", command=self._add_operation).pack(pady=2)
        ttk.Button(center_frame, text="<- Remove", command=self._remove_operation).pack(pady=2)
        ttk.Button(center_frame, text="Move Up", command=self._move_up).pack(pady=2)
        ttk.Button(center_frame, text="Move Down", command=self._move_down).pack(pady=2)

        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
        ttk.Label(right_frame, text="Execution Order").pack(anchor='w')
        self.list_selected = tk.Listbox(right_frame, selectmode=tk.SINGLE, height=LISTBOX_HEIGHT)
        self.list_selected.pack(fill=tk.X, expand=False, pady=5)
        self._refresh_selected_list()

        status_frame = ttk.LabelFrame(frame, text="Deployment Status", padding=5)
        status_frame.pack(fill=tk.X, padx=5, pady=5)

        # Status frame
        status_frame = ttk.LabelFrame(frame, text="Deployment Status", padding=5)
        status_frame.pack(fill=tk.X, padx=5, pady=5)

        # Simple one-line status with Current and Next
        status_line = ttk.Frame(status_frame)
        status_line.pack(fill=tk.X, pady=2)

        # Current Operation
        ttk.Label(status_line, text="Current Operation:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=5)
        self.current_op_label = ttk.Label(status_line, text="None", font=('Arial', 9))
        self.current_op_label.pack(side=tk.LEFT, padx=5)

        # Spacer - pushes next operation to the right
        spacer = ttk.Frame(status_line)
        spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Next Operation
        ttk.Label(status_line, text="Next Operation:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=5)
        self.next_op_label = ttk.Label(status_line, text="None", font=('Arial', 9), width=45)
        self.next_op_label.pack(side=tk.LEFT, padx=5)

        # Separator line (below the status line)
        ttk.Separator(status_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Treeview for operation status list (unchanged)
        tree_frame = ttk.Frame(status_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        # ... rest of your code ...

        tree_frame = ttk.Frame(status_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.status_tree = ttk.Treeview(tree_frame, columns=('status', 'operation', 'message'), show='headings', height=6)
        self.status_tree.heading('status', text='Status')
        self.status_tree.heading('operation', text='Operation')
        self.status_tree.heading('message', text='Message')

        STATUS_COL_WIDTHS = {'status': 80, 'operation': 180, 'message': 350}
        self.status_tree.column('status', width=STATUS_COL_WIDTHS['status'], anchor='center', stretch=False)
        self.status_tree.column('operation', width=STATUS_COL_WIDTHS['operation'], anchor='w', stretch=False)
        self.status_tree.column('message', width=STATUS_COL_WIDTHS['message'], anchor='w', stretch=False)

        self.status_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        status_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.status_tree.yview)
        status_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_tree.configure(yscrollcommand=status_scroll.set)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        self.btn_deploy = ttk.Button(btn_frame, text="Deploy", command=self._start_deployment)
        self.btn_deploy.pack(side=tk.LEFT, padx=5)
        self.btn_cancel = ttk.Button(btn_frame, text="Cancel", command=self._cancel_deployment, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=5)

        ttk.Label(frame, text="Detailed Log").pack(anchor='w', padx=5)
        self.log_text = scrolledtext.ScrolledText(frame, height=12, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _refresh_available_list(self):
        self.list_available.delete(0, tk.END)
        for op in self.available_ops:
            self.list_available.insert(tk.END, op.get('display', op.get('internal')))

    def _refresh_selected_list(self):
        self.list_selected.delete(0, tk.END)
        for internal in self.selected_operations:
            for op in self.available_ops:
                if op['internal'] == internal:
                    self.list_selected.insert(tk.END, op.get('display', internal))
                    break
            else:
                self.list_selected.insert(tk.END, internal)

    def _add_operation(self):
        selection = self.list_available.curselection()
        if not selection:
            return
        idx = selection[0]
        op = self.available_ops[idx]
        internal = op['internal']
        if internal not in self.selected_operations:
            self.selected_operations.append(internal)
            self._refresh_selected_list()

    def _remove_operation(self):
        selection = self.list_selected.curselection()
        if not selection:
            return
        idx = selection[0]
        del self.selected_operations[idx]
        self._refresh_selected_list()

    def _move_up(self):
        selection = self.list_selected.curselection()
        if not selection or selection[0] == 0:
            return
        idx = selection[0]
        self.selected_operations[idx], self.selected_operations[idx-1] = self.selected_operations[idx-1], self.selected_operations[idx]
        self._refresh_selected_list()
        self.list_selected.selection_set(idx-1)

    def _move_down(self):
        selection = self.list_selected.curselection()
        if not selection or selection[0] >= len(self.selected_operations)-1:
            return
        idx = selection[0]
        self.selected_operations[idx], self.selected_operations[idx+1] = self.selected_operations[idx+1], self.selected_operations[idx]
        self._refresh_selected_list()
        self.list_selected.selection_set(idx+1)

    def _add_all_operations(self):
        """Move all available operations to the execution order."""
        for op in self.available_ops:
            internal = op['internal']
            if internal not in self.selected_operations:
                self.selected_operations.append(internal)
        self._refresh_selected_list()

    def _remove_all_operations(self):
        """Clear the execution order."""
        self.selected_operations.clear()
        self._refresh_selected_list()
        
        
    # ---------- Status Update Methods ----------
    def _update_status_panel(self):
        try:
            status_list = self.install_engine.status_list
            current_idx = self.install_engine.current_index
            next_idx = self.install_engine.next_index

            for item in self.status_tree.get_children():
                self.status_tree.delete(item)

            status_icons = {'pending': '⏳', 'running': '▶️', 'success': '✅', 'failed': '❌', 'skipped': '⏭️'}
            for i, item in enumerate(status_list):
                icon = status_icons.get(item['status'], '?')
                self.status_tree.insert('', 'end', values=(icon, item['display'], item['message']))

            if current_idx >= 0 and current_idx < len(status_list):
                current_display = status_list[current_idx]['display']
                current_status = status_list[current_idx]['status']
                self.current_op_label.config(text=f"{current_display} ({current_status})")
            else:
                self.current_op_label.config(text="None")

            if next_idx >= 0 and next_idx < len(status_list):
                self.next_op_label.config(text=status_list[next_idx]['display'])
            else:
                self.next_op_label.config(text="None")

        except Exception as e:
            print(f"Status panel update error: {e}")

    # ------------------ Install Tab ------------------
    def _build_install_tab(self):
        self.install_frame = self.tab_install

        filter_frame = ttk.Frame(self.install_frame)
        filter_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Label(filter_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self._refresh_install_tab())
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="Filter by Type:").pack(side=tk.LEFT, padx=15)
        filter_types = ['All', 'Silent', 'Non-Silent', 'Driver', 'Script', 'Redist']
        self.filter_var = tk.StringVar(value='All')
        filter_combo = ttk.Combobox(filter_frame, textvariable=self.filter_var, values=filter_types, state='readonly', width=14)
        filter_combo.pack(side=tk.LEFT, padx=5)
        filter_combo.bind('<<ComboboxSelected>>', lambda e: self._refresh_install_tab())

        ttk.Button(filter_frame, text="Refresh Versions", command=self._refresh_versions).pack(side=tk.RIGHT, padx=5)

        self.install_container = ttk.Frame(self.install_frame)
        self.install_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.app_radio_vars = {}
        self.version_labels = {}

        self._refresh_install_tab()

    def _refresh_install_tab(self):
        for widget in self.install_container.winfo_children():
            widget.destroy()

        self.catalog.refresh()
        search_text = self.search_var.get().strip().lower()
        filter_type = self.filter_var.get().lower()

        main_frame = tk.Frame(self.install_container, bg='white')
        main_frame.pack(fill=tk.BOTH, expand=True)

        header_frame = tk.Frame(main_frame, bg='white')
        header_frame.pack(fill=tk.X, pady=(0, 4))

        col_widths = {
            'name': 250, 'category': 130, 'type': 80, 'none': 60,
            'offline': 130, 'winget': 180, 'choco': 180
        }
        col_keys = ['name', 'category', 'type', 'none', 'offline', 'winget', 'choco']
        col_key_display = {
            'name': 'App Name', 'category': 'Category', 'type': 'Type',
            'none': 'None', 'offline': 'Offline', 'winget': 'Winget', 'choco': 'Choco'
        }

        for i, key in enumerate(col_keys):
            header_frame.columnconfigure(i, weight=0, minsize=col_widths[key])
        header_frame.columnconfigure(7, weight=1)

        for i, key in enumerate(col_keys):
            ttk.Label(header_frame, text=col_key_display[key],
                      font=('Arial', 10, 'bold'), anchor='w', background='white') \
                .grid(row=0, column=i, padx=4, sticky='w')

        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        canvas_container = tk.Frame(main_frame, bg='white')
        canvas_container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(canvas_container, highlightthickness=0, bg='white')
        scrollbar = ttk.Scrollbar(canvas_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='white')

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.version_labels = {}
        self.app_radio_vars = {}

        row = 0
        for app in self.catalog.apps:
            if search_text and search_text not in app.display_name.lower():
                continue
            if filter_type != 'all' and app.install_type != filter_type:
                continue

            default = -1
            if app.selected_provider == 'offline':
                default = 0
            elif app.selected_provider == 'winget':
                default = 1
            elif app.selected_provider == 'choco':
                default = 2
            if default == -1 and app.is_offline_available and app.offline_path:
                default = 0
                app.selected_provider = 'offline'

            row_frame = tk.Frame(scrollable_frame, bg='white')
            row_frame.grid(row=row, column=0, columnspan=8, sticky='w', pady=1)

            ttk.Label(row_frame, text=app.display_name, anchor='w',
                      font=('Arial', 9), width=col_widths['name']//7, background='white') \
                .grid(row=0, column=0, padx=4, sticky='w')

            ttk.Label(row_frame, text=app.category or "Uncategorized", anchor='w',
                      font=('Arial', 9), width=col_widths['category']//8, background='white') \
                .grid(row=0, column=1, padx=(5,4), sticky='w')

            type_display = app.install_type.capitalize()
            if app.install_type == 'non_silent':
                type_display = 'Non-Silent'
            ttk.Label(row_frame, text=type_display, anchor='w',
                      font=('Arial', 9), width=col_widths['type']//8, background='white') \
                .grid(row=0, column=2, padx=4, sticky='w')

            provider_var = tk.IntVar(value=default)
            self.app_radio_vars[app.display_name] = provider_var

            none_frame = tk.Frame(row_frame, bg='white')
            none_frame.grid(row=0, column=3, padx=(10,4), sticky='w')
            rb_none = ttk.Radiobutton(none_frame, variable=provider_var, value=-1,
                                      command=lambda a=app, v=provider_var: self._set_provider(a, v))
            rb_none.pack(side=tk.LEFT)

            offline_frame = tk.Frame(row_frame, bg='white')
            offline_frame.grid(row=0, column=4, padx=4, sticky='w')
            rb_offline = ttk.Radiobutton(offline_frame, variable=provider_var, value=0,
                                         command=lambda a=app, v=provider_var: self._set_provider(a, v))
            rb_offline.pack(side=tk.LEFT, padx=(30, 2))
            if not app.is_offline_available or not app.offline_path:
                rb_offline.config(state=tk.DISABLED)
            offline_ver_label = ttk.Label(offline_frame, text=app.offline_version or "N/A",
                                          anchor='w', font=('Arial', 9), width=12, background='white')
            offline_ver_label.pack(side=tk.LEFT, padx=2)

            winget_frame = tk.Frame(row_frame, bg='white')
            winget_frame.grid(row=0, column=5, padx=4, sticky='w')
            rb_winget = ttk.Radiobutton(winget_frame, variable=provider_var, value=1,
                                        command=lambda a=app, v=provider_var: self._set_provider(a, v))
            rb_winget.pack(side=tk.LEFT, padx=(5, 2))
            if not app.winget_id:
                rb_winget.config(state=tk.DISABLED)
            winget_ver_label = ttk.Label(winget_frame, text="?", anchor='w',
                                         font=('Arial', 9), width=20, background='white')
            winget_ver_label.pack(side=tk.LEFT, padx=2)

            choco_frame = tk.Frame(row_frame, bg='white')
            choco_frame.grid(row=0, column=6, padx=4, sticky='w')
            rb_choco = ttk.Radiobutton(choco_frame, variable=provider_var, value=2,
                                       command=lambda a=app, v=provider_var: self._set_provider(a, v))
            rb_choco.pack(side=tk.LEFT, padx=(2, 2))
            if not app.choco_id:
                rb_choco.config(state=tk.DISABLED)
            choco_ver_label = ttk.Label(choco_frame, text="?", anchor='w',
                                        font=('Arial', 9), width=20, background='white')
            choco_ver_label.pack(side=tk.LEFT, padx=2)

            self.version_labels[app.display_name] = {
                'offline': offline_ver_label,
                'winget': winget_ver_label,
                'choco': choco_ver_label
            }

            row += 1

        self._fetch_versions_background()

    def _set_provider(self, app, var):
        value = var.get()
        if value == 0:
            app.selected_provider = 'offline'
        elif value == 1:
            app.selected_provider = 'winget'
        elif value == 2:
            app.selected_provider = 'choco'
        else:
            app.selected_provider = None

    def _fetch_versions_background(self):
        def task():
            for app in self.catalog.apps:
                if app.winget_id:
                    app.get_winget_version()
                if app.choco_id:
                    app.get_choco_version()
            self.root.after(0, self._update_version_labels)
        threading.Thread(target=task, daemon=True).start()

    def _update_version_labels(self):
        for app in self.catalog.apps:
            if app.display_name in self.version_labels:
                labels = self.version_labels[app.display_name]
                if app.winget_id:
                    labels['winget'].config(text=app.get_winget_version())
                if app.choco_id:
                    labels['choco'].config(text=app.get_choco_version())

    def _refresh_versions(self):
        self._fetch_versions_background()

    # ------------------ Backup/Restore Tab (New) ------------------
    # ------------------ Backup/Restore Tab (Updated) ------------------
    def _build_backup_tab(self):
        frame = self.tab_backup

        # === TOP: Destination ===
        top_frame = ttk.Frame(frame)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(top_frame, text="Backup Destination:").pack(side=tk.LEFT, padx=5)
        self.dest_var = tk.StringVar(value=self.backup_engine.destination_dir)
        dest_entry = ttk.Entry(top_frame, textvariable=self.dest_var, width=40)
        dest_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        dest_entry.bind('<FocusOut>', lambda e: self._update_destination_from_entry())
        ttk.Button(top_frame, text="Browse", command=self._browse_dest).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_frame, text="Default", command=self._reset_dest_default).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_frame, text="Refresh List", command=self._refresh_backup_list).pack(side=tk.LEFT, padx=2)

        # === MIDDLE: Sources List with checkboxes ===
        sources_label_frame = ttk.Frame(frame)
        sources_label_frame.pack(fill=tk.X, padx=5, pady=(5,0))
        ttk.Label(sources_label_frame, text="Backup Sources:").pack(anchor='w')

        sources_container = ttk.Frame(frame)
        sources_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        sources_canvas = tk.Canvas(sources_container, height=120, highlightthickness=0, bg='white')
        sources_scrollbar = ttk.Scrollbar(sources_container, orient="vertical", command=sources_canvas.yview)
        self.sources_check_frame = tk.Frame(sources_canvas, bg='white')

        self.sources_check_frame.bind(
            "<Configure>",
            lambda e: sources_canvas.configure(scrollregion=sources_canvas.bbox("all"))
        )
        sources_canvas.create_window((0, 0), window=self.sources_check_frame, anchor="nw")
        sources_canvas.configure(yscrollcommand=sources_scrollbar.set)

        sources_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sources_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Store checkbox variables and widgets
        self.source_vars = []
        self.source_checkboxes = []
        self.special_source_vars = []
        self.special_checkboxes = []

        # === BOTTOM: Available Backups Dropdown + Buttons ===
        bottom_frame = ttk.Frame(frame)
        bottom_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(bottom_frame, text="Available Backups:").pack(side=tk.LEFT, padx=5)
        # Adjust the dropdown width here – change `width=30` to your preferred size
        self.backup_combo = ttk.Combobox(bottom_frame, state='readonly', width=30)
        self.backup_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=False)

        # Buttons row
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(side=tk.RIGHT, padx=5)

        # NEW button names
        ttk.Button(btn_frame, text="Add", command=self._add_source).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Remove", command=self._remove_selected_sources).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Select All", command=self._select_all_sources).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Select None", command=self._select_none_sources).pack(side=tk.LEFT, padx=2)

        # Restore selected only checkbox
        self.restore_selected_only_var = tk.BooleanVar(value=True)
        restore_check = ttk.Checkbutton(btn_frame, text="Restore selected only",
                                        variable=self.restore_selected_only_var)
        restore_check.pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="Backup", command=self._do_backup).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Restore", command=self._do_restore).pack(side=tk.LEFT, padx=2)

        # Initial refresh
        self._refresh_sources_list()
        self._refresh_backup_list()

    def _update_destination_from_entry(self):
        """Update the backup engine's destination from the entry field."""
        new_dest = self.dest_var.get().strip()
        if new_dest and (os.path.isdir(new_dest) or not os.path.exists(new_dest)):
            self.backup_engine.set_destination(new_dest)
            self._refresh_backup_list()

    def _refresh_sources_list(self):
        """Rebuild the sources list with checkboxes, showing special sources at the top."""
        # Clear existing checkboxes
        for widget in self.sources_check_frame.winfo_children():
            widget.destroy()

        self.source_vars = []
        self.source_checkboxes = []
        self.special_source_vars = []
        self.special_checkboxes = []

        # 1. Special sources FIRST (always shown, protected) – use expandvars for correct path
        special_sources = [
            ('⭐ Custom Scripts', os.path.expandvars('%SystemDrive%\\Scripts'), 'custom_scripts'),
            ('⭐ PowerTools', os.path.expandvars('%SystemDrive%\\PowerTools'), 'powertools')
        ]
        for display, src_path, subfolder in special_sources:
            var = tk.BooleanVar(value=True)
            cb = tk.Checkbutton(self.sources_check_frame, text=display, variable=var,
                                bg='white', highlightthickness=0, anchor='w')
            cb.pack(fill=tk.X, padx=2, pady=1, anchor='w')
            self.special_source_vars.append((display, src_path, subfolder, var))
            self.special_checkboxes.append(cb)

        # 2. User sources (from backup_engine.sources)
        for src in self.backup_engine.sources:
            var = tk.BooleanVar(value=True)
            cb = tk.Checkbutton(self.sources_check_frame, text=src, variable=var,
                                bg='white', highlightthickness=0, anchor='w')
            cb.pack(fill=tk.X, padx=2, pady=1, anchor='w')
            self.source_vars.append(var)
            self.source_checkboxes.append(cb)

    def _add_source(self):
        from tkinter import filedialog
        path = filedialog.askdirectory()
        if path:
            converted = self.backup_engine._convert_to_env_var(path)
            self.backup_engine.add_source(converted)
            self._refresh_sources_list()

    def _remove_selected_sources(self):
        """Remove unchecked user sources. Special sources are protected."""
        if not self.source_vars:
            return
        to_remove = []
        for i, var in enumerate(self.source_vars):
            if not var.get():
                to_remove.append(i)
        if not to_remove:
            messagebox.showinfo("Info", "No user sources are unchecked. To remove a source, uncheck it first, then click 'Remove Source'.")
            return
        if messagebox.askyesno("Confirm Remove", f"Remove {len(to_remove)} unchecked user source(s)?"):
            for i in reversed(to_remove):
                src = self.backup_engine.sources[i]
                self.backup_engine.remove_source(src)
            self._refresh_sources_list()

    def _select_all_sources(self):
        for var in self.source_vars:
            var.set(True)
        for _, _, _, var in self.special_source_vars:
            var.set(True)

    def _select_none_sources(self):
        for var in self.source_vars:
            var.set(False)
        for _, _, _, var in self.special_source_vars:
            var.set(False)

    def _browse_dest(self):
        from tkinter import filedialog
        path = filedialog.askdirectory()
        if path:
            self.dest_var.set(path)
            self.backup_engine.set_destination(path)
            self._refresh_backup_list()

    def _reset_dest_default(self):
        default_path = self.backup_engine.reset_destination_to_default()
        self.dest_var.set(default_path)
        self._refresh_backup_list()
        self.log_text_insert(f"Backup destination reset to: {default_path}\n")

    def _refresh_backup_list(self):
        """Refresh the dropdown list with available backups (root only)."""
        # Sync destination
        current_dest = self.dest_var.get().strip()
        if current_dest and current_dest != self.backup_engine.destination_dir:
            self.backup_engine.set_destination(current_dest)

        backups = self.backup_engine.get_backup_list()
        if backups:
            self.backup_combo['values'] = [f for f, _, _ in backups]
            self.backup_combo.set(backups[0][0])
            self.backup_engine.set_selected_by_filename(backups[0][0])
        else:
            self.backup_combo['values'] = []
            self.backup_combo.set("")
            self.backup_engine.selected_backup_path = None

    def _do_backup(self):
        """Create backups: user sources in one archive, special sources separately in subfolders."""
        # Collect checked user sources
        user_sources = []
        for i, var in enumerate(self.source_vars):
            if var.get():
                user_sources.append(self.backup_engine.sources[i])

        # Collect checked special sources
        special_sources = []
        for display, src_path, subfolder, var in self.special_source_vars:
            if var.get():
                special_sources.append((src_path, subfolder))

        if not user_sources and not special_sources:
            messagebox.showwarning("No Sources Selected", "No backup sources are checked. Please select at least one source.")
            return

        def task():
            self.root.config(cursor="watch")
            self.log_text_insert("Backup started...\n")

            # Backup user sources (root)
            if user_sources:
                self.log_text_insert("Backing up user sources...\n")
                success, msg = self.backup_engine.create_backup(source_list=user_sources, subfolder=None)
                if success:
                    self.log_text_insert(f"User backup successful: {os.path.basename(msg)}\n")
                else:
                    self.log_text_insert(f"User backup failed: {msg}\n")

            # Backup special sources (each separately)
            for src_path, subfolder in special_sources:
                if not os.path.isdir(src_path):
                    self.log_text_insert(f"Warning: Special folder '{src_path}' not found, skipping.\n")
                    continue
                self.log_text_insert(f"Backing up {os.path.basename(src_path)} to {subfolder}/\n")
                success, msg = self.backup_engine.create_backup(source_list=[src_path], subfolder=subfolder)
                if success:
                    self.log_text_insert(f"Backup of {os.path.basename(src_path)} successful.\n")
                else:
                    self.log_text_insert(f"Backup of {os.path.basename(src_path)} failed: {msg}\n")

            self.root.config(cursor="")
            # Only refresh the backup list – preserve source selection
            self._refresh_backup_list()
            # DO NOT call _refresh_sources_list() – it resets selections

        threading.Thread(target=task, daemon=True).start()

    def _do_restore(self):
        selected = self.backup_combo.get()
        if not selected:
            messagebox.showinfo("No Backup", "No backup selected in the dropdown.")
            return
        zip_path = os.path.join(self.backup_engine.destination_dir, selected)
        if not os.path.isfile(zip_path):
            messagebox.showerror("Error", "Backup file not found.")
            return

        # Determine sources to restore based on checkbox
        restore_selected_only = self.restore_selected_only_var.get()
        sources_to_restore = None
        if restore_selected_only:
            # Gather checked user sources
            checked_sources = []
            for i, var in enumerate(self.source_vars):
                if var.get():
                    checked_sources.append(self.backup_engine.sources[i])
            if not checked_sources:
                messagebox.showwarning("No Sources Selected", 
                                       "No user sources are checked. Please select at least one source to restore.")
                return
            sources_to_restore = checked_sources
        # else: sources_to_restore remains None -> restore all

        if not messagebox.askyesno("Confirm Restore", 
                                   f"Restore from '{selected}'?\nThis will overwrite existing files for the selected sources."):
            return

        def task():
            self.root.config(cursor="watch")
            self.log_text_insert(f"Restoring from {selected}...\n")
            success, msg = self.backup_engine.restore_backup(zip_path, sources_to_restore=sources_to_restore)
            if success:
                self.log_text_insert("Restore completed successfully.\n")
            else:
                self.log_text_insert(f"Restore failed: {msg}\n")
            self.root.config(cursor="")
        threading.Thread(target=task, daemon=True).start()

    # ---------- Logging & Status Polling ----------
    def log_text_insert(self, text):
        def _insert():
            try:
                self.log_text.config(state='normal')
                self.log_text.insert(tk.END, text)
                self.log_text.see(tk.END)
                self.log_text.config(state='disabled')
            except Exception:
                pass
        self.root.after(0, _insert)

    def _poll_logs(self):
        try:
            logs = self.install_engine.get_logs()
            for msg, level in logs:
                if level == 'STATUS':
                    try:
                        parts = msg.split('|')
                        if len(parts) >= 4:
                            idx = int(parts[1])
                            status = parts[2]
                            message = parts[3]
                            self._update_status_panel()
                    except Exception:
                        self.log_text_insert(f"[STATUS] {msg}\n")
                else:
                    prefix = ""
                    if level == 'ERROR':
                        prefix = "[ERROR] "
                    elif level == 'WARNING':
                        prefix = "[WARN] "
                    self.log_text_insert(prefix + msg + "\n")

            if self.install_engine.is_running():
                self.root.update()
        except Exception as e:
            print(f"Polling error: {e}")
        finally:
            self.root.after(100, self._poll_logs)

    # ---------- Deployment Controls ----------
    def _start_deployment(self):
        if not self.selected_operations:
            messagebox.showwarning("No Operations", "Please add operations to the execution order.")
            return

        selected_activators = []
        for item in self.tree_activators.get_children():
            values = self.tree_activators.item(item, 'values')
            if values[0] == "☑":
                selected_activators.append({
                    'name': values[1],
                    'switches': values[3]
                })
        self.install_engine.set_selected_activators(selected_activators)

        # ... existing code to get selected_activators ...

        # Gather external scripts
        ext_scripts = self.get_checked_external_scripts()
        self.install_engine.set_external_scripts(ext_scripts)

        # ... rest ...

        # Gather restore sources (if "Restore selected only" is checked)
        if self.restore_selected_only_var.get():
            # Get checked user sources
            checked_sources = []
            for i, var in enumerate(self.source_vars):
                if var.get():
                    checked_sources.append(self.backup_engine.sources[i])
            self.install_engine.restore_sources = checked_sources if checked_sources else None
        else:
            self.install_engine.restore_sources = None

        self.btn_deploy.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL)
        self.notebook.select(0)
        self.root.update()

        self.log_text_insert("Deployment started.\n")
        self.install_engine.set_operations(self.selected_operations)
        self.install_engine.start_deployment(on_finished=self._deployment_finished)
        self._update_status_panel()

    def _enable_ui(self):
        self.btn_deploy.config(state=tk.NORMAL)
        self.btn_cancel.config(state=tk.DISABLED)

    def _deployment_finished(self):
        self.root.after(0, self._enable_ui)
        self.log_text_insert("Deployment finished.\n")
        self._update_status_panel()

    def _cancel_deployment(self):
        self.install_engine.cancel()
        self.log_text_insert("Cancel requested. Waiting for current task to finish...\n")
        self.btn_cancel.config(state=tk.DISABLED)

    # ---------- Settings ----------
    def _open_settings(self):
        dlg = SettingsDialog(self.root, self.config, self.catalog)
        self.root.wait_window(dlg.dialog)
        self.catalog.refresh()
        self._refresh_install_tab()
        self.available_ops = self.config.get_operations()
        self._refresh_available_list()
        self._refresh_backup_list()
        # Refresh tweaks and activators tabs to reflect changes made in Settings
        self._refresh_tweaks_tab()
        self._refresh_activators_tab()

    # ------------------ Tweaks Tab ------------------
    def _build_tweaks_tab(self):
        frame = self.tab_tweaks

        top_frame = ttk.Frame(frame)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(top_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.tweak_search_var = tk.StringVar()
        self.tweak_search_var.trace('w', lambda *args: self._refresh_tweaks_tab())
        search_entry = ttk.Entry(top_frame, textvariable=self.tweak_search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)

        ttk.Label(top_frame, text="Filter by Category:").pack(side=tk.LEFT, padx=15)
        self.tweak_filter_var = tk.StringVar(value='All')
        self.tweak_filter_combo = ttk.Combobox(top_frame, textvariable=self.tweak_filter_var, values=['All'], state='readonly', width=16)
        self.tweak_filter_combo.pack(side=tk.LEFT, padx=5)
        self.tweak_filter_combo.bind('<<ComboboxSelected>>', lambda e: self._refresh_tweaks_tab())

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Columns: Disable (first), Enable (second), then Name, Description, Category, Type
        columns = ('disable', 'enable', 'name', 'description', 'category', 'type')
        self.tree_tweaks = ttk.Treeview(tree_frame, columns=columns, show='headings', height=10)
        self.tree_tweaks.heading('disable', text='Disable')
        self.tree_tweaks.heading('enable', text='Enable')
        self.tree_tweaks.heading('name', text='Name')
        self.tree_tweaks.heading('description', text='Description')
        self.tree_tweaks.heading('category', text='Category')
        self.tree_tweaks.heading('type', text='Type')

        self.tree_tweaks.column('disable', width=60, anchor='center', stretch=False)
        self.tree_tweaks.column('enable', width=60, anchor='center', stretch=False)
        self.tree_tweaks.column('name', width=200, anchor='w', stretch=False)
        self.tree_tweaks.column('description', width=300, anchor='w')
        self.tree_tweaks.column('category', width=100, anchor='w', stretch=False)
        self.tree_tweaks.column('type', width=50, anchor='w', stretch=False)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_tweaks.yview)
        self.tree_tweaks.configure(yscrollcommand=scrollbar.set)

        self.tree_tweaks.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_tweaks.bind('<Button-1>', self._on_tweak_click)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="Apply Selected", command=self._apply_all_tweaks).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Clear All", command=self._clear_all_tweaks).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Refresh", command=self._refresh_tweaks_tab).pack(side=tk.RIGHT, padx=2)

        self._refresh_tweaks_tab()
        
    def _sort_tweaks(self, col):
        items = [(self.tree_tweaks.set(child, col), child) for child in self.tree_tweaks.get_children('')]
        if not items:
            return
        reverse = False
        if hasattr(self, '_tweak_sort_col') and self._tweak_sort_col == col:
            reverse = not getattr(self, '_tweak_sort_reverse', False)
        self._tweak_sort_col = col
        self._tweak_sort_reverse = reverse
        items.sort(key=lambda x: x[0].lower(), reverse=reverse)
        for index, (val, child) in enumerate(items):
            self.tree_tweaks.move(child, '', index)

    def _on_tweak_click(self, event):
        region = self.tree_tweaks.identify_region(event.x, event.y)
        if region != 'cell':
            return
        column = self.tree_tweaks.identify_column(event.x)
        # Column '#1' = Disable, '#2' = Enable
        if column not in ('#1', '#2'):
            return
        item = self.tree_tweaks.identify_row(event.y)
        if not item:
            return

        values = self.tree_tweaks.item(item, 'values')
        if not values:
            return
        name = values[2]  # Name is third column

        tweaks_list = self.config.tweaks.get('tweaks', [])
        tweak = None
        for t in tweaks_list:
            if t.get('name') == name:
                tweak = t
                break
        if not tweak:
            return

        # Determine which column was clicked and check if script exists
        if column == '#1':  # Disable column
            if not tweak.get('disable_script', '').strip():
                messagebox.showinfo("Not Available", "This tweak has no disable script.")
                return
            current = tweak.get('selected_action', None)
            action = None if current == 'disable' else 'disable'
        else:  # Enable column
            if not tweak.get('enable_script', '').strip():
                messagebox.showinfo("Not Available", "This tweak has no enable script.")
                return
            current = tweak.get('selected_action', None)
            action = None if current == 'enable' else 'enable'

        tweak['selected_action'] = action
        self.config.tweaks['tweaks'] = tweaks_list
        self.config.save_tweaks()
        self._refresh_tweaks_tab()
        return "break"
        
    def _refresh_tweaks_tab(self):
        for item in self.tree_tweaks.get_children():
            self.tree_tweaks.delete(item)

        self.config.tweaks = self.config._load_json(self.config.tweaks_file)
        tweaks = self.config.tweaks.get('tweaks', [])

        categories = sorted(set(t.get('category', 'Uncategorized') for t in tweaks if t.get('category')))
        current_filter = self.tweak_filter_var.get()
        filter_values = ['All'] + categories
        self.tweak_filter_combo['values'] = filter_values
        if current_filter in filter_values:
            self.tweak_filter_combo.set(current_filter)
        else:
            self.tweak_filter_combo.set('All')

        search_text = self.tweak_search_var.get().strip().lower()
        filter_category = self.tweak_filter_var.get()

        for tweak in tweaks:
            name = tweak.get('name', '')
            if search_text and search_text not in name.lower():
                continue
            if filter_category != 'All' and tweak.get('category', '') != filter_category:
                continue

            selected_action = tweak.get('selected_action', None)
            has_disable_script = bool(tweak.get('disable_script', '').strip())
            has_enable_script = bool(tweak.get('enable_script', '').strip())

            # Determine checkbox display: if script missing, show a dash instead of checkbox
            if has_disable_script:
                disable_check = "☑" if selected_action == 'disable' else "☐"
            else:
                disable_check = "‑"  # em dash indicates unavailable

            if has_enable_script:
                enable_check = "☑" if selected_action == 'enable' else "☐"
            else:
                enable_check = "‑"

            if tweak.get('is_builtin', False):
                script_type = "Built-in"
            else:
                script_type = tweak.get('script_type', 'ps1').upper()

            # Insert row (disable first, enable second)
            self.tree_tweaks.insert('', tk.END, values=(
                disable_check,
                enable_check,
                name,
                tweak.get('description', ''),
                tweak.get('category', ''),
                script_type
            ))
            
    def _apply_all_tweaks(self):
        from modules.script_engine import ScriptEngine
        engine = ScriptEngine(self.config)
        engine.load_tweaks()

        tweaks = self.config.tweaks.get('tweaks', [])
        if not tweaks:
            self.log_text_insert("No tweaks configured.\n")
            return

        # Filter tweaks that have a selected action
        selected_tweaks = [t for t in tweaks if t.get('selected_action')]
        if not selected_tweaks:
            self.log_text_insert("No tweaks selected. Nothing to apply.\n")
            return

        def log_cb(msg):
            self.log_text_insert(f"[Tweaks] {msg}\n")

        self.log_text_insert(f"Applying {len(selected_tweaks)} selected tweak actions...\n")
        success_count = 0
        fail_count = 0

        for tweak in selected_tweaks:
            name = tweak.get('name', 'Unnamed')
            action = tweak.get('selected_action')
            script_path = tweak.get(f'{action}_script', '')
            if not script_path:
                self.log_text_insert(f"⚠️ {name}: No {action} script defined (skipped)\n")
                fail_count += 1
                continue

            script_type = tweak.get('script_type', 'ps1')
            arguments = tweak.get('arguments', '')

            self.log_text_insert(f"▶️ {name}: Running {action} script...\n")
            success, msg = engine._run_script(script_path, script_type, log_cb, tweak_name=name, arguments=arguments)
            if success:
                self.log_text_insert(f"✅ {name}: {action} script succeeded\n")
                success_count += 1
            else:
                self.log_text_insert(f"❌ {name}: {action} script failed: {msg}\n")
                fail_count += 1

        # Final summary
        self.log_text_insert(f"Tweak actions completed: {success_count} succeeded, {fail_count} failed.\n")
        
    def _clear_all_tweaks(self):
        """Clear all checkbox selections (set selected_action to None for all tweaks)."""
        tweaks_list = self.config.tweaks.get('tweaks', [])
        for tweak in tweaks_list:
            tweak['selected_action'] = None
        self.config.tweaks['tweaks'] = tweaks_list
        self.config.save_tweaks()
        self._refresh_tweaks_tab()
        
    # ------------------ Activators Tab ------------------
    # ------------------ Activators Tab (Complete) ------------------
    def _build_activators_tab(self):
        frame = self.tab_activators
        
        # === TOP: Info note ===
        info_frame = ttk.Frame(frame)
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(info_frame, text="⚠️ Only one activator can run at a time.", 
                  font=('Arial', 9, 'italic'), foreground='#555').pack(anchor='w')
        
        # === SEARCH/FILTER ===
        filter_frame = ttk.Frame(frame)
        filter_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(filter_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.activator_search_var = tk.StringVar()
        self.activator_search_var.trace('w', lambda *args: self._refresh_activators_tab())
        search_entry = ttk.Entry(filter_frame, textvariable=self.activator_search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(filter_frame, text="Filter by Category:").pack(side=tk.LEFT, padx=15)
        self.activator_filter_var = tk.StringVar(value='All')
        self.activator_filter_combo = ttk.Combobox(filter_frame, textvariable=self.activator_filter_var, 
                                                    values=['All'], state='readonly', width=16)
        self.activator_filter_combo.pack(side=tk.LEFT, padx=5)
        self.activator_filter_combo.bind('<<ComboboxSelected>>', lambda e: self._refresh_activators_tab())
        
        ttk.Button(filter_frame, text="Refresh", command=self._refresh_activators_tab).pack(side=tk.RIGHT, padx=5)
        
        # === TREEVIEW ===
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Column order: Select, Name, Description, Switches, Category
        columns = ('Select', 'Name', 'Description', 'Switches', 'Category')
        self.tree_activators = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
        self.tree_activators.heading('Select', text='')
        self.tree_activators.heading('Name', text='Name')
        self.tree_activators.heading('Description', text='Description')
        self.tree_activators.heading('Switches', text='Switches')
        self.tree_activators.heading('Category', text='Category')
        
        # Fixed column widths
        self.tree_activators.column('Select', width=50, anchor='center', stretch=False)
        self.tree_activators.column('Name', width=230, anchor='w', stretch=False)
        self.tree_activators.column('Description', width=250, anchor='w')
        self.tree_activators.column('Switches', width=200, anchor='w', stretch=False)
        self.tree_activators.column('Category', width=80, anchor='w', stretch=False)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_activators.yview)
        self.tree_activators.configure(yscrollcommand=scrollbar.set)
        self.tree_activators.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Click binding for checkbox toggle (fixes checkbox issue)
        self.tree_activators.bind('<Button-1>', self._on_activator_click)
        
        # Double-click to edit switches
        self.tree_activators.bind('<Double-Button-1>', self._edit_activator_switches)
        
        # === BOTTOM BUTTONS ===
        # === BOTTOM BUTTONS ===
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Select All", command=self._select_all_activators).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Select None", command=self._select_none_activators).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Run Selected", command=self._run_selected_activators).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Refresh", command=self._refresh_activators_tab).pack(side=tk.RIGHT, padx=2)
        
        # Initial refresh
        self._refresh_activators_tab()
    
    def _refresh_activators_tab(self):
        """Refresh the Activators treeview with current data."""
        # Clear tree
        for item in self.tree_activators.get_children():
            self.tree_activators.delete(item)
        
        # Load activators
        self.config.activators = self.config._load_json(self.config.activators_file)
        activators = self.config.activators.get('activators', [])
        
        # Update category filter dropdown
        categories = sorted(set(a.get('category', 'Uncategorized') for a in activators if a.get('category')))
        filter_values = ['All'] + categories
        self.activator_filter_combo['values'] = filter_values
        current_filter = self.activator_filter_var.get()
        if current_filter in filter_values:
            self.activator_filter_combo.set(current_filter)
        else:
            self.activator_filter_combo.set('All')
        
        search_text = self.activator_search_var.get().strip().lower()
        filter_category = self.activator_filter_var.get()
        
        # Check which activators exist (offline)
        for act in activators:
            name = act.get('name', '')
            if search_text and search_text not in name.lower():
                continue
            if filter_category != 'All' and act.get('category', '') != filter_category:
                continue
            
            # Check if activator is available offline
            is_available = self._is_activator_available(act)
            
            self.tree_activators.insert('', tk.END, values=(
                "☐",
                name,
                act.get('description', ''),
                act.get('default_switches', ''),
                act.get('category', '')
            ), tags=('available' if is_available else 'unavailable',))
        
        # Configure tag colors
        self.tree_activators.tag_configure('unavailable', foreground='gray')
    
    def _is_activator_available(self, activator):
        """Check if an activator is available offline (file exists)."""
        exec_path = activator.get('executable', '')
        if not exec_path:
            return False
        
        # Check archive first
        archive = activator.get('archive', '')
        if archive:
            archive_path = os.path.join(self.config.base_dir, 'activators', archive)
            if os.path.isfile(archive_path):
                return True
        
        # Check folder
        folder = activator.get('folder', '')
        if folder and os.path.isdir(folder):
            full_path = os.path.join(folder, exec_path)
            if os.path.isfile(full_path):
                return True
        
        # Check if executable is a full path
        if os.path.isabs(exec_path) and os.path.isfile(exec_path):
            return True
        
        # Check if it's in activators folder
        full_path = os.path.join(self.config.base_dir, 'activators', exec_path)
        if os.path.isfile(full_path):
            return True
        
        # Check if any file in activators folder matches the executable name
        activators_dir = os.path.join(self.config.base_dir, 'activators')
        if os.path.isdir(activators_dir):
            for f in os.listdir(activators_dir):
                if f == exec_path:
                    return True
                # Check if exec_path is inside a subfolder
                for root, dirs, files in os.walk(activators_dir):
                    if exec_path in files:
                        return True
        
        return False
    
    def _on_activator_click(self, event):
        """Toggle checkbox when clicking on the first column (Select column)."""
        region = self.tree_activators.identify_region(event.x, event.y)
        if region != 'cell':
            return
        column = self.tree_activators.identify_column(event.x)
        # The 'Select' column is the first data column, which is '#1'
        if column != '#1':
            return
        item = self.tree_activators.identify_row(event.y)
        if not item:
            return
        
        # Check if item is available (not grayed out)
        tags = self.tree_activators.item(item, 'tags')
        if 'unavailable' in tags:
            messagebox.showinfo("Not Available", "This activator is not available offline. Download it first or use online mode.")
            return
        
        values = self.tree_activators.item(item, 'values')
        if not values:
            return
        
        current = values[0]
        new_val = "☑" if current == "☐" else "☐"
        self.tree_activators.item(item, values=(new_val, *values[1:]))
        
        # Prevent default selection behavior
        return "break"
    
    def _edit_activator_switches(self, event):
        """Double-click to edit switches for an activator."""
        item = self.tree_activators.selection()[0] if self.tree_activators.selection() else None
        if not item:
            item = self.tree_activators.identify_row(event.y)
            if not item:
                return
        
        # Check if item is available
        tags = self.tree_activators.item(item, 'tags')
        if 'unavailable' in tags:
            messagebox.showinfo("Not Available", "This activator is not available offline. Download it first.")
            return
        
        values = self.tree_activators.item(item, 'values')
        current_switches = values[3]
        name = values[1]
        
        from tkinter import simpledialog
        new_switches = simpledialog.askstring("Edit Switches", f"Enter switches for {name}:", initialvalue=current_switches)
        if new_switches is not None:
            self.tree_activators.item(item, values=(values[0], values[1], values[2], new_switches, values[4]))
    
  
    def _run_selected_activators(self):
        """Run all activators that are selected (checkbox ticked)."""
        from modules.activator_engine import ActivatorEngine
        engine = ActivatorEngine(self.config)
        engine.load_activators()
        
        selected = []
        for item in self.tree_activators.get_children():
            values = self.tree_activators.item(item, 'values')
            tags = self.tree_activators.item(item, 'tags')
            if values[0] == "☑":
                name = values[1]
                switches = values[3]
                
                activator = None
                for a in engine.activators:
                    if a.get('name') == name:
                        activator = a
                        break
                
                if activator:
                    if not self._is_activator_available(activator):
                        self.log_text_insert(f"⚠️ {name}: Skipping - not available offline.\n")
                        continue
                    selected.append((activator, switches))
        
        if not selected:
            messagebox.showinfo("No Selection", "Please select at least one available activator.")
            return
        
        def log_cb(msg):
            self.log_text_insert(f"[Activator] {msg}\n")
        
        self.log_text_insert("Running selected activators...\n")
        self.log_text_insert("⚠️ Only one activator runs at a time.\n")
        
        results = engine.run_selected(selected, log_cb)
        for name, success, msg in results:
            if success:
                self.log_text_insert(f"✅ {name}: {msg}\n")
            else:
                self.log_text_insert(f"❌ {name}: {msg}\n")
    
    def _select_all_activators(self):
        for item in self.tree_activators.get_children():
            tags = self.tree_activators.item(item, 'tags')
            if 'unavailable' in tags:
                continue
            values = self.tree_activators.item(item, 'values')
            self.tree_activators.item(item, values=("☑", values[1], values[2], values[3], values[4]))
    
    def _select_none_activators(self):
        for item in self.tree_activators.get_children():
            values = self.tree_activators.item(item, 'values')
            self.tree_activators.item(item, values=("☐", values[1], values[2], values[3], values[4]))
            
            
    # ------------------ External Scripts Tab ------------------
    def _build_external_tab(self):
        """Build the External Scripts tab for temporary per-session scripts."""
        frame = self.tab_external

        # ---- Top: Search ----
        top_frame = ttk.Frame(frame)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(top_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.ext_search_var = tk.StringVar()
        self.ext_search_var.trace('w', lambda *args: self._refresh_external_tab())
        search_entry = ttk.Entry(top_frame, textvariable=self.ext_search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)

        # ---- Treeview ----
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ('check', 'name', 'type', 'source', 'description')
        self.tree_external = ttk.Treeview(tree_frame, columns=columns, show='headings', height=10)
        self.tree_external.heading('check', text='')
        self.tree_external.heading('name', text='Name')
        self.tree_external.heading('type', text='Type')
        self.tree_external.heading('source', text='Source')
        self.tree_external.heading('description', text='Description')

        self.tree_external.column('check', width=40, anchor='center', stretch=False)
        self.tree_external.column('name', width=150, anchor='w', stretch=False)
        self.tree_external.column('type', width=40, anchor='w', stretch=False)
        self.tree_external.column('source', width=50, anchor='w', stretch=False)
        self.tree_external.column('description', width=250, anchor='w')

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_external.yview)
        self.tree_external.configure(yscrollcommand=scrollbar.set)
        self.tree_external.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Click to toggle checkbox
        self.tree_external.bind('<Button-1>', self._on_external_click)

        # ---- Buttons ----
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="Add Script", command=self._add_external_script).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Add Text Script", command=self._add_external_text_script).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Edit", command=self._edit_external_script).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Remove", command=self._remove_external_script).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Move Up", command=self._move_external_up).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Move Down", command=self._move_external_down).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Run Selected", command=self._run_selected_external).pack(side=tk.LEFT, padx=2)

        self._refresh_external_tab()
        
    def _refresh_external_tab(self):
        """Refresh the External Scripts treeview."""
        for item in self.tree_external.get_children():
            self.tree_external.delete(item)

        search = self.ext_search_var.get().strip().lower()
        for idx, script in enumerate(self.external_scripts):
            name = script.get('name', '')
            if search and search not in name.lower():
                continue
            check = "☑" if script.get('enabled', False) else "☐"
            self.tree_external.insert('', tk.END, values=(
                check,
                name,
                script.get('type', ''),
                script.get('source', ''),
                script.get('description', '')
            ), tags=(str(idx),))

    def _on_external_click(self, event):
        """Toggle checkbox on click in first column."""
        region = self.tree_external.identify_region(event.x, event.y)
        if region != 'cell':
            return
        column = self.tree_external.identify_column(event.x)
        if column != '#1':
            return
        item = self.tree_external.identify_row(event.y)
        if not item:
            return
        values = self.tree_external.item(item, 'values')
        if not values:
            return
        tags = self.tree_external.item(item, 'tags')
        if not tags:
            return
        idx = int(tags[0])
        # Toggle enabled
        self.external_scripts[idx]['enabled'] = not self.external_scripts[idx]['enabled']
        self._refresh_external_tab()
        return "break"
        
    def _add_external_script(self):
        """Add a script by browsing for a file."""
        from tkinter import filedialog
        filetypes = [
            ("Script files", "*.ps1;*.bat;*.cmd;*.py;*.reg"),
            ("All files", "*.*")
        ]
        filename = filedialog.askopenfilename(title="Select Script File", filetypes=filetypes)
        if not filename:
            return
        # Auto-detect type from extension
        ext = os.path.splitext(filename)[1].lower()
        type_map = {'.ps1': 'ps1', '.bat': 'bat', '.cmd': 'cmd', '.py': 'py', '.reg': 'reg'}
        script_type = type_map.get(ext, 'ps1')
        name = os.path.basename(filename)
        description = f"File: {name}"
        self.external_scripts.append({
            'name': name,
            'type': script_type,
            'content': filename,
            'source': 'File',
            'description': description,
            'enabled': False
        })
        self._refresh_external_tab()

    def _add_external_text_script(self):
        """Open a dialog to type or paste script content."""
        popup = tk.Toplevel(self.root)
        popup.title("Add Text Script")
        popup.geometry("600x400")
        popup.transient(self.root)
        popup.grab_set()

        ttk.Label(popup, text="Enter Script Content:").pack(pady=5)

        text_widget = scrolledtext.ScrolledText(popup, height=15, width=70)
        text_widget.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # Name, type, description entries
        entry_frame = ttk.Frame(popup)
        entry_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(entry_frame, text="Name:").grid(row=0, column=0, sticky='e', padx=5)
        name_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=name_var, width=20).grid(row=0, column=1, sticky='w', padx=5)

        ttk.Label(entry_frame, text="Type:").grid(row=0, column=2, sticky='e', padx=5)
        type_var = tk.StringVar(value='ps1')
        type_combo = ttk.Combobox(entry_frame, textvariable=type_var, values=['ps1', 'bat', 'cmd', 'reg', 'py'], state='readonly', width=8)
        type_combo.grid(row=0, column=3, sticky='w', padx=5)

        ttk.Label(entry_frame, text="Description:").grid(row=1, column=0, sticky='e', padx=5)
        desc_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=desc_var, width=40).grid(row=1, column=1, columnspan=3, sticky='w', padx=5)

        def save_text_script():
            content = text_widget.get("1.0", tk.END).strip()
            if not content:
                messagebox.showerror("Error", "Script content cannot be empty.")
                return
            name = name_var.get().strip() or "Inline Script"
            script_type = type_var.get()
            description = desc_var.get().strip() or "Inline script"
            self.external_scripts.append({
                'name': name,
                'type': script_type,
                'content': content,
                'source': 'Text',
                'description': description,
                'enabled': False
            })
            self._refresh_external_tab()
            popup.destroy()

        btn_frame = ttk.Frame(popup)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="OK", command=save_text_script).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=popup.destroy).pack(side=tk.LEFT, padx=5)
 
    def _edit_external_script(self):
        """Edit the selected external script."""
        selected = self.tree_external.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select a script to edit.")
            return
        item = selected[0]
        tags = self.tree_external.item(item, 'tags')
        if not tags:
            return
        idx = int(tags[0])
        if idx < 0 or idx >= len(self.external_scripts):
            return
        script = self.external_scripts[idx]

        # Open a dialog similar to Add Text Script but pre‑filled
        popup = tk.Toplevel(self.root)
        popup.title("Edit Script")
        popup.geometry("600x400")
        popup.transient(self.root)
        popup.grab_set()

        ttk.Label(popup, text="Edit Script Content:").pack(pady=5)

        text_widget = scrolledtext.ScrolledText(popup, height=15, width=70)
        text_widget.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        text_widget.insert("1.0", script.get('content', ''))

        # Name, type, description entries
        entry_frame = ttk.Frame(popup)
        entry_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(entry_frame, text="Name:").grid(row=0, column=0, sticky='e', padx=5)
        name_var = tk.StringVar(value=script.get('name', ''))
        ttk.Entry(entry_frame, textvariable=name_var, width=20).grid(row=0, column=1, sticky='w', padx=5)

        ttk.Label(entry_frame, text="Type:").grid(row=0, column=2, sticky='e', padx=5)
        type_var = tk.StringVar(value=script.get('type', 'ps1'))
        type_combo = ttk.Combobox(entry_frame, textvariable=type_var, values=['ps1', 'bat', 'cmd', 'reg', 'py'], state='readonly', width=8)
        type_combo.grid(row=0, column=3, sticky='w', padx=5)

        ttk.Label(entry_frame, text="Description:").grid(row=1, column=0, sticky='e', padx=5)
        desc_var = tk.StringVar(value=script.get('description', ''))
        ttk.Entry(entry_frame, textvariable=desc_var, width=40).grid(row=1, column=1, columnspan=3, sticky='w', padx=5)

        def save_edit():
            content = text_widget.get("1.0", tk.END).strip()
            if not content:
                messagebox.showerror("Error", "Script content cannot be empty.")
                return
            name = name_var.get().strip() or "Inline Script"
            script_type = type_var.get()
            description = desc_var.get().strip() or "Inline script"
            # Update the script in place
            self.external_scripts[idx] = {
                'name': name,
                'type': script_type,
                'content': content,
                'source': 'Text',   # after editing, it becomes a text script
                'description': description,
                'enabled': script.get('enabled', False)
            }
            self._refresh_external_tab()
            popup.destroy()

        btn_frame = ttk.Frame(popup)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Save", command=save_edit).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=popup.destroy).pack(side=tk.LEFT, padx=5)
 
    def _remove_external_script(self):
        selected = self.tree_external.selection()
        if not selected:
            return
        indices = []
        for item in selected:
            tags = self.tree_external.item(item, 'tags')
            if tags:
                indices.append(int(tags[0]))
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self.external_scripts):
                del self.external_scripts[idx]
        self._refresh_external_tab()

    def _move_external_up(self):
        selected = self.tree_external.selection()
        if not selected:
            return
        item = selected[0]
        tags = self.tree_external.item(item, 'tags')
        if not tags:
            return
        idx = int(tags[0])
        if idx <= 0:
            return
        self.external_scripts[idx], self.external_scripts[idx-1] = self.external_scripts[idx-1], self.external_scripts[idx]
        self._refresh_external_tab()
        for child in self.tree_external.get_children():
            if self.tree_external.item(child, 'tags')[0] == str(idx-1):
                self.tree_external.selection_set(child)
                break

    def _move_external_down(self):
        selected = self.tree_external.selection()
        if not selected:
            return
        item = selected[0]
        tags = self.tree_external.item(item, 'tags')
        if not tags:
            return
        idx = int(tags[0])
        if idx >= len(self.external_scripts) - 1:
            return
        self.external_scripts[idx], self.external_scripts[idx+1] = self.external_scripts[idx+1], self.external_scripts[idx]
        self._refresh_external_tab()
        for child in self.tree_external.get_children():
            if self.tree_external.item(child, 'tags')[0] == str(idx+1):
                self.tree_external.selection_set(child)
                break
                
    def _run_selected_external(self):
        """Run all checked scripts using ScriptEngine."""
        checked = [s for s in self.external_scripts if s.get('enabled', False)]
        if not checked:
            messagebox.showinfo("No Selection", "No scripts are checked.")
            return

        from modules.script_engine import ScriptEngine
        engine = ScriptEngine(self.config)

        def log_cb(msg):
            self.log_text_insert(f"[External Script] {msg}\n")

        self.log_text_insert("Running selected external scripts...\n")
        for script in checked:
            name = script.get('name', 'Unnamed')
            script_type = script.get('type', 'ps1')
            content = script.get('content', '')
            self.log_text_insert(f"Running: {name} ({script_type})\n")
            # Use test_script which uses _run_script with interactive console
            success, msg = engine.test_script(content, script_type, log_cb, arguments='')
            if success:
                self.log_text_insert(f"✅ {name}: OK\n")
            else:
                self.log_text_insert(f"❌ {name}: {msg}\n")
                
    def get_checked_external_scripts(self):
        """Return list of enabled external scripts."""
        return [s for s in self.external_scripts if s.get('enabled', False)]