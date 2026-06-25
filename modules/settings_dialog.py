"""
SettingsDialog - Full configuration dialog with sub-tabs for App Management,
Command Templates, Operations, Tweaks, Activators, and General Settings.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import os
import shutil
import re
import subprocess
import threading
import datetime

class SettingsDialog:
    def __init__(self, parent, config_manager, app_catalog):
        self.parent = parent
        self.config = config_manager
        self.catalog = app_catalog

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Settings")
        self.dialog.geometry("800x600")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.notebook = ttk.Notebook(self.dialog)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tabs
        self.tab_apps = ttk.Frame(self.notebook)
        self.tab_commands = ttk.Frame(self.notebook)
        self.tab_operations = ttk.Frame(self.notebook)
        self.tab_tweaks = ttk.Frame(self.notebook)
        self.tab_activators = ttk.Frame(self.notebook)
        self.tab_general = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_general, text="General")
        self.notebook.add(self.tab_apps, text="App Management")
        self.notebook.add(self.tab_tweaks, text="Tweaks Management")
        self.notebook.add(self.tab_activators, text="Activators Management")
        self.notebook.add(self.tab_operations, text="Operations")
        self.notebook.add(self.tab_commands, text="Command Templates")

        self._build_apps_tab()
        self._build_commands_tab()
        self._build_operations_tab()
        self._build_tweaks_tab()
        self._build_activators_tab()
        self._build_general_tab()

        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="Close", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)

    # ---------- Helper: Drag‑and‑Drop for Treeviews ----------
    def _make_draggable(self, tree, data_list, key_func, save_func):
        """
        Make Treeview rows draggable to reorder data_list.
        tree: ttk.Treeview
        data_list: list of items (objects or dicts)
        key_func: callable(item) -> str (unique key)
        save_func: callable() to save the config after reordering
        """
        drag_data = {"item": None, "index": None}

        def on_press(event):
            item = tree.identify_row(event.y)
            if not item:
                return
            tree.selection_set(item)
            drag_data["item"] = item
            drag_data["index"] = tree.index(item)

        def on_motion(event):
            if not drag_data["item"]:
                return
            dest_item = tree.identify_row(event.y)
            if not dest_item or dest_item == drag_data["item"]:
                return
            dest_index = tree.index(dest_item)
            tree.move(drag_data["item"], "", dest_index)
            drag_data["index"] = dest_index

        def on_release(event):
            if not drag_data["item"]:
                return
            # Get new order of keys from tree (first column)
            new_order = []
            for child in tree.get_children():
                values = tree.item(child, 'values')
                if values:
                    new_order.append(values[0])
            # Reorder data_list to match new_order
            key_to_item = {key_func(item): item for item in data_list}
            reordered = []
            for key in new_order:
                if key in key_to_item:
                    reordered.append(key_to_item.pop(key))
            # Append remaining items (safety)
            reordered.extend(key_to_item.values())
            # Update data_list in place
            data_list.clear()
            data_list.extend(reordered)
            save_func()
            drag_data["item"] = None

        tree.bind("<Button-1>", on_press)
        tree.bind("<B1-Motion>", on_motion)
        tree.bind("<ButtonRelease-1>", on_release)

    # ---------- Helper: Show URL Dialog ----------
    def _show_url_dialog(self, title, current_url=""):
        dialog = tk.Toplevel(self.dialog)
        dialog.title(title)
        dialog.geometry("450x120")
        dialog.transient(self.dialog)
        dialog.grab_set()

        ttk.Label(dialog, text="Enter Download URL:").pack(pady=(10, 5))
        url_var = tk.StringVar(value=current_url)
        entry = ttk.Entry(dialog, textvariable=url_var, width=50)
        entry.pack(padx=10, pady=5, fill=tk.X)

        result = [None]

        def on_ok():
            result[0] = url_var.get().strip()
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=5)

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f'+{x}+{y}')
        self.dialog.wait_window(dialog)

        return result[0]

    # ---------- Helper: Test Package ID ----------
    def _test_package_id(self, provider, package_id):
        """
        Test if a package ID exists in Winget or Chocolatey.
        Returns (success, message, version) where version is the latest version string or None.
        """
        if not package_id:
            return False, "Package ID is empty", None

        try:
            if provider == 'winget':
                cmd = f"winget show {package_id}"
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',      # <-- ADDED
                    errors='ignore',       # <-- ADDED
                    timeout=30
                )
                if result.returncode == 0:
                    version = None
                    for line in result.stdout.split('\n'):
                        if 'Version' in line and ':' in line:
                            version = line.split(':', 1)[1].strip()
                            break
                    if version:
                        return True, f"Winget Found: {version}", version
                    else:
                        return True, "Package found (no version info)", None
                else:
                    error = result.stderr.strip() or result.stdout.strip()
                    if "not found" in error.lower() or "no such" in error.lower():
                        return False, "Package not found", None
                    else:
                        return False, f"Error: {error[:80]}", None
            elif provider == 'choco':
                cmd = f"choco find {package_id} --exact --limit-output"
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',      # <-- ADDED
                    errors='ignore',       # <-- ADDED
                    timeout=30
                )
                if result.returncode == 0:
                    version = None
                    for line in result.stdout.split('\n'):
                        if '|' in line:
                            parts = line.split('|')
                            if len(parts) >= 2:
                                version = parts[1].strip()
                                break
                    if version:
                        return True, f"Choco Found: {version}", version
                    else:
                        return True, "Package found (no version info)", None
                else:
                    error = result.stderr.strip() or result.stdout.strip()
                    if "not found" in error.lower() or "no such" in error.lower():
                        return False, "Package not found", None
                    else:
                        return False, f"Error: {error[:80]}", None
            else:
                return False, f"Unknown provider: {provider}", None
        except subprocess.TimeoutExpired:
            return False, "Timeout (package query took too long)", None
        except FileNotFoundError:
            return False, f"{provider.capitalize()} not installed", None
        except Exception as e:
            return False, f"Exception: {str(e)[:80]}", None
            
    def _test_package_id_ui(self, provider, package_id, status_label):
        """Test a package ID and update the status label."""
        if not package_id:
            try:
                status_label.config(text="Please enter a package ID", foreground="orange")
            except tk.TclError:
                pass
            return

        # Show checking message immediately
        try:
            status_label.config(text=f"⏳ Checking {provider}...", foreground="blue")
        except tk.TclError:
            pass

        def run_test():
            success, msg, version = self._test_package_id(provider, package_id)
            # Schedule UI update on the main thread
            def update_label():
                try:
                    if status_label.winfo_exists():
                        if success:
                            status_label.config(text=f"✅ {msg}", foreground="green")
                        else:
                            status_label.config(text=f"❌ {msg}", foreground="red")
                except tk.TclError:
                    pass
            try:
                self.dialog.after_idle(update_label)
            except tk.TclError:
                pass

        threading.Thread(target=run_test, daemon=True).start()
        
    # ---------- App Management Tab ----------
    def _build_apps_tab(self):
        frame = self.tab_apps
        columns = ('Name', 'Category', 'Type', 'Offline Path', 'Winget ID', 'Choco ID')
        self.tree_apps = ttk.Treeview(frame, columns=columns, show='headings')
        for col in columns:
            self.tree_apps.heading(col, text=col)
            self.tree_apps.column(col, width=100)
        self.tree_apps.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Make Apps tree draggable
        self._make_draggable(
            self.tree_apps,
            self.catalog.apps,
            lambda app: app.display_name,
            self.catalog._save_apps_to_config
        )

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="Add App", command=self._add_app).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Edit App", command=self._edit_app).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete App", command=self._delete_app).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Update Offline", command=self._update_offline).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Refresh", command=self._refresh_apps_list).pack(side=tk.LEFT, padx=2)

        self._refresh_apps_list()

    def _refresh_apps_list(self):
        self.tree_apps.delete(*self.tree_apps.get_children())
        self.catalog.refresh()
        for app in self.catalog.apps:
            self.tree_apps.insert('', tk.END, values=(
                app.display_name,
                app.category,
                app.install_type,
                app.offline_path,
                app.winget_id,
                app.choco_id
            ))

    def _add_app(self):
        self._edit_app_dialog(None)

    def _edit_app(self):
        selected = self.tree_apps.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select an app to edit.")
            return
        item = selected[0]
        values = self.tree_apps.item(item, 'values')
        display_name = values[0]
        app = self.catalog.get_app(display_name)
        if app:
            self._edit_app_dialog(app)

    def _delete_app(self):
        selected = self.tree_apps.selection()
        if not selected:
            return
        if messagebox.askyesno("Confirm Delete", "Delete selected app?"):
            item = selected[0]
            values = self.tree_apps.item(item, 'values')
            display_name = values[0]
            self.catalog.delete_app(display_name)
            self._refresh_apps_list()

    def _download_app(self, display_name, url=None, show_dialog=True, callback=None):
        app = self.catalog.get_app(display_name)
        if not app and not url:
            messagebox.showerror("Error", "App not found and no URL provided.")
            return False

        current_url = url if url is not None else (app.offline_download_url if app else "")
        if show_dialog:
            new_url = self._show_url_dialog(f"Download URL for {display_name}", current_url)
            if new_url is None:
                return False
            if new_url != current_url:
                current_url = new_url
        else:
            if not current_url:
                messagebox.showerror("Error", "Download URL is empty.")
                return False

        temp_app = None
        if not app:
            temp_data = {
                'display_name': display_name,
                'offline_download_url': current_url,
                'offline_path': ''
            }
            temp_app = self.catalog.add_app(temp_data)
            app = temp_app
        else:
            if current_url != app.offline_download_url:
                app.offline_download_url = current_url
                self.catalog._save_apps_to_config()

        progress_dlg = tk.Toplevel(self.dialog)
        progress_dlg.title("Downloading...")
        progress_dlg.geometry("300x80")
        ttk.Label(progress_dlg, text=f"Downloading {display_name}...").pack(pady=5)
        progress = ttk.Progressbar(progress_dlg, length=250, mode='determinate')
        progress.pack(pady=5)

        def update_progress(value):
            progress['value'] = value
            progress_dlg.update_idletasks()

        def do_download():
            success, msg = self.catalog.download_offline_installer(display_name, progress_callback=update_progress)
            progress_dlg.destroy()
            if success:
                messagebox.showinfo("Success", f"Download of {display_name} completed.")
                app_after = self.catalog.get_app(display_name)
                if callback and app_after:
                    callback(app_after.offline_path)
                self._refresh_apps_list()
                if temp_app:
                    self.catalog.delete_app(display_name)
            else:
                messagebox.showerror("Download Failed", msg)
                if temp_app:
                    self.catalog.delete_app(display_name)

        threading.Thread(target=do_download, daemon=True).start()
        return True

    def _sanitize_folder_name(self, name):
        return re.sub(r'[\\/*?:"<>|]', '_', name).strip()

    def _test_offline_installer(self, path_var, switch_var):
        offline_path = path_var.get().strip()
        switch = switch_var.get().strip()
        if not offline_path:
            messagebox.showerror("Error", "No offline path specified.")
            return
        if not os.path.isabs(offline_path):
            full_path = os.path.join(self.config.base_dir, offline_path)
        else:
            full_path = offline_path
        if not os.path.isfile(full_path):
            messagebox.showerror("Error", f"Installer file not found: {full_path}")
            return
        if full_path.lower().endswith('.msi'):
            cmd = f'msiexec /i "{full_path}" {switch}'
        else:
            cmd = f'"{full_path}" {switch}'

        test_dlg = tk.Toplevel(self.dialog)
        test_dlg.title("Testing Installer")
        test_dlg.geometry("500x400")
        test_dlg.transient(self.dialog)
        test_dlg.grab_set()

        ttk.Label(test_dlg, text=f"Testing: {os.path.basename(full_path)}").pack(pady=5)
        ttk.Label(test_dlg, text=f"Command: {cmd}").pack(pady=2)
        output_text = scrolledtext.ScrolledText(test_dlg, height=10, state='normal')
        output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        status_label = ttk.Label(test_dlg, text="Running...")
        status_label.pack(pady=5)

        def run_test():
            try:
                start_time = datetime.datetime.now()
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
                elapsed = (datetime.datetime.now() - start_time).total_seconds()
                try:
                    output_text.insert(tk.END, f"Exit code: {result.returncode}\n")
                    output_text.insert(tk.END, f"Time: {elapsed:.2f} seconds\n\n")
                    if result.stdout:
                        output_text.insert(tk.END, "--- STDOUT ---\n")
                        output_text.insert(tk.END, result.stdout)
                    if result.stderr:
                        output_text.insert(tk.END, "--- STDERR ---\n")
                        output_text.insert(tk.END, result.stderr)
                    output_text.see(tk.END)
                    if result.returncode == 0:
                        status_label.config(text="✅ SUCCESS", foreground="green")
                    else:
                        status_label.config(text=f"❌ FAILED (exit {result.returncode})", foreground="red")
                except tk.TclError:
                    pass
            except subprocess.TimeoutExpired:
                try:
                    output_text.insert(tk.END, "⏱️ Test timed out after 120 seconds.\n")
                    status_label.config(text="⏱️ TIMEOUT", foreground="orange")
                except tk.TclError:
                    pass
            except Exception as e:
                try:
                    output_text.insert(tk.END, f"⚠️ Error: {str(e)}\n")
                    status_label.config(text="⚠️ ERROR", foreground="red")
                except tk.TclError:
                    pass

        threading.Thread(target=run_test, daemon=True).start()

    def _edit_app_dialog(self, app):
        dialog = tk.Toplevel(self.dialog)
        dialog.title("Edit App" if app else "Add App")
        dialog.geometry("500x560")  # taller for status label
        dialog.transient(self.dialog)
        dialog.grab_set()

        dialog.columnconfigure(0, weight=0)
        dialog.columnconfigure(1, weight=1)

        display_var = tk.StringVar()
        category_var = tk.StringVar()
        offline_path_var = tk.StringVar()
        offline_switch_var = tk.StringVar()
        offline_version_var = tk.StringVar()
        download_url_var = tk.StringVar()
        winget_var = tk.StringVar()
        choco_var = tk.StringVar()
        install_type_var = tk.StringVar()
        post_install_path_var = tk.StringVar()
        original_offline_path = ""
        original_post_install_path = ""

        if app:
            display_var.set(app.display_name)
            category_var.set(app.category)
            offline_path_var.set(app.offline_path)
            original_offline_path = app.offline_path
            offline_switch_var.set(app.offline_switch)
            offline_version_var.set(app.offline_version)
            download_url_var.set(app.offline_download_url)
            winget_var.set(app.winget_id)
            choco_var.set(app.choco_id)
            install_type_var.set(app.install_type)
            post_install_path_var.set(app.post_install_script)
            original_post_install_path = app.post_install_script
        else:
            install_type_var.set('silent')

        row = 0
        # Display Name
        ttk.Label(dialog, text="Display Name:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=display_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Category
        ttk.Label(dialog, text="Category:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        categories = ['Browser', 'Utilities', 'Developer Tools', 'Office', 'Multimedia', 'Security', 'Communication', 'System', 'Other']
        cat_combo = ttk.Combobox(dialog, textvariable=category_var, values=categories, state='normal')
        cat_combo.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Offline Path
        ttk.Label(dialog, text="Offline Path:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        path_frame = ttk.Frame(dialog)
        path_frame.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        path_entry = ttk.Entry(path_frame, textvariable=offline_path_var)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_frame, text="Browse...", command=lambda: self._browse_offline_file(offline_path_var)).pack(side=tk.LEFT, padx=2)
        row += 1

        # Offline Switch
        ttk.Label(dialog, text="Offline Switch:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=offline_switch_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Offline Version
        ttk.Label(dialog, text="Offline Version:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=offline_version_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Download URL
        ttk.Label(dialog, text="Download URL:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=download_url_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Winget ID with Test button
        ttk.Label(dialog, text="Winget ID:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        winget_frame = ttk.Frame(dialog)
        winget_frame.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        winget_entry = ttk.Entry(winget_frame, textvariable=winget_var)
        winget_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(winget_frame, text="Test",
                   command=lambda: self._test_package_id_ui('winget', winget_var.get().strip(), status_label)).pack(side=tk.LEFT, padx=2)
        row += 1

        # Choco ID with Test button
        ttk.Label(dialog, text="Choco ID:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        choco_frame = ttk.Frame(dialog)
        choco_frame.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        choco_entry = ttk.Entry(choco_frame, textvariable=choco_var)
        choco_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(choco_frame, text="Test",
                   command=lambda: self._test_package_id_ui('choco', choco_var.get().strip(), status_label)).pack(side=tk.LEFT, padx=2)
        row += 1

        # Install Type
        ttk.Label(dialog, text="Install Type:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        install_types = ['silent', 'non_silent', 'driver', 'script', 'redist']
        install_combo = ttk.Combobox(dialog, textvariable=install_type_var, values=install_types, state='readonly')
        install_combo.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Status label for test results
        status_label = ttk.Label(dialog, text="", foreground="blue")
        status_label.grid(row=row, column=0, columnspan=2, sticky='w', padx=5, pady=2)
        row += 1

        # Post-Install Script
        ttk.Label(dialog, text="Post-Install Script:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        post_frame = ttk.Frame(dialog)
        post_frame.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        post_entry = ttk.Entry(post_frame, textvariable=post_install_path_var)
        post_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(post_frame, text="Browse...", command=lambda: self._browse_post_install_script(post_install_path_var)).pack(side=tk.LEFT, padx=2)
        row += 1

        # Action buttons: Test Installer & Download Now
        action_frame = ttk.Frame(dialog)
        action_frame.grid(row=row, column=0, columnspan=2, pady=10)
        action_frame.columnconfigure(0, weight=1)

        ttk.Button(action_frame, text="Test Installer",
                   command=lambda: self._test_offline_installer(offline_path_var, offline_switch_var)) \
            .pack(side=tk.LEFT, padx=5)

        ttk.Frame(action_frame, width=20).pack(side=tk.LEFT)

        def update_path_field(new_path):
            offline_path_var.set(new_path)

        download_btn_frame = ttk.Frame(action_frame)
        download_btn_frame.pack(side=tk.LEFT)
        ttk.Button(download_btn_frame, text="Download Now",
                   command=lambda: self._download_app(
                       display_var.get().strip(),
                       url=download_url_var.get().strip(),
                       show_dialog=False,
                       callback=update_path_field
                   )).pack(side=tk.LEFT)
        ttk.Label(download_btn_frame, text="(uses URL above)", foreground="gray").pack(side=tk.LEFT, padx=5)
        row += 1

        def save():
            data = {
                'display_name': display_var.get().strip(),
                'category': category_var.get().strip(),
                'offline_path': offline_path_var.get().strip(),
                'offline_switch': offline_switch_var.get().strip(),
                'offline_version': offline_version_var.get().strip(),
                'offline_download_url': download_url_var.get().strip(),
                'winget_id': winget_var.get().strip(),
                'choco_id': choco_var.get().strip(),
                'install_type': install_type_var.get(),
                'post_install_script': post_install_path_var.get().strip()
            }
            if not data['display_name']:
                messagebox.showerror("Error", "Display name is required")
                return

            # Copy offline installer
            offline_path = data['offline_path']
            if offline_path and os.path.isabs(offline_path) and offline_path != original_offline_path:
                if os.path.isfile(offline_path):
                    try:
                        folder_name = self._sanitize_folder_name(data['display_name'])
                        target_dir = os.path.join(self.config.base_dir, 'install', folder_name)
                        os.makedirs(target_dir, exist_ok=True)
                        original_filename = os.path.basename(offline_path)
                        target_file = os.path.join(target_dir, original_filename)
                        if os.path.abspath(offline_path) != os.path.abspath(target_file):
                            shutil.copy2(offline_path, target_file)
                        rel_path = os.path.join('install', folder_name, original_filename)
                        data['offline_path'] = rel_path
                    except PermissionError:
                        if not messagebox.askyesno("File Locked", f"Cannot copy the file because it is in use.\n\nWould you like to continue saving without copying the installer?"):
                            return
                        messagebox.showwarning("Warning", "The offline path will remain absolute. This may cause issues if the tool is moved.")
                else:
                    if not messagebox.askyesno("File Not Found", f"The file '{offline_path}' does not exist. Continue saving?"):
                        return

            # Copy post-install script
            post_script = data['post_install_script']
            if post_script and os.path.isabs(post_script) and os.path.isfile(post_script) and post_script != original_post_install_path:
                try:
                    folder_name = self._sanitize_folder_name(data['display_name'])
                    target_dir = os.path.join(self.config.base_dir, 'install', folder_name)
                    os.makedirs(target_dir, exist_ok=True)
                    ext = os.path.splitext(post_script)[1]
                    dest = os.path.join(target_dir, f"post_install{ext}")
                    shutil.copy2(post_script, dest)
                    data['post_install_script'] = os.path.join('install', folder_name, f"post_install{ext}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to copy post-install script: {e}")
            elif post_script and os.path.isabs(post_script) and post_script == original_post_install_path:
                pass

            if app:
                if self.catalog.update_app(app.display_name, data):
                    messagebox.showinfo("Success", "App updated.")
                    self._refresh_apps_list()
                    dialog.destroy()
                else:
                    messagebox.showerror("Error", "Update failed.")
            else:
                if self.catalog.get_app(data['display_name']):
                    messagebox.showerror("Error", "App with this name already exists.")
                    return
                self.catalog.add_app(data)
                self._refresh_apps_list()
                dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Save", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _browse_post_install_script(self, var):
        filetypes = [("Script files", "*.ps1;*.bat;*.cmd;*.py;*.reg"), ("All files", "*.*")]
        filename = filedialog.askopenfilename(title="Select Post-Install Script", filetypes=filetypes)
        if filename:
            var.set(filename)

    def _update_offline(self):
        selected = self.tree_apps.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select an app to update.")
            return
        item = selected[0]
        values = self.tree_apps.item(item, 'values')
        display_name = values[0]
        self._download_app(display_name, show_dialog=True)

    def _browse_offline_file(self, path_var):
        filetypes = [("Executable files", "*.exe"), ("MSI files", "*.msi"), ("MSIX files", "*.msix"),
                     ("Batch files", "*.bat;*.cmd"), ("PowerShell scripts", "*.ps1"), ("All files", "*.*")]
        filename = filedialog.askopenfilename(title="Select Offline Installer", filetypes=filetypes)
        if filename:
            path_var.set(filename)

    # ---------- Command Templates Tab ----------
    def _build_commands_tab(self):
        frame = self.tab_commands
        self.command_entries = {}
        templates = self.config.settings.get('command_templates', {})
        row = 0
        for key, value in templates.items():
            label = ttk.Label(frame, text=key.replace('_', ' ').title())
            label.grid(row=row, column=0, sticky='e', padx=5, pady=2)
            var = tk.StringVar(value=value)
            entry = ttk.Entry(frame, textvariable=var, width=60)
            entry.grid(row=row, column=1, padx=5, pady=2, sticky='w')
            self.command_entries[key] = var
            row += 1
        ttk.Button(frame, text="Save Templates", command=self._save_commands).grid(row=row, column=0, columnspan=2, pady=10)

    def _save_commands(self):
        templates = {key: var.get() for key, var in self.command_entries.items()}
        self.config.settings['command_templates'] = templates
        self.config.save_settings()
        messagebox.showinfo("Saved", "Command templates saved.")

    # ---------- Operations Tab ----------
    def _build_operations_tab(self):
        frame = self.tab_operations
        self.op_vars = {}
        ops = self.config.settings.get('available_operations', [])
        row = 0
        for op in ops:
            var = tk.BooleanVar(value=op.get('enabled', True))
            chk = ttk.Checkbutton(frame, text=op.get('display', op.get('internal')), variable=var)
            chk.grid(row=row, column=0, sticky='w', padx=5, pady=2)
            self.op_vars[op['internal']] = var
            row += 1
        ttk.Button(frame, text="Save Operations", command=self._save_operations).grid(row=row, column=0, pady=10)

    def _save_operations(self):
        ops = self.config.settings.get('available_operations', [])
        for op in ops:
            if op['internal'] in self.op_vars:
                op['enabled'] = self.op_vars[op['internal']].get()
        self.config.save_settings()
        messagebox.showinfo("Saved", "Operations configuration saved.")

    # ---------- Tweaks Management Tab ----------
    def _build_tweaks_tab(self):
        frame = self.tab_tweaks

        columns = ('name', 'description', 'type', 'category')
        self.tree_tweaks = ttk.Treeview(frame, columns=columns, show='headings')
        self.tree_tweaks.heading('name', text='Name')
        self.tree_tweaks.heading('description', text='Description')
        self.tree_tweaks.heading('type', text='Script Type')
        self.tree_tweaks.heading('category', text='Category')

        self.tree_tweaks.column('name', width=180)
        self.tree_tweaks.column('description', width=300)
        self.tree_tweaks.column('type', width=90)
        self.tree_tweaks.column('category', width=120)

        self.tree_tweaks.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Get tweaks list and make it draggable
        tweaks_list = self.config.tweaks.get('tweaks', [])
        self._make_draggable(
            self.tree_tweaks,
            tweaks_list,
            lambda t: t.get('name', ''),
            self.config.save_tweaks
        )

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="Add Tweak", command=self._add_tweak).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Edit Tweak", command=self._edit_tweak).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete Tweak", command=self._delete_tweak).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Refresh", command=self._refresh_tweaks_list).pack(side=tk.LEFT, padx=2)

        self._refresh_tweaks_list()

    def _refresh_tweaks_list(self):
        self.tree_tweaks.delete(*self.tree_tweaks.get_children())
        self.config.tweaks = self.config._load_json(self.config.tweaks_file)
        for tweak in self.config.tweaks.get('tweaks', []):
            if tweak.get('is_builtin', False):
                script_type = "Built-in"
            else:
                script_type = tweak.get('script_type', 'ps1').upper()
            self.tree_tweaks.insert('', tk.END, values=(
                tweak.get('name', ''),
                tweak.get('description', ''),
                script_type,
                tweak.get('category', '')
            ))

    def _add_tweak(self):
        self._edit_tweak_dialog(None)

    def _edit_tweak(self):
        selected = self.tree_tweaks.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select a tweak to edit.")
            return
        item = selected[0]
        values = self.tree_tweaks.item(item, 'values')
        name = values[0]
        tweak = None
        for t in self.config.tweaks.get('tweaks', []):
            if t.get('name') == name:
                tweak = t
                break
        if tweak:
            if tweak.get('is_builtin', False):
                messagebox.showinfo("Info", "Built‑in tweaks cannot be edited.")
                return
            self._edit_tweak_dialog(tweak)

    def _delete_tweak(self):
        selected = self.tree_tweaks.selection()
        if not selected:
            return
        item = selected[0]
        values = self.tree_tweaks.item(item, 'values')
        name = values[0]
        for t in self.config.tweaks.get('tweaks', []):
            if t.get('name') == name and t.get('is_builtin', False):
                messagebox.showinfo("Info", "Built‑in tweaks cannot be deleted.")
                return
        if messagebox.askyesno("Confirm Delete", "Delete selected tweak?"):
            tweaks_list = self.config.tweaks.get('tweaks', [])
            self.config.tweaks['tweaks'] = [t for t in tweaks_list if t.get('name') != name]
            self.config.save_tweaks()
            self._refresh_tweaks_list()

    # ---------- Tweaks Edit Dialog ----------
    def _edit_tweak_dialog(self, tweak):
        dialog = tk.Toplevel(self.dialog)
        dialog.title("Edit Tweak" if tweak else "Add Tweak")
        dialog.geometry("500x450")
        dialog.transient(self.dialog)
        dialog.grab_set()

        dialog.columnconfigure(0, weight=0)
        dialog.columnconfigure(1, weight=1)

        name_var = tk.StringVar()
        category_var = tk.StringVar()
        desc_var = tk.StringVar()
        script_type_var = tk.StringVar(value='ps1')
        enable_var = tk.StringVar()
        disable_var = tk.StringVar()
        args_var = tk.StringVar()

        if tweak:
            name_var.set(tweak.get('name', ''))
            category_var.set(tweak.get('category', ''))
            desc_var.set(tweak.get('description', ''))
            script_type_var.set(tweak.get('script_type', 'ps1'))
            enable_var.set(tweak.get('enable_script', ''))
            disable_var.set(tweak.get('disable_script', ''))
            args_var.set(tweak.get('arguments', ''))

        row = 0

        # Name
        ttk.Label(dialog, text="Name:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=name_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Category
        ttk.Label(dialog, text="Category:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        existing_categories = sorted(set(
            t.get('category', '') for t in self.config.tweaks.get('tweaks', []) if t.get('category')
        ))
        cat_combo = ttk.Combobox(dialog, textvariable=category_var, values=existing_categories, state='normal')
        cat_combo.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Description
        ttk.Label(dialog, text="Description:").grid(row=row, column=0, sticky='ne', padx=5, pady=2)
        desc_frame = ttk.Frame(dialog)
        desc_frame.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        desc_text = tk.Text(desc_frame, height=3, wrap='word')
        desc_text.insert('1.0', desc_var.get())
        desc_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        desc_scroll = ttk.Scrollbar(desc_frame, orient='vertical', command=desc_text.yview)
        desc_text.configure(yscrollcommand=desc_scroll.set)
        desc_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        row += 1

        # Script Type
        ttk.Label(dialog, text="Script Type:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        script_combo = ttk.Combobox(dialog, textvariable=script_type_var, values=['ps1', 'bat', 'py', 'reg'], state='readonly')
        script_combo.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Arguments
        ttk.Label(dialog, text="Arguments:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=args_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Enable Script
        ttk.Label(dialog, text="Enable Script:").grid(row=row, column=0, sticky='ne', padx=5, pady=2)
        enable_frame = ttk.Frame(dialog)
        enable_frame.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        enable_preview = ttk.Label(enable_frame, text="", anchor='w', relief='sunken')
        enable_preview.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(enable_frame, text="Edit...", command=lambda: self._edit_script_popup(enable_var, enable_preview)).pack(side=tk.LEFT, padx=2)
        ttk.Button(enable_frame, text="Browse...", command=lambda: self._browse_script_file(enable_var, enable_preview, script_type_var)).pack(side=tk.LEFT, padx=2)
        self._update_script_preview(enable_var, enable_preview)
        row += 1

        # Disable Script
        ttk.Label(dialog, text="Disable Script:").grid(row=row, column=0, sticky='ne', padx=5, pady=2)
        disable_frame = ttk.Frame(dialog)
        disable_frame.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        disable_preview = ttk.Label(disable_frame, text="", anchor='w', relief='sunken')
        disable_preview.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(disable_frame, text="Edit...", command=lambda: self._edit_script_popup(disable_var, disable_preview)).pack(side=tk.LEFT, padx=2)
        ttk.Button(disable_frame, text="Browse...", command=lambda: self._browse_script_file(disable_var, disable_preview, script_type_var)).pack(side=tk.LEFT, padx=2)
        self._update_script_preview(disable_var, disable_preview)
        row += 1

        # Test Script
        ttk.Button(dialog, text="Test Script",
                   command=lambda: self._test_tweak_script(enable_var, disable_var, script_type_var, args_var)) \
            .grid(row=row, column=1, sticky='w', padx=(5,10), pady=5)
        row += 1

        def save_tweak():
            description = desc_text.get("1.0", tk.END).strip()
            data = {
                'name': name_var.get().strip(),
                'category': category_var.get().strip(),
                'description': description,
                'script_type': script_type_var.get(),
                'arguments': args_var.get().strip(),
                'enable_script': enable_var.get().strip(),
                'disable_script': disable_var.get().strip(),
                'enabled': False
            }
            if not data['name']:
                messagebox.showerror("Error", "Name is required")
                return

            if tweak:
                data['enabled'] = tweak.get('enabled', False)

            def copy_script_file(script_var, suffix):
                path = script_var.get().strip()
                if not path:
                    return path
                if os.path.isabs(path) and os.path.isfile(path):
                    folder = os.path.join(self.config.base_dir, 'tweaks', data['name'])
                    os.makedirs(folder, exist_ok=True)
                    ext = os.path.splitext(path)[1]
                    dest = os.path.join(folder, f"script_{suffix}{ext}")
                    shutil.copy2(path, dest)
                    return os.path.join('tweaks', data['name'], f"script_{suffix}{ext}")
                return path

            data['enable_script'] = copy_script_file(enable_var, 'enable')
            data['disable_script'] = copy_script_file(disable_var, 'disable')

            tweaks_list = self.config.tweaks.get('tweaks', [])
            if tweak:
                for i, t in enumerate(tweaks_list):
                    if t.get('name') == tweak.get('name'):
                        tweaks_list[i] = data
                        break
            else:
                if any(t.get('name') == data['name'] for t in tweaks_list):
                    messagebox.showerror("Error", "Tweak with this name already exists.")
                    return
                tweaks_list.append(data)

            self.config.tweaks['tweaks'] = tweaks_list
            self.config.save_tweaks()
            self._refresh_tweaks_list()
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Save", command=save_tweak).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _update_script_preview(self, var, preview_label):
        text = var.get().strip()
        if text:
            preview = text[:50] + ('...' if len(text) > 50 else '')
            preview_label.config(text=preview)
        else:
            preview_label.config(text="(empty)")

    def _edit_script_popup(self, var, preview_label):
        popup = tk.Toplevel(self.dialog)
        popup.title("Edit Script")
        popup.geometry("600x400")
        popup.transient(self.dialog)
        popup.grab_set()

        ttk.Label(popup, text="Edit Script Content (inline):").pack(pady=5)
        text_widget = scrolledtext.ScrolledText(popup, height=15, width=70)
        text_widget.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        text_widget.insert(tk.END, var.get())

        def save_script():
            var.set(text_widget.get("1.0", tk.END).strip())
            self._update_script_preview(var, preview_label)
            popup.destroy()

        btn_frame = ttk.Frame(popup)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Save", command=save_script).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=popup.destroy).pack(side=tk.LEFT, padx=5)

    def _test_tweak_script(self, enable_var, disable_var, script_type_var, args_var):
        from modules.script_engine import ScriptEngine
        engine = ScriptEngine(self.config)

        script = enable_var.get().strip()
        script_type = script_type_var.get()
        arguments = args_var.get().strip()
        if not script:
            script = disable_var.get().strip()
            if not script:
                messagebox.showerror("Error", "No script to test (enable or disable) is defined.")
                return

        test_dlg = tk.Toplevel(self.dialog)
        test_dlg.title("Test Script Output")
        test_dlg.geometry("600x400")
        test_dlg.transient(self.dialog)
        test_dlg.grab_set()

        instruction = ttk.Label(test_dlg,
            text="A new console window will open for interactive scripts.\n"
                 "Please complete the script interaction there.\n"
                 "Status will update when the script finishes.",
            foreground="blue", justify='center')
        instruction.pack(pady=5)

        output_text = scrolledtext.ScrolledText(test_dlg, height=12, state='normal')
        output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        status_label = ttk.Label(test_dlg, text="Running...")
        status_label.pack(pady=5)

        def safe_insert(msg):
            try:
                output_text.insert(tk.END, msg + "\n")
                output_text.see(tk.END)
                test_dlg.update_idletasks()
            except tk.TclError:
                pass

        def run_test():
            def log_cb(msg):
                test_dlg.after(0, lambda: safe_insert(msg))
            log_cb(f"Testing script (type: {script_type}, args: {arguments})...")
            success, msg = engine.test_script(script, script_type, log_cb, arguments)
            try:
                status_label.config(
                    text="✅ SUCCESS" if success else "❌ FAILED",
                    foreground="green" if success else "red"
                )
            except tk.TclError:
                pass
            if not success:
                try:
                    safe_insert(f"Error: {msg}")
                except:
                    pass

        threading.Thread(target=run_test, daemon=True).start()

    def _browse_script_file(self, var, preview_label, script_type_var=None):
        filetypes = [
            ("Script files", "*.ps1;*.bat;*.cmd;*.py;*.reg"),
            ("All files", "*.*")
        ]
        filename = filedialog.askopenfilename(title="Select Script File", filetypes=filetypes)
        if filename:
            var.set(filename)
            self._update_script_preview(var, preview_label)
            if script_type_var:
                ext = os.path.splitext(filename)[1].lower()
                ext_map = {'.ps1': 'ps1', '.bat': 'bat', '.cmd': 'bat', '.py': 'py', '.reg': 'reg'}
                if ext in ext_map:
                    script_type_var.set(ext_map[ext])

    # ---------- Activators Management Tab ----------
    def _build_activators_tab(self):
        frame = self.tab_activators
        columns = ('Name', 'Category', 'Description', 'Executable', 'Default Switches')
        self.tree_activators = ttk.Treeview(frame, columns=columns, show='headings')
        for col in columns:
            self.tree_activators.heading(col, text=col)
            self.tree_activators.column(col, width=120)
        self.tree_activators.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Get activators list and make it draggable
        activators_list = self.config.activators.get('activators', [])
        self._make_draggable(
            self.tree_activators,
            activators_list,
            lambda a: a.get('name', ''),
            self.config.save_activators
        )

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="Add Activator", command=self._add_activator).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Edit Activator", command=self._edit_activator).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete Activator", command=self._delete_activator).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Download", command=self._download_selected_activator).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Refresh", command=self._refresh_activators_list).pack(side=tk.LEFT, padx=2)

        self._refresh_activators_list()

    def _refresh_activators_list(self):
        self.tree_activators.delete(*self.tree_activators.get_children())
        self.config.activators = self.config._load_json(self.config.activators_file)
        for act in self.config.activators.get('activators', []):
            self.tree_activators.insert('', tk.END, values=(
                act.get('name', ''),
                act.get('category', ''),
                act.get('description', ''),
                act.get('executable', ''),
                act.get('default_switches', '')
            ))

    def _add_activator(self):
        self._edit_activator_dialog(None)

    def _edit_activator(self):
        selected = self.tree_activators.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select an activator to edit.")
            return
        item = selected[0]
        values = self.tree_activators.item(item, 'values')
        name = values[0]
        act = None
        for a in self.config.activators.get('activators', []):
            if a.get('name') == name:
                act = a
                break
        if act:
            self._edit_activator_dialog(act)

    def _delete_activator(self):
        selected = self.tree_activators.selection()
        if not selected:
            return
        if messagebox.askyesno("Confirm Delete", "Delete selected activator?"):
            item = selected[0]
            values = self.tree_activators.item(item, 'values')
            name = values[0]
            activators_list = self.config.activators.get('activators', [])
            self.config.activators['activators'] = [a for a in activators_list if a.get('name') != name]
            self.config.save_activators()
            self._refresh_activators_list()

    # ---------- Activators Edit Dialog ----------
    def _edit_activator_dialog(self, activator):
        dialog = tk.Toplevel(self.dialog)
        dialog.title("Edit Activator" if activator else "Add Activator")
        dialog.geometry("550x400")
        dialog.transient(self.dialog)
        dialog.grab_set()

        dialog.columnconfigure(0, weight=0)
        dialog.columnconfigure(1, weight=1)
        dialog.columnconfigure(2, weight=0)

        name_var = tk.StringVar()
        category_var = tk.StringVar()
        desc_var = tk.StringVar()
        exec_var = tk.StringVar()
        folder_var = tk.StringVar()
        archive_var = tk.StringVar()
        switches_var = tk.StringVar()
        download_url_var = tk.StringVar()
        github_repo_var = tk.StringVar()
        github_pattern_var = tk.StringVar()

        if activator:
            name_var.set(activator.get('name', ''))
            category_var.set(activator.get('category', ''))
            desc_var.set(activator.get('description', ''))
            exec_var.set(activator.get('executable', ''))
            folder_var.set(activator.get('folder', ''))
            archive_var.set(activator.get('archive', ''))
            switches_var.set(activator.get('default_switches', ''))
            download_url_var.set(activator.get('download_url', ''))
            github_repo_var.set(activator.get('github_repo', ''))
            github_pattern_var.set(activator.get('github_asset_pattern', ''))

        row = 0
        # Name
        ttk.Label(dialog, text="Name:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=name_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Category
        ttk.Label(dialog, text="Category:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        existing_categories = sorted(set(
            a.get('category', '') for a in self.config.activators.get('activators', []) if a.get('category')
        ))
        cat_combo = ttk.Combobox(dialog, textvariable=category_var, values=existing_categories, state='normal')
        cat_combo.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Description
        ttk.Label(dialog, text="Description:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=desc_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Main Executable
        ttk.Label(dialog, text="Main Executable (filename):").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        exec_frame = ttk.Frame(dialog)
        exec_frame.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        exec_entry = ttk.Entry(exec_frame, textvariable=exec_var)
        exec_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(exec_frame, text="Browse...", command=lambda: self._browse_file_for_activator(exec_var, 'file')).pack(side=tk.LEFT, padx=2)
        row += 1

        # Folder
        ttk.Label(dialog, text="Folder (optional – full folder with all files):").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        folder_frame = ttk.Frame(dialog)
        folder_frame.grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        folder_entry = ttk.Entry(folder_frame, textvariable=folder_var)
        folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(folder_frame, text="Browse...", command=lambda: self._browse_file_for_activator(folder_var, 'folder')).pack(side=tk.LEFT, padx=2)
        row += 1

        # Archive – entry only, label moved to next row
        ttk.Label(dialog, text="Archive (if folder selected, will be zipped):").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=archive_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        ttk.Label(dialog, text="(Leave empty – auto-generated)", foreground="gray").grid(row=row, column=1, sticky='w', padx=(5,10), pady=(0,5))
        row += 1

        # Default Switches
        ttk.Label(dialog, text="Default Switches:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=switches_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Download URL
        ttk.Label(dialog, text="Download URL:").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=download_url_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # GitHub Repo
        ttk.Label(dialog, text="GitHub Repo (user/repo):").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=github_repo_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # GitHub Asset Pattern
        ttk.Label(dialog, text="GitHub Asset Pattern (e.g., *.zip):").grid(row=row, column=0, sticky='e', padx=5, pady=2)
        ttk.Entry(dialog, textvariable=github_pattern_var).grid(row=row, column=1, padx=(5,10), pady=2, sticky='we')
        row += 1

        # Download Now button
        download_frame = ttk.Frame(dialog)
        download_frame.grid(row=row, column=0, columnspan=2, pady=5)
        ttk.Button(download_frame, text="Download Now (from URL/GitHub)",
                   command=lambda: self._download_activator(
                       name_var.get().strip(),
                       {
                           'download_url': download_url_var.get().strip(),
                           'github_repo': github_repo_var.get().strip(),
                           'github_asset_pattern': github_pattern_var.get().strip()
                       },
                       show_dialog=False
                   )).pack()
        row += 1

        def save_activator():
            data = {
                'name': name_var.get().strip(),
                'category': category_var.get().strip(),
                'description': desc_var.get().strip(),
                'executable': exec_var.get().strip(),
                'folder': folder_var.get().strip(),
                'archive': archive_var.get().strip(),
                'default_switches': switches_var.get().strip(),
                'download_url': download_url_var.get().strip(),
                'github_repo': github_repo_var.get().strip(),
                'github_asset_pattern': github_pattern_var.get().strip()
            }

            if not data['name']:
                messagebox.showerror("Error", "Name is required")
                return
            if not data['executable']:
                messagebox.showerror("Error", "Main executable is required")
                return

            # Handle folder compression
            if data['folder'] and os.path.isdir(data['folder']):
                if not data['archive'] or messagebox.askyesno("Compress Folder",
                                                              "The folder will be compressed to a .7z archive. Continue?"):
                    import time
                    archive_name = f"activator_{data['name'].replace(' ', '_')}_{int(time.time())}.7z"
                    try:
                        import py7zr
                        activators_dir = os.path.join(self.config.base_dir, 'activators')
                        os.makedirs(activators_dir, exist_ok=True)
                        with py7zr.SevenZipFile(os.path.join(activators_dir, archive_name), 'w') as archive:
                            archive.writeall(data['folder'], arcname=os.path.basename(data['folder']))
                        data['archive'] = archive_name
                        data['folder'] = ''
                    except ImportError:
                        messagebox.showerror("Error", "py7zr module is required to compress activator folder. Install: pip install py7zr")
                        return
                    except Exception as e:
                        messagebox.showerror("Error", f"Failed to compress folder: {str(e)}")
                        return

            activators_list = self.config.activators.get('activators', [])
            if activator:
                for i, a in enumerate(activators_list):
                    if a.get('name') == activator.get('name'):
                        activators_list[i] = data
                        break
            else:
                if any(a.get('name') == data['name'] for a in activators_list):
                    messagebox.showerror("Error", "Activator with this name already exists.")
                    return
                activators_list.append(data)

            self.config.activators['activators'] = activators_list
            self.config.save_activators()
            self._refresh_activators_list()
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Save", command=save_activator).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _browse_file_for_activator(self, var, mode='file'):
        if mode == 'file':
            filename = filedialog.askopenfilename(title="Select Main Executable",
                                                  filetypes=[("Executable files", "*.exe;*.cmd;*.bat;*.ps1"), ("All files", "*.*")])
            if filename:
                var.set(filename)
        else:
            folder = filedialog.askdirectory(title="Select Activator Folder")
            if folder:
                var.set(folder)

    def _download_activator(self, name, activator_dict, show_dialog=True):
        current_url = activator_dict.get('download_url', '')
        if show_dialog:
            new_url = self._show_url_dialog(f"Download URL for {name}", current_url)
            if new_url is None:
                return False
            if new_url != current_url:
                activator_dict['download_url'] = new_url
                current_url = new_url
        else:
            if not current_url:
                messagebox.showerror("Error", "Download URL is empty.")
                return False

        # Update real activator in config if it exists
        real_act = None
        for a in self.config.activators.get('activators', []):
            if a.get('name') == name:
                real_act = a
                break
        if real_act:
            if current_url != real_act.get('download_url'):
                real_act['download_url'] = current_url
                self.config.save_activators()

        from modules.activator_engine import ActivatorEngine
        engine = ActivatorEngine(self.config)
        download_dict = {
            'name': name,
            'download_url': current_url,
            'github_repo': activator_dict.get('github_repo', ''),
            'github_asset_pattern': activator_dict.get('github_asset_pattern', '')
        }

        progress_dlg = tk.Toplevel(self.dialog)
        progress_dlg.title("Downloading Activator")
        progress_dlg.geometry("400x80")
        progress_dlg.transient(self.dialog)
        progress_dlg.grab_set()

        ttk.Label(progress_dlg, text=f"Downloading {name}...").pack(pady=5)
        progress = ttk.Progressbar(progress_dlg, length=350, mode='determinate')
        progress.pack(pady=5)

        def update_progress(value):
            progress['value'] = value
            progress_dlg.update_idletasks()

        def do_download():
            def log_cb(msg):
                print(f"[Download] {msg}")
            success, msg, file_path = engine.download_activator(download_dict, update_progress, log_cb)
            progress_dlg.destroy()
            if success:
                messagebox.showinfo("Success", f"Download of {name} completed.")
                self._refresh_activators_list()
            else:
                messagebox.showerror("Download Failed", msg)

        threading.Thread(target=do_download, daemon=True).start()
        return True

    def _download_selected_activator(self):
        selected = self.tree_activators.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select an activator to download.")
            return
        item = selected[0]
        values = self.tree_activators.item(item, 'values')
        name = values[0]
        act = next((a for a in self.config.activators.get('activators', []) if a.get('name') == name), None)
        if act:
            self._download_activator(name, act, show_dialog=True)

    # ---------- General Tab ----------
    def _build_general_tab(self):
        frame = self.tab_general

        ttk.Label(frame, text="Default Online Provider:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        provider_var = tk.StringVar(value=self.config.settings.get('general', {}).get('default_provider', 'winget'))
        provider_menu = ttk.Combobox(frame, textvariable=provider_var, values=['winget', 'chocolatey'], state='readonly')
        provider_menu.grid(row=0, column=1, sticky='w', padx=5, pady=5)

        ttk.Label(frame, text="Log Level:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        log_var = tk.StringVar(value=self.config.settings.get('general', {}).get('log_level', 'verbose'))
        log_menu = ttk.Combobox(frame, textvariable=log_var, values=['verbose', 'normal', 'errors'], state='readonly')
        log_menu.grid(row=1, column=1, sticky='w', padx=5, pady=5)

        ttk.Label(frame, text="Archive Format:").grid(row=2, column=0, sticky='e', padx=5, pady=5)
        archive_var = tk.StringVar(value=self.config.settings.get('general', {}).get('archive_format', 'zip'))
        archive_menu = ttk.Combobox(frame, textvariable=archive_var, values=['zip', '7z'], state='readonly')
        archive_menu.grid(row=2, column=1, sticky='w', padx=5, pady=5)

        ttk.Label(frame, text="Backup Destination:").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        backup_var = tk.StringVar(value=self.config.settings.get('general', {}).get('backup_destination', 'backups'))
        backup_entry = ttk.Entry(frame, textvariable=backup_var, width=40)
        backup_entry.grid(row=3, column=1, sticky='w', padx=5, pady=5)

        def browse_backup():
            path = filedialog.askdirectory()
            if path:
                backup_var.set(path)
        ttk.Button(frame, text="Browse", command=browse_backup).grid(row=3, column=2, padx=5)

        def save_general():
            self.config.settings['general']['default_provider'] = provider_var.get()
            self.config.settings['general']['log_level'] = log_var.get()
            self.config.settings['general']['archive_format'] = archive_var.get()
            self.config.settings['general']['backup_destination'] = backup_var.get()
            self.config.save_settings()
            messagebox.showinfo("Saved", "General settings saved.")

        ttk.Button(frame, text="Save General Settings", command=save_general).grid(row=4, column=0, columnspan=2, pady=10)