"""
ProfileManager - Handles saving and loading of deployment profiles.
"""

import os
import json
import logging
import re
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

class ProfileManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.profiles_dir = os.path.join(base_dir, 'profiles')
        os.makedirs(self.profiles_dir, exist_ok=True)

    def list_profiles(self):
        """Return a list of profile names (without .profile)."""
        if not os.path.isdir(self.profiles_dir):
            return []
        files = [f for f in os.listdir(self.profiles_dir) if f.endswith('.profile')]
        return [os.path.splitext(f)[0] for f in files]

    def save_profile(self, name, data):
        """Save profile data to a .profile file."""
        if not name.strip():
            raise ValueError("Profile name cannot be empty")
        safe_name = self._sanitize_name(name)
        filepath = os.path.join(self.profiles_dir, safe_name + '.profile')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.getLogger('DeploymentKit').info(f"Profile '{name}' saved")

    def load_profile(self, name):
        """Load profile data from a .profile file."""
        safe_name = self._sanitize_name(name)
        filepath = os.path.join(self.profiles_dir, safe_name + '.profile')
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Profile '{name}' not found")
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    def delete_profile(self, name):
        """Delete a profile file."""
        safe_name = self._sanitize_name(name)
        filepath = os.path.join(self.profiles_dir, safe_name + '.profile')
        if os.path.isfile(filepath):
            os.remove(filepath)
            logging.getLogger('DeploymentKit').info(f"Profile '{name}' deleted")
            return True
        return False

    def _sanitize_name(self, name):
        """Replace unsafe characters for filenames."""
        return re.sub(r'[^a-zA-Z0-9 _\-.]+', '', name.strip())

    # ---------- GUI Dialogs ----------
    def manage_profiles_dialog(self, parent, collect_data_callback, apply_data_callback, log_callback):
        """Open a unified dialog to manage profiles: Load, Save, Delete."""
        dialog = tk.Toplevel(parent)
        dialog.title("Manage Profiles")
        dialog.geometry("450x400")
        dialog.transient(parent)
        dialog.grab_set()

        # ----- Listbox with scrollbar -----
        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        listbox = tk.Listbox(frame, selectmode=tk.SINGLE)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.configure(yscrollcommand=scrollbar.set)

        def refresh_list():
            listbox.delete(0, tk.END)
            for p in self.list_profiles():
                listbox.insert(tk.END, p)

        refresh_list()

        # ----- Buttons -----
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        def do_load():
            sel = listbox.curselection()
            if not sel:
                messagebox.showinfo("No Selection", "Please select a profile to load.")
                return
            name = listbox.get(sel[0])
            try:
                data = self.load_profile(name)
                missing = apply_data_callback(data)
                log_callback(f"✅ Profile '{name}' loaded successfully.\n")
                if any(missing.values()):
                    log_callback("⚠️ Missing items:\n")
                    for cat, items in missing.items():
                        if items:
                            log_callback(f"  {cat}: {', '.join(items)}\n")
                    self._show_missing_items_dialog(parent, missing, name)
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load profile: {e}")

        def do_save():
            from tkinter import simpledialog
            name = simpledialog.askstring("Save Profile", "Enter a name for this profile:")
            if not name:
                return
            existing = self.list_profiles()
            if name in existing:
                if not messagebox.askyesno("Overwrite", f"Profile '{name}' already exists. Overwrite?"):
                    return
            data = collect_data_callback()
            try:
                self.save_profile(name, data)
                log_callback(f"✅ Profile '{name}' saved successfully.\n")
                refresh_list()
                for i, p in enumerate(self.list_profiles()):
                    if p == name:
                        listbox.selection_set(i)
                        break
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save profile: {e}")

        def do_delete():
            sel = listbox.curselection()
            if not sel:
                messagebox.showinfo("No Selection", "Please select a profile to delete.")
                return
            name = listbox.get(sel[0])
            if messagebox.askyesno("Confirm Delete", f"Delete profile '{name}'?"):
                self.delete_profile(name)
                log_callback(f"Profile '{name}' deleted.\n")
                refresh_list()

        ttk.Button(btn_frame, text="Load", command=do_load).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save", command=do_save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Delete", command=do_delete).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Refresh", command=refresh_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def _show_missing_items_dialog(self, parent, missing, profile_name=None):
        """Display a formatted dialog listing missing items from a loaded profile."""
        # Build the message
        lines = []
        if profile_name:
            lines.append(f"Profile: {profile_name}")
            lines.append("")
        lines.append("The following items from the profile were not found")
        lines.append("in the current configuration and have been skipped:")
        lines.append("")

        has_items = any(items for items in missing.values() if items)
        if not has_items:
            return

        for category, items in missing.items():
            if not items:
                continue
            lines.append(f"{category}:")
            for item in items:
                lines.append(f"  • {item}")
            lines.append("")

        message = "\n".join(lines)

        dialog = tk.Toplevel(parent)
        dialog.title("Missing Items" + (f" – {profile_name}" if profile_name else ""))
        dialog.geometry("550x350")
        dialog.minsize(400, 250)
        dialog.transient(parent)
        dialog.grab_set()

        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        text = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, font=('Consolas', 10))
        text.pack(fill=tk.BOTH, expand=True)

        text.insert(tk.END, message)
        text.config(state=tk.DISABLED)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        def copy_to_clipboard():
            parent.clipboard_clear()
            parent.clipboard_append(message)
            parent.update()
            copy_btn.config(text="Copied!")
            dialog.after(1500, lambda: copy_btn.config(text="Copy to Clipboard"))

        copy_btn = ttk.Button(btn_frame, text="Copy to Clipboard", command=copy_to_clipboard)
        copy_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="Close", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)