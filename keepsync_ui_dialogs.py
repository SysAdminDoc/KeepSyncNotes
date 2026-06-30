"""Standalone CustomTkinter dialogs for KeepSyncNotes."""

import threading
import webbrowser
from pathlib import Path
from tkinter import messagebox
from typing import Any, Callable, Dict

import customtkinter as ctk

from keepsync_diagnostics import DiagnosticsManager
from keepsync_models import KEEP_COLOR_PALETTE, Note, normalize_keep_color
from keepsync_note_ops import default_advanced_filters, note_conflict_diff
from keepsync_theme import COLORS
from keepsync_ui_modal import configure_modal_dialog


class AdvancedFilterDialog(ctk.CTkToplevel):
    """Advanced note filter editor."""

    def __init__(self, parent, filters: Dict[str, Any], on_apply: Callable[[Dict[str, Any]], None]):
        super().__init__(parent)
        self.filters = dict(default_advanced_filters())
        self.filters.update(filters or {})
        self.on_apply = on_apply

        self.title("Advanced Filters")
        self.geometry("420x520")
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        configure_modal_dialog(self, parent, initial_focus=self.label_entry)

    def _build_ui(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text="Advanced Filters",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(0, 16))

        self.mode_var = ctk.StringVar(value=self.filters.get("mode", "AND"))
        self.mode_menu = ctk.CTkOptionMenu(
            frame,
            values=["AND", "OR"],
            variable=self.mode_var,
            fg_color=COLORS["bg_medium"],
            button_color=COLORS["bg_hover"],
            button_hover_color=COLORS["accent_blue"],
            text_color=COLORS["text_primary"]
        )
        self.mode_menu.pack(fill="x", pady=(0, 10))

        self.label_entry = self._entry(frame, "Label", self.filters.get("label", ""))
        color_values = [""] + [name for name in KEEP_COLOR_PALETTE.keys() if name]
        self.color_var = ctk.StringVar(value=normalize_keep_color(self.filters.get("color", "")))
        self.color_menu = ctk.CTkOptionMenu(
            frame,
            values=color_values,
            variable=self.color_var,
            fg_color=COLORS["bg_medium"],
            button_color=COLORS["bg_hover"],
            button_hover_color=COLORS["accent_blue"],
            text_color=COLORS["text_primary"]
        )
        self.color_menu.pack(fill="x", pady=(0, 10))

        self.date_from_entry = self._entry(frame, "From date YYYY-MM-DD", self.filters.get("date_from", ""))
        self.date_to_entry = self._entry(frame, "To date YYYY-MM-DD", self.filters.get("date_to", ""))

        self.has_image_var = ctk.BooleanVar(value=bool(self.filters.get("has_image")))
        self.has_checklist_var = ctk.BooleanVar(value=bool(self.filters.get("has_checklist")))
        self.is_archived_var = ctk.BooleanVar(value=bool(self.filters.get("is_archived")))
        for label, variable in (
            ("Has image", self.has_image_var),
            ("Has checklist", self.has_checklist_var),
            ("Is archived", self.is_archived_var),
        ):
            ctk.CTkCheckBox(
                frame,
                text=label,
                variable=variable,
                font=ctk.CTkFont(size=13),
                text_color=COLORS["text_secondary"],
                fg_color=COLORS["accent_green"],
                hover_color=COLORS["accent_green_hover"]
            ).pack(anchor="w", pady=(0, 8))

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.pack(fill="x", side="bottom", pady=(18, 0))

        ctk.CTkButton(
            actions,
            text="Clear",
            height=38,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._clear
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            actions,
            text="Apply",
            height=38,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._apply
        ).pack(side="left", fill="x", expand=True)

    def _entry(self, parent, placeholder: str, value: str):
        entry = ctk.CTkEntry(
            parent,
            placeholder_text=placeholder,
            font=ctk.CTkFont(size=13),
            height=36,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"]
        )
        entry.pack(fill="x", pady=(0, 10))
        if value:
            entry.insert(0, value)
        return entry

    def _current_filters(self) -> Dict[str, Any]:
        return {
            "mode": self.mode_var.get(),
            "label": self.label_entry.get().strip(),
            "color": self.color_var.get(),
            "date_from": self.date_from_entry.get().strip(),
            "date_to": self.date_to_entry.get().strip(),
            "has_image": self.has_image_var.get(),
            "has_checklist": self.has_checklist_var.get(),
            "is_archived": self.is_archived_var.get(),
        }

    def _clear(self):
        self.on_apply(default_advanced_filters())
        self.destroy()

    def _apply(self):
        self.on_apply(self._current_filters())
        self.destroy()


class ImportConflictDialog(ctk.CTkToplevel):
    """Modal import conflict resolver."""

    def __init__(self, parent, local_note: Note, imported_note: Note):
        super().__init__(parent)
        self.local_note = local_note
        self.imported_note = imported_note
        self.result = "local"

        self.title("Import Conflict")
        self.geometry("760x560")
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        configure_modal_dialog(self, parent)
        self.wait_window()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(18, 10))

        ctk.CTkLabel(
            header,
            text="Import Conflict",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text=self.imported_note.title or "Untitled",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            anchor="w"
        ).pack(anchor="w", pady=(4, 0))

        diff_box = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(size=12, family="Consolas"),
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=8,
            wrap="none"
        )
        diff_box.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        diff_text = note_conflict_diff(self.local_note, self.imported_note) or "Metadata differs; content is identical."
        diff_box.insert("1.0", diff_text)
        diff_box.configure(state="disabled")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 18))

        for label, result, color in (
            ("Keep Local", "local", COLORS["bg_light"]),
            ("Use Imported", "imported", COLORS["accent_blue"]),
            ("Merge", "merge", COLORS["accent_green"]),
        ):
            button = ctk.CTkButton(
                actions,
                text=label,
                font=ctk.CTkFont(size=13, weight="bold"),
                height=38,
                fg_color=color,
                hover_color=COLORS["bg_hover"] if result == "local" else color,
                text_color=COLORS["text_primary"] if result == "local" else COLORS["bg_darkest"],
                command=lambda choice=result: self._finish(choice)
            )
            button.pack(side="left", fill="x", expand=True, padx=(0, 8))

    def _finish(self, result: str):
        self.result = result
        self.destroy()


class TakeoutInstructionsDialog(ctk.CTkToplevel):
    """Dialog showing Google Takeout export instructions"""

    def __init__(self, parent):
        super().__init__(parent)

        self.title("Import via Google Takeout")
        self.geometry("550x500")
        self.configure(fg_color=COLORS["bg_dark"])

        self.transient(parent)
        self.grab_set()

        self._build_ui()
        configure_modal_dialog(self, parent)

    def _build_ui(self):
        # Header
        header = ctk.CTkLabel(
            self,
            text="📦 Import via Google Takeout",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        header.pack(pady=(20, 10))

        subtitle = ctk.CTkLabel(
            self,
            text="The most reliable way to get your Google Keep notes",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        )
        subtitle.pack(pady=(0, 20))

        # Instructions frame
        instructions_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], corner_radius=12)
        instructions_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        steps = [
            ("1", "Go to Google Takeout", "takeout.google.com"),
            ("2", "Click 'Deselect all'", "Then scroll down and select only 'Keep'"),
            ("3", "Click 'Next step'", "Choose 'Export once' and '.zip' format"),
            ("4", "Click 'Create export'", "Wait for Google to prepare your data"),
            ("5", "Download the ZIP", "Check your email for the download link"),
            ("6", "Extract the ZIP", "Find the 'Keep' folder inside"),
            ("7", "Import JSON files", "Use Settings → Import Notes in this app"),
        ]

        for num, title, desc in steps:
            step_frame = ctk.CTkFrame(instructions_frame, fg_color="transparent")
            step_frame.pack(fill="x", padx=16, pady=8)

            num_label = ctk.CTkLabel(
                step_frame,
                text=num,
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=COLORS["accent_green"],
                width=30
            )
            num_label.pack(side="left")

            text_frame = ctk.CTkFrame(step_frame, fg_color="transparent")
            text_frame.pack(side="left", fill="x", expand=True, padx=(8, 0))

            title_label = ctk.CTkLabel(
                text_frame,
                text=title,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COLORS["text_primary"],
                anchor="w"
            )
            title_label.pack(anchor="w")

            desc_label = ctk.CTkLabel(
                text_frame,
                text=desc,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_muted"],
                anchor="w"
            )
            desc_label.pack(anchor="w")

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))

        open_takeout_btn = ctk.CTkButton(
            btn_frame,
            text="Open Google Takeout",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            text_color=COLORS["bg_darkest"],
            command=lambda: webbrowser.open("https://takeout.google.com")
        )
        open_takeout_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        close_btn = ctk.CTkButton(
            btn_frame,
            text="Close",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            border_width=1,
            border_color=COLORS["border"],
            command=self.destroy
        )
        close_btn.pack(side="left", fill="x", expand=True)


class TokenGeneratorDialog(ctk.CTkToplevel):
    """Dialog to generate Google Master Token"""

    def __init__(self, parent, prefill_email: str = ""):
        super().__init__(parent)

        self.title("Get Master Token")
        self.geometry("500x550")
        self.configure(fg_color=COLORS["bg_dark"])

        self.transient(parent)
        self.grab_set()

        self.parent_dialog = parent
        self._build_ui(prefill_email)
        configure_modal_dialog(self, parent, initial_focus=self.email_entry)

    def _build_ui(self, prefill_email: str):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)

        title = ctk.CTkLabel(
            header,
            text="🔑 Master Token Generator",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        title.pack(anchor="w")

        # Instructions
        instructions = ctk.CTkLabel(
            self,
            text="Google requires a Master Token for Keep sync.\n"
                 "This will authenticate with Google and generate your token.",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            justify="left"
        )
        instructions.pack(anchor="w", padx=20, pady=(0, 16))

        # Form frame
        form_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], corner_radius=12)
        form_frame.pack(fill="x", padx=20, pady=(0, 16))

        # Email
        ctk.CTkLabel(
            form_frame,
            text="Google Email",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", padx=16, pady=(16, 4))

        self.email_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="your.email@gmail.com",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"]
        )
        self.email_entry.pack(fill="x", padx=16)
        if prefill_email:
            self.email_entry.insert(0, prefill_email)

        # Password
        ctk.CTkLabel(
            form_frame,
            text="Password (or App Password if 2FA enabled)",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self.password_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="Your password",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"],
            show="•"
        )
        self.password_entry.pack(fill="x", padx=16)

        # 2FA note
        note = ctk.CTkLabel(
            form_frame,
            text="⚠️ If you have 2FA enabled, create an App Password at:\n"
                 "   myaccount.google.com/apppasswords",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["accent_yellow"],
            justify="left"
        )
        note.pack(anchor="w", padx=16, pady=(8, 16))

        # Generate button
        self.generate_btn = ctk.CTkButton(
            self,
            text="Generate Master Token",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._generate_token
        )
        self.generate_btn.pack(fill="x", padx=20, pady=(0, 16))

        # Result frame (initially hidden)
        self.result_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], corner_radius=12)

        ctk.CTkLabel(
            self.result_frame,
            text="✓ Master Token Generated!",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["accent_green"]
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.token_display = ctk.CTkTextbox(
            self.result_frame,
            height=80,
            font=ctk.CTkFont(size=11, family="Consolas"),
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"]
        )
        self.token_display.pack(fill="x", padx=16, pady=(0, 8))

        btn_frame = ctk.CTkFrame(self.result_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 16))

        self.copy_btn = ctk.CTkButton(
            btn_frame,
            text="Copy & Use Token",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._copy_and_use
        )
        self.copy_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        close_btn = ctk.CTkButton(
            btn_frame,
            text="Close",
            font=ctk.CTkFont(size=13),
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            border_width=1,
            border_color=COLORS["border"],
            command=self.destroy
        )
        close_btn.pack(side="left", fill="x", expand=True)

        # Status label
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"]
        )
        self.status_label.pack(pady=(8, 20))

        self.generated_token = None

    def _generate_token(self):
        """Generate the master token"""
        email = self.email_entry.get().strip()
        password = self.password_entry.get()

        if not email or not password:
            messagebox.showerror("Error", "Please enter both email and password")
            return

        self.generate_btn.configure(state="disabled", text="Generating...")
        self.status_label.configure(text="Checking gpsoauth...", text_color=COLORS["text_muted"])
        self.update()

        # Run in thread to not block UI
        def generate():
            try:
                try:
                    import gpsoauth
                except ImportError:
                    self.after(0, lambda: self._show_error(
                        "gpsoauth is not installed. Run: python -m pip install -r requirements.txt"
                    ))
                    return

                self.after(0, lambda: self.status_label.configure(
                    text="Authenticating with Google...", text_color=COLORS["text_muted"]))

                # Generate token
                android_id = "0123456789abcdef"
                master_response = gpsoauth.perform_master_login(email, password, android_id)

                if "Token" not in master_response:
                    error = master_response.get("Error", "Unknown error")
                    self.after(0, lambda: self._show_error(error))
                    return

                token = master_response["Token"]
                self.after(0, lambda: self._show_success(token))

            except Exception as e:
                self.after(0, lambda: self._show_error(str(e)))

        threading.Thread(target=generate, daemon=True).start()

    def _show_error(self, error: str):
        """Show error message"""
        self.generate_btn.configure(state="normal", text="Generate Master Token")

        if "BadAuthentication" in error:
            self.status_label.configure(
                text="Authentication failed. Check password or use App Password for 2FA.",
                text_color=COLORS["accent_red"]
            )
            messagebox.showerror("Authentication Failed",
                "Google rejected the authentication.\n\n"
                "If you have 2FA enabled:\n"
                "1. Go to myaccount.google.com/apppasswords\n"
                "2. Create an App Password\n"
                "3. Use that instead of your regular password\n\n"
                "Also check your email for security alerts from Google.")
        else:
            self.status_label.configure(text=f"Error: {error}", text_color=COLORS["accent_red"])

    def _show_success(self, token: str):
        """Show success and token"""
        self.generated_token = token
        self.generate_btn.configure(state="normal", text="Generate Master Token")
        self.status_label.configure(text="", text_color=COLORS["text_muted"])

        self.result_frame.pack(fill="x", padx=20, pady=(0, 16))
        self.token_display.delete("1.0", "end")
        self.token_display.insert("1.0", token)

    def _copy_and_use(self):
        """Copy token to clipboard and fill in parent dialog"""
        if self.generated_token:
            self.clipboard_clear()
            self.clipboard_append(self.generated_token)

            # Fill in the parent dialog's token entry
            if hasattr(self.parent_dialog, 'token_entry'):
                self.parent_dialog.token_entry.delete(0, "end")
                self.parent_dialog.token_entry.insert(0, self.generated_token)

            messagebox.showinfo("Token Copied",
                "Token copied to clipboard and filled in.\n"
                "Click 'Connect' to authenticate.")
            self.destroy()


class ImportProgressDialog(ctk.CTkToplevel):
    """Cancellable modal progress for archive and bulk imports."""

    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.cancelled = False
        self.title(title)
        self.geometry("420x180")
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()

        ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", padx=20, pady=(20, 8))

        self.status_label = ctk.CTkLabel(
            self,
            text="Preparing import...",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
        )
        self.status_label.pack(anchor="w", padx=20, pady=(0, 12))

        self.progress_bar = ctk.CTkProgressBar(self, mode="determinate")
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 16))

        self.cancel_btn = ctk.CTkButton(
            self,
            text="Cancel",
            font=ctk.CTkFont(size=12),
            height=34,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self.cancel,
        )
        self.cancel_btn.pack(anchor="e", padx=20)
        configure_modal_dialog(self, parent, initial_focus=self.cancel_btn, on_close=self.cancel, escape_handler=self.cancel)

    def cancel(self):
        self.cancelled = True
        self.cancel_btn.configure(state="disabled", text="Cancelling...")
        self.status_label.configure(text="Cancelling after the current file...", text_color=COLORS["accent_yellow"])

    def is_cancelled(self) -> bool:
        return self.cancelled

    def set_progress(self, message: str, current: int, total: int):
        total = max(total, 1)
        self.status_label.configure(text=f"{message} ({current}/{total})", text_color=COLORS["text_secondary"])
        self.progress_bar.set(min(max(current / total, 0), 1))


class DiagnosticsDialog(ctk.CTkToplevel):
    """Read-only diagnostics panel."""

    def __init__(self, parent, diagnostics: DiagnosticsManager, db_path: Path, attachments_path: Path):
        super().__init__(parent)
        self.diagnostics = diagnostics
        self.db_path = db_path
        self.attachments_path = attachments_path
        self.title("Diagnostics")
        self.geometry("760x560")
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            header,
            text="Diagnostics",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text_primary"],
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Open Log",
            font=ctk.CTkFont(size=12),
            width=100,
            height=32,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._open_log,
        ).pack(side="right")

        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=COLORS["bg_darkest"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
        )
        self.textbox.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._refresh()
        configure_modal_dialog(self, parent, initial_focus=self.textbox)

    def _refresh(self):
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", self.diagnostics.report(self.db_path, self.attachments_path))
        self.textbox.configure(state="disabled")

    def _open_log(self):
        if self.diagnostics.log_path.exists():
            webbrowser.open(self.diagnostics.log_path.resolve().as_uri())
