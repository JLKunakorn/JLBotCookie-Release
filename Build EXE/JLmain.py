"""JLmain CustomTkinter GUI."""
import datetime
import os
import queue
import sys
import threading
import time
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

import bot
import license_core


APP_NAME = "JLmain"
APP_DISPLAY_VERSION = "V1.1.1 Premium"
license_core.CLIENT_VERSION = APP_DISPLAY_VERSION
RELEASE_MODE = bool(getattr(sys, "frozen", False))

BG = "#2B1D14"
CARD = "#3A2A1E"
CARD_DARK = "#261910"
TEXT = "#F5E6D0"
MUTED = "#C9B79B"
GOLD = "#FFD23F"
CARAMEL = "#C8783C"
MINT = "#7ED957"
BERRY = "#FF6B6B"
LINE = "#5A3B25"
ENTRY = "#24170F"
LOG_TIME = "#8F7C66"
LOG_OK = "#7ED957"
LOG_WARN = "#FF6B6B"
LOG_COIN = "#FFD23F"
LOG_INFO = "#6EC6FF"
LOG_STATE = "#C8783C"


ctk.set_appearance_mode("dark")
if hasattr(ctk, "deactivate_automatic_dpi_scaling"):
    ctk.deactivate_automatic_dpi_scaling()
elif hasattr(ctk, "deactivate_automatic_dpi_awareness"):
    ctk.deactivate_automatic_dpi_awareness()


class JLMainApp:
    def __init__(self, root):
        self.root = root
        self.log_queue = queue.Queue()
        self.bot_thread = None
        self.running = False
        self._max_loops = 0
        self.advanced_open = False
        self.inst_serials = {}
        self.license_enabled = license_core.is_enabled()
        self.license_key_var = None
        self.license_status_var = None
        self.license_countdown_var = None
        self.license_exp = None
        self.license_expired_notified = False
        self.license_popup = None
        self._geometry_busy_until = 0.0

        bot.LOG_CALLBACK = self._enqueue_bot_log
        bot.COIN_CALLBACK = lambda c, t: self.root.after(0, self._update_coins, c, t)
        bot.CAPTCHA_CALLBACK = lambda cnt: self.root.after(0, self._update_captcha, cnt)

        self._build_ui()
        self._fit_window()
        self.root.bind("<Configure>", self._on_window_configure, add="+")
        self._poll_log()

    def _fit_window(self):
        try:
            self.root.update_idletasks()
            w = 760
            screen_h = self.root.winfo_screenheight()
            h = min(860, screen_h - 80)
            x = max(0, (self.root.winfo_screenwidth() - w) // 2)
            y = max(0, (screen_h - h) // 2 - 20)
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.root.resizable(True, True)
        except Exception:
            return None

    def _on_window_configure(self, event):
        if event.widget is self.root:
            self._geometry_busy_until = time.monotonic() + 0.18

    def _window_is_moving(self):
        return time.monotonic() < self._geometry_busy_until

    def _card(self, parent, title=None):
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=18, border_width=1, border_color=LINE)
        card.pack(fill="x", padx=18, pady=(0, 14))
        if title:
            ctk.CTkLabel(card, text=title, text_color=GOLD, font=("Segoe UI", 16, "bold")).pack(
                anchor="w", padx=18, pady=(16, 8)
            )
        return card

    def _img(self, rel, size):
        try:
            path = bot.resource_path(rel)
            if os.path.exists(path):
                img = Image.open(path).convert("RGBA")
                img = img.resize(size, Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(img)
        except Exception:
            pass
        return None

    def _apply_window_icon(self):
        try:
            icon_path = bot.resource_path(os.path.join("assets", "app.ico"))
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

    def _build_ui(self):
        self.root.title(f"JL Bot Cookie - {APP_DISPLAY_VERSION}")
        self.root.geometry("760x820")
        self.root.minsize(620, 680)
        self.root.configure(fg_color=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._apply_window_icon()

        self.body = ctk.CTkScrollableFrame(
            self.root,
            fg_color=BG,
            bg_color=BG,
            scrollbar_button_color=CARAMEL,
            scrollbar_button_hover_color=GOLD
        )
        self.body.pack(fill="both", expand=True)

        banner = ctk.CTkFrame(self.body, fg_color=CARAMEL, corner_radius=24)
        banner.pack(fill="x", padx=18, pady=(18, 16))
        inner = ctk.CTkFrame(banner, fg_color=CARAMEL)
        inner.pack(padx=18, pady=16)
        self._face_img = self._img(os.path.join("templates", "ui", "jlbot_face.png"), (70, 70))
        if self._face_img:
            tk.Label(
                inner,
                image=self._face_img,
                text="",
                bg=CARAMEL,
                bd=0,
                highlightthickness=0,
            ).pack(side="left", padx=(0, 14))
        title_box = ctk.CTkFrame(inner, fg_color=CARAMEL)
        title_box.pack(side="left")
        ctk.CTkLabel(
            title_box,
            text="JL Bot Cookie",
            text_color="#2B1D14",
            font=("Segoe UI", 25, "bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box,
            text=APP_DISPLAY_VERSION,
            text_color="#FFE7B8",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")

        self._build_license_card()
        self.tabs = ctk.CTkTabview(
            self.body,
            fg_color=BG,
            segmented_button_fg_color=CARD,
            segmented_button_selected_color=CARAMEL,
            segmented_button_selected_hover_color=GOLD,
            segmented_button_unselected_color=CARD_DARK,
            segmented_button_unselected_hover_color=LINE,
            text_color=TEXT,
            corner_radius=14,
        )
        self.tabs.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.control_parent = self.tabs.add("Auto farm")
        self.claim_parent = self.tabs.add("Claim item")
        self.device_parent = self.tabs.add("Setting")
        for tab in (self.control_parent, self.claim_parent, self.device_parent):
            tab.configure(fg_color=BG)

        self.control_layout = ctk.CTkFrame(self.control_parent, fg_color=BG)
        self.control_layout.pack(fill="both", expand=True)
        self.control_main_parent = ctk.CTkFrame(self.control_layout, fg_color=BG)
        self.control_main_parent.pack(side="left", fill="both", expand=True)
        self.control_options_parent = ctk.CTkFrame(self.control_layout, fg_color=BG)
        self.control_options_parent.pack(side="left", fill="both", expand=True)

        self.claim_layout = ctk.CTkFrame(self.claim_parent, fg_color=BG)
        self.claim_layout.pack(fill="both", expand=True)

        self._build_control_card()
        self._build_options_card()
        self._build_auto_farm_assist_card()
        self._build_claim_card(self.claim_layout)
        self._build_device_card()
        self.tabs.set("Auto farm")
        self._init_emu_default()
        if self.license_enabled:
            self.root.after(350, self._check_license_on_start)
            self.root.after(1000, self._tick_license_countdown)

    def _build_license_card(self):
        if not self.license_enabled:
            return
        card = self._card(self.body, "สิทธิ์ใช้งาน")
        row = ctk.CTkFrame(card, fg_color=CARD)
        row.pack(fill="x", padx=18, pady=(0, 12))
        row.grid_columnconfigure(0, weight=1)

        self.license_key_var = tk.StringVar(value="")
        ctk.CTkEntry(
            row,
            textvariable=self.license_key_var,
            placeholder_text="ใส่ license key ใหม่",
            fg_color=ENTRY,
            border_color=LINE,
            text_color=TEXT,
            height=38,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.license_btn = ctk.CTkButton(
            row,
            text="เปิดใช้งาน",
            command=self._activate_license,
            width=108,
            height=38,
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            corner_radius=12,
        )
        self.license_btn.grid(row=0, column=1)

        status = "กำลังตรวจสิทธิ์..." if license_core.get_saved_key() else "ยังไม่ได้เปิดใช้งาน"
        self.license_status_var = tk.StringVar(value=status)
        self.license_status_lbl = ctk.CTkLabel(
            card,
            textvariable=self.license_status_var,
            text_color=MUTED,
            font=("Segoe UI", 12, "bold"),
        )
        self.license_status_lbl.pack(anchor="w", padx=18, pady=(0, 14))
        self.license_countdown_var = tk.StringVar(value="")
        self.license_countdown_lbl = ctk.CTkLabel(
            card,
            textvariable=self.license_countdown_var,
            text_color=GOLD,
            font=("Segoe UI", 18, "bold"),
        )
        self.license_countdown_lbl.pack(anchor="w", padx=18, pady=(0, 14))

    def _license_text(self, info):
        if isinstance(info, dict):
            exp = info.get("exp")
            if exp:
                try:
                    when = datetime.datetime.fromtimestamp(int(exp)).strftime("%Y-%m-%d %H:%M")
                    return f"ใช้งานได้ถึง {when}"
                except Exception:
                    return "license ใช้งานได้"
            return "license ใช้งานได้"
        return str(info)

    def _set_license_info(self, info):
        if isinstance(info, dict):
            try:
                bot.set_license_context(info)
            except Exception:
                pass
            try:
                self.license_exp = int(info.get("exp") or 0) or None
                self.license_expired_notified = False
            except Exception:
                self.license_exp = None
        else:
            try:
                bot.clear_license_context()
            except Exception:
                pass
            self.license_exp = None
        self._tick_license_countdown(schedule=False)

    def _set_license_status(self, text, color=None):
        if not self.license_status_var:
            return
        self.license_status_var.set(text)
        try:
            self.license_status_lbl.configure(text_color=color or MUTED)
        except Exception:
            pass

    def _format_remaining(self, seconds):
        seconds = max(0, int(seconds))
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        if days:
            return f"{days} วัน {hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _tick_license_countdown(self, schedule=True):
        if self.license_countdown_var:
            if self.license_exp:
                remaining = self.license_exp - int(time.time())
                if remaining > 0:
                    self.license_countdown_var.set(f"เหลือเวลา: {self._format_remaining(remaining)}")
                else:
                    self.license_countdown_var.set("หมดอายุแล้ว")
                    self._set_license_status("license หมดอายุ", BERRY)
                    if not self.license_expired_notified:
                        self.license_expired_notified = True
                        # self._log("[license] หมดเวลาใช้งานแล้ว\n")
                        if self.running:
                            bot.STOP_FLAG.set()
                            # self._log("[license] หยุดบอทเพราะ license หมดอายุ\n")
            else:
                self.license_countdown_var.set("")
        if schedule:
            self.root.after(1000, self._tick_license_countdown)

    def _check_license_on_start(self):
        ok, info = license_core.check_license(force_online=True)
        if ok:
            self._set_license_info(info)
            self._set_license_status(self._license_text(info), MINT)
            self._check_app_update(info)
            return
        self._set_license_info(None)
        self._set_license_status(str(info), BERRY)
        self._show_license_popup()

    def _check_app_update(self, info):
        if not info:
            return
        srv_ver = info.get("app_version")
        if srv_ver and srv_ver != APP_DISPLAY_VERSION:
            from tkinter import messagebox
            dl_url = info.get("download_url") or "https://jlcookie-license.aura-secretary.workers.dev"
            if messagebox.askyesno(
                "ตรวจพบเวอร์ชันใหม่",
                f"มีอัปเดตใหม่เวอร์ชัน: {srv_ver}\nเวอร์ชันของคุณในปัจจุบันคือ: {APP_DISPLAY_VERSION}\n\nต้องการดาวน์โหลดและติดตั้งเวอร์ชันใหม่โดยอัตโนมัติเลยหรือไม่?"
            ):
                self._start_auto_update(dl_url, srv_ver)

    def _start_auto_update(self, dl_url, srv_ver):
        popup = ctk.CTkToplevel(self.root)
        popup.title("ดาวน์โหลดอัปเดตใหม่")
        popup.geometry("380x150")
        popup.resizable(False, False)
        popup.configure(fg_color=BG)
        popup.transient(self.root)
        popup.grab_set()
        popup.protocol("WM_DELETE_WINDOW", lambda: None)

        # Center relative to main window
        x = self.root.winfo_x() + max(0, (self.root.winfo_width() - 380) // 2)
        y = self.root.winfo_y() + 150
        popup.geometry(f"380x150+{x}+{y}")

        frame = ctk.CTkFrame(popup, fg_color=CARD, corner_radius=18, border_width=1, border_color=LINE)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(frame, text="กำลังดาวน์โหลด JL Bot Cookie", text_color=GOLD, font=("Segoe UI", 15, "bold")).pack(
            anchor="w", padx=18, pady=(14, 4)
        )

        progress_var = tk.DoubleVar(value=0.0)
        progress_bar = ctk.CTkProgressBar(frame, variable=progress_var, progress_color=MINT, fg_color=LINE, height=14)
        progress_bar.pack(fill="x", padx=18, pady=8)

        status_label = ctk.CTkLabel(frame, text="กำลังเตรียมดาวน์โหลด... 0%", text_color=MUTED, font=("Segoe UI", 12))
        status_label.pack(anchor="w", padx=18, pady=(0, 10))

        def worker():
            import urllib.request
            import subprocess
            import sys
            try:
                current_exe = sys.executable
                is_exe = current_exe.endswith(".exe") and "python" not in os.path.basename(current_exe).lower()
                
                # Determine absolute paths
                srv_ver_clean = srv_ver.replace(" ", "_") if srv_ver else "update"
                final_exe_name = f"JLmain_{srv_ver_clean}.exe"

                if is_exe:
                    exe_dir = os.path.dirname(os.path.abspath(current_exe))
                    target_exe_path = os.path.abspath(current_exe)
                else:
                    exe_dir = os.path.dirname(os.path.abspath(__file__))
                    target_exe_path = os.path.join(exe_dir, final_exe_name)
                
                final_exe_path = os.path.join(exe_dir, final_exe_name)
                temp_exe_path = os.path.join(exe_dir, "update_temp.exe")
                updater_bat_path = os.path.join(exe_dir, "updater.bat")

                req = urllib.request.Request(
                    dl_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )

                with urllib.request.urlopen(req, timeout=60) as response:
                    content_length = response.getheader('Content-Length')
                    total_size = int(content_length) if content_length else 0
                    downloaded = 0
                    block_size = 65536

                    with open(temp_exe_path, "wb") as f:
                        while True:
                            buffer = response.read(block_size)
                            if not buffer:
                                break
                            f.write(buffer)
                            downloaded += len(buffer)

                            if total_size > 0:
                                percent = min(1.0, downloaded / total_size)
                                self.root.after(0, lambda p=percent: progress_var.set(p))
                                percent_str = f"กำลังดาวน์โหลด... {int(percent * 100)}%"
                                self.root.after(0, lambda s=percent_str: status_label.configure(text=s))

                MIN_EXE_SIZE = 1_000_000
                with open(temp_exe_path, "rb") as f:
                    header = f.read(2)
                file_size = os.path.getsize(temp_exe_path)
                if header != b"MZ" or file_size < MIN_EXE_SIZE:
                    try:
                        os.remove(temp_exe_path)
                    except Exception:
                        pass
                    self.root.after(0, lambda: status_label.configure(
                        text="ไฟล์อัปเดตไม่สมบูรณ์ ยกเลิกการติดตั้ง กรุณาลองใหม่ภายหลัง", text_color=BERRY))
                    self.root.after(0, lambda: popup.protocol("WM_DELETE_WINDOW", popup.destroy))
                    return

                self.root.after(0, lambda: status_label.configure(text="เสร็จสมบูรณ์! กำลังติดตั้งและเปิดโปรแกรมใหม่..."))
                time.sleep(1.0)

                backup_exe_path = os.path.join(
                    exe_dir,
                    f"{os.path.splitext(os.path.basename(target_exe_path))[0]}_old_backup.exe",
                )
                bat_content = f"""@echo off
chcp 65001 > nul
cd /d "{exe_dir}"
:loop
if not exist "{target_exe_path}" goto swap
move /y "{target_exe_path}" "{backup_exe_path}"
if exist "{target_exe_path}" (
    timeout /t 1 /nobreak > nul
    goto loop
)
:swap
if exist "{final_exe_name}" del /f /q "{final_exe_name}"
rename "{temp_exe_path}" "{final_exe_name}"
timeout /t 2 /nobreak > nul
start "" "{final_exe_name}"
del "%~f0"
"""
                with open(updater_bat_path, "w", encoding="utf-8") as bat_file:
                    bat_file.write(bat_content)

                subprocess.Popen(
                    ["cmd.exe", "/c", updater_bat_path],
                    cwd=exe_dir,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                )

                self.root.after(0, lambda: self.root.quit())
                os._exit(0)

            except Exception as e:
                err_msg = f"ดาวน์โหลดไม่สำเร็จ: {str(e)}"
                self.root.after(0, lambda s=err_msg: status_label.configure(text=s, text_color=BERRY))
                self.root.after(0, lambda: popup.protocol("WM_DELETE_WINDOW", popup.destroy))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _show_license_popup(self):
        if self.license_popup and self.license_popup.winfo_exists():
            self.license_popup.focus()
            return

        popup = ctk.CTkToplevel(self.root)
        self.license_popup = popup
        popup.title("เปิดใช้งาน License")
        popup.geometry("420x245")
        popup.resizable(False, False)
        popup.configure(fg_color=BG)
        popup.transient(self.root)
        popup.grab_set()
        popup.protocol("WM_DELETE_WINDOW", lambda: None if license_core.is_required() else popup.destroy())
        self._apply_window_icon()

        frame = ctk.CTkFrame(popup, fg_color=CARD, corner_radius=18, border_width=1, border_color=LINE)
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(frame, text="สิทธิ์ใช้งาน", text_color=GOLD, font=("Segoe UI", 20, "bold")).pack(
            anchor="w", padx=18, pady=(18, 8)
        )
        ctk.CTkLabel(
            frame,
            text="ใส่ key ที่ได้รับจากร้าน",
            text_color=MUTED,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=18, pady=(0, 10))

        popup_key = tk.StringVar(value="")
        entry = ctk.CTkEntry(
            frame,
            textvariable=popup_key,
            placeholder_text="JL-XXXX-XXXX-XXXX-XXXX",
            fg_color=ENTRY,
            border_color=LINE,
            text_color=TEXT,
            height=42,
        )
        entry.pack(fill="x", padx=18, pady=(0, 10))

        popup_status = tk.StringVar(value="")
        ctk.CTkLabel(frame, textvariable=popup_status, text_color=BERRY, font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=18, pady=(0, 10)
        )

        def activate_from_popup():
            key = popup_key.get().strip()
            if not key:
                popup_status.set("กรุณาใส่ license key")
                return
            btn.configure(state="disabled", text="กำลังเช็ค...")
            popup_status.set("กำลังติดต่อ license server...")

            def worker():
                ok, info = license_core.activate(key)

                def done():
                    btn.configure(state="normal", text="เปิดใช้งาน")
                    if ok:
                        msg = self._license_text(info)
                        self._set_license_info(info)
                        self._set_license_status(msg, MINT)
                        # self._log(f"[license] เปิดใช้งานสำเร็จ: {msg}\n")
                        popup.destroy()
                        self._check_app_update(info)
                    else:
                        msg = str(info)
                        popup_status.set(msg)
                        self._set_license_info(None)
                        self._set_license_status(msg, BERRY)
                        # self._log(f"[license] เปิดใช้งานไม่สำเร็จ: {msg}\n")

                self.root.after(0, done)

            threading.Thread(target=worker, daemon=True).start()

        btn = ctk.CTkButton(
            frame,
            text="เปิดใช้งาน",
            command=activate_from_popup,
            height=42,
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            font=("Segoe UI", 15, "bold"),
            corner_radius=12,
        )
        btn.pack(fill="x", padx=18, pady=(0, 18))

        self.root.update_idletasks()
        x = self.root.winfo_x() + max(0, (self.root.winfo_width() - 420) // 2)
        y = self.root.winfo_y() + 90
        popup.geometry(f"420x245+{x}+{y}")
        entry.focus_set()

    def _activate_license(self):
        if not self.license_key_var:
            return
        key = self.license_key_var.get().strip()
        if not key:
            self._set_license_status("กรุณาใส่ license key", BERRY)
            return
        self.license_btn.configure(state="disabled", text="กำลังเช็ค...")
        self._set_license_status("กำลังติดต่อ license server...", GOLD)

        def worker():
            ok, info = license_core.activate(key)

            def done():
                self.license_btn.configure(state="normal", text="เปิดใช้งาน")
                if ok:
                    msg = self._license_text(info)
                    self._set_license_info(info)
                    self._set_license_status(msg, MINT)
                    self.license_key_var.set("")
                    # self._log(f"[license] เปิดใช้งานสำเร็จ: {msg}\n")
                    self._check_app_update(info)
                else:
                    msg = str(info)
                    self._set_license_info(None)
                    self._set_license_status(msg, BERRY)
                    # self._log(f"[license] เปิดใช้งานไม่สำเร็จ: {msg}\n")

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _build_device_card(self):
        card = self._card(self.device_parent, "Device Setting")
        grid = ctk.CTkFrame(card, fg_color=CARD)
        grid.pack(fill="x", padx=18, pady=(0, 16))
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(grid, text="อีมูเลเตอร์", text_color=TEXT, font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=8
        )
        self.emu_var = tk.StringVar()
        self.emu_combo = ctk.CTkOptionMenu(
            grid,
            variable=self.emu_var,
            values=list(bot.EMU_PROFILES.keys()) or ["Emulator"],
            command=self._on_emu_change,
            fg_color=ENTRY,
            button_color=CARAMEL,
            button_hover_color=GOLD,
            dropdown_fg_color=CARD_DARK,
            dropdown_hover_color=CARAMEL,
            text_color=TEXT,
            dropdown_text_color=TEXT,
            width=132,
        )
        self.emu_combo.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=8)

        ctk.CTkLabel(grid, text="Instance", text_color=TEXT, font=("Segoe UI", 13, "bold")).grid(
            row=0, column=2, sticky="w", padx=(0, 8), pady=8
        )
        self.inst_var = tk.StringVar()
        self.inst_combo = ctk.CTkOptionMenu(
            grid,
            variable=self.inst_var,
            values=["ยังไม่ได้ค้นหา"],
            command=self._on_inst_change,
            fg_color=ENTRY,
            button_color=CARAMEL,
            button_hover_color=GOLD,
            dropdown_fg_color=CARD_DARK,
            dropdown_hover_color=CARAMEL,
            text_color=TEXT,
            dropdown_text_color=TEXT,
            width=180,
        )
        self.inst_combo.grid(row=0, column=3, sticky="ew", padx=(0, 8), pady=8)

        self.refresh_btn = ctk.CTkButton(
            grid,
            text="⟳",
            width=42,
            height=36,
            command=self._refresh_instances,
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            font=("Segoe UI", 16, "bold"),
            corner_radius=12,
        )
        self.refresh_btn.grid(row=0, column=4, sticky="e", pady=8)

        self.advanced_btn = ctk.CTkButton(
            card,
            text="▸ ตั้งค่าขั้นสูง",
            command=self._toggle_advanced,
            fg_color=CARD,
            hover_color=CARD_DARK,
            text_color=MUTED,
            anchor="w",
            font=("Segoe UI", 13, "bold"),
            corner_radius=10,
        )
        self.advanced_btn.pack(fill="x", padx=14, pady=(0, 14))

        self.advanced_frame = ctk.CTkFrame(card, fg_color=CARD_DARK, corner_radius=14)
        self._build_advanced_fields(self.advanced_frame)

    def _build_advanced_fields(self, parent):
        parent.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(parent, text="ADB path", text_color=TEXT, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", padx=14, pady=(14, 8)
        )
        self.adb_var = tk.StringVar(value=bot.ADB_PATH)
        ctk.CTkEntry(
            parent,
            textvariable=self.adb_var,
            fg_color=ENTRY,
            border_color=LINE,
            text_color=TEXT,
            height=36,
        ).grid(row=0, column=1, sticky="ew", padx=8, pady=(14, 8))
        ctk.CTkButton(
            parent,
            text="หาอัตโนมัติ",
            command=self.auto_find_adb,
            width=96,
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            corner_radius=10,
        ).grid(row=0, column=2, padx=14, pady=(14, 8))

        ctk.CTkLabel(parent, text="Device", text_color=TEXT, font=("Segoe UI", 12, "bold")).grid(
            row=1, column=0, sticky="w", padx=14, pady=8
        )
        self.dev_var = tk.StringVar(value=bot.ADB_DEVICE or "")
        ctk.CTkEntry(
            parent,
            textvariable=self.dev_var,
            fg_color=ENTRY,
            border_color=LINE,
            text_color=TEXT,
            height=36,
        ).grid(row=1, column=1, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(
            parent,
            text="ทดสอบ",
            command=self.test_connection,
            width=96,
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            corner_radius=10,
        ).grid(row=1, column=2, padx=14, pady=8)

    def _build_options_card(self):
        card = self._card(self.control_options_parent, "โหมดการเล่น")
        self.opt_vars = {}
        main = ctk.CTkFrame(card, fg_color=CARD)
        main.pack(fill="x", padx=18, pady=(0, 10))
        main.grid_columnconfigure((0, 1), weight=1)

        options = [
            ("use_jump", "Jump Assist"),
            ("use_relay", "Relay Assist"),
            ("use_faststart", "Fast Start"),
        ]
        for i, (key, text) in enumerate(options):
            var = tk.BooleanVar(value=bool(bot.SETTINGS.get(key, True)))
            self.opt_vars[key] = var
            switch = ctk.CTkSwitch(
                main,
                text=text,
                variable=var,
                onvalue=True,
                offvalue=False,
                progress_color=MINT,
                button_color=TEXT,
                button_hover_color=GOLD,
                fg_color=LINE,
                text_color=TEXT,
                font=("Segoe UI", 13, "bold"),
            )
            switch.grid(row=i // 2, column=i % 2, sticky="w", padx=4, pady=8)

        boosts = ctk.CTkFrame(card, fg_color=CARD_DARK, corner_radius=14)
        boosts.pack(fill="x", padx=18, pady=(4, 16))
        ctk.CTkLabel(boosts, text="Boost Slots", text_color=GOLD, font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        boost_row = ctk.CTkFrame(boosts, fg_color=CARD_DARK)
        boost_row.pack(fill="x", padx=14, pady=(0, 10))
        boost_row.grid_columnconfigure((0, 1), weight=1)
        for i, (key, label) in enumerate([("boost_potion", "Potion"), ("boost_stopwatch", "Stopwatch"), ("boost_star", "Star x2")]):
            var = tk.BooleanVar(value=bool(bot.SETTINGS.get(key, True)))
            self.opt_vars[key] = var
            ctk.CTkSwitch(
                boost_row,
                text=label,
                variable=var,
                onvalue=True,
                offvalue=False,
                progress_color=MINT,
                fg_color=LINE,
                text_color=TEXT,
                font=("Segoe UI", 12, "bold"),
            ).grid(row=i // 2, column=i % 2, sticky="w", padx=4, pady=6)

        ctk.CTkLabel(boosts, text="Target Boost", text_color=GOLD, font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=14, pady=(0, 4)
        )
        multi = ctk.CTkFrame(boosts, fg_color=CARD_DARK)
        multi.pack(fill="x", padx=14, pady=(0, 14))
        multi.grid_columnconfigure((0, 1), weight=1)
        short = {
            "double_coins": "Double Coins",
            "score_bonus": "+15% score",
            "hp_drain": "-15% HP drain",
            "revive_80hp": "Revive 80HP",
            "crush_chance": "70% Crush",
            "base_speed": "+17% speed",
            "gold_magic": "Gold Magic",
            "less_collision": "-30% ชน",
            "hp_potion": "+20% HP potion",
            "magnetic": "Magnetic",
            "pit_lifts": "2 Pit Lifts",
        }
        for i, boost in enumerate(getattr(bot, "MULTI_BOOSTS", [])):
            key = "multi_" + boost["key"]
            var = tk.BooleanVar(value=bool(bot.SETTINGS.get(key, boost["default"])))
            self.opt_vars[key] = var
            ctk.CTkSwitch(
                multi,
                text=short.get(boost["key"], boost["name"]),
                variable=var,
                onvalue=True,
                offvalue=False,
                progress_color=MINT,
                fg_color=LINE,
                text_color=TEXT,
                font=("Segoe UI", 12),
            ).grid(row=i // 2, column=i % 2, sticky="w", padx=4, pady=5)

    def _build_auto_farm_assist_card(self):
        card = self._card(self.control_options_parent, "ระบบฟาร์มเสริม")
        main = ctk.CTkFrame(card, fg_color=CARD)
        main.pack(fill="x", padx=18, pady=(0, 16))
        main.grid_columnconfigure(1, weight=1)
        
        # Mail Lives Switch
        mail_var = tk.BooleanVar(value=bool(bot.SETTINGS.get('use_mail_lives', False)))
        self.opt_vars['use_mail_lives'] = mail_var
        
        mail_switch = ctk.CTkSwitch(
            main,
            text="รับหัวใจในเมล (Mail Lives)",
            variable=mail_var,
            onvalue=True,
            offvalue=False,
            progress_color=MINT,
            fg_color=LINE,
            text_color=TEXT,
            font=("Segoe UI", 12, "bold"),
            command=self._on_mail_toggle
        )
        mail_switch.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 10))

        # Mail min count input frame (shown only if mail_var is True)
        self.mail_limit_frame = ctk.CTkFrame(main, fg_color=CARD)
        self.mail_limit_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))
        
        ctk.CTkLabel(self.mail_limit_frame, text="รับเมื่อมีจดหมายขั้นต่ำ:", text_color=TEXT, font=("Segoe UI", 12)).pack(side="left", padx=(0, 8))
        self.mail_count_var = tk.StringVar(value=str(bot.MAIL_MIN_COUNT or "5"))
        self.mail_count_entry = ctk.CTkEntry(
            self.mail_limit_frame,
            textvariable=self.mail_count_var,
            fg_color=ENTRY,
            border_color=LINE,
            text_color=TEXT,
            width=50,
            height=28,
            justify="center"
        )
        self.mail_count_entry.pack(side="left")
        ctk.CTkLabel(self.mail_limit_frame, text="ฉบับ", text_color=MUTED, font=("Segoe UI", 12)).pack(side="left", padx=5)

        self._on_mail_toggle()

    def _on_mail_toggle(self):
        if self.opt_vars['use_mail_lives'].get():
            self.mail_limit_frame.grid()
        else:
            self.mail_limit_frame.grid_remove()

    def _build_claim_card(self, parent):
        # 1. Gift Draw Card
        gift_card = self._card(parent, "ระบบสุ่มกล่องของขวัญ (Gift Draw)")
        gift_main = ctk.CTkFrame(gift_card, fg_color=CARD)
        gift_main.pack(fill="x", padx=18, pady=(0, 16))
        
        self.gift_run_var = tk.StringVar(value="▶ เริ่มสุ่มกล่องของขวัญ")
        self.gift_run_btn = ctk.CTkButton(
            gift_main,
            textvariable=self.gift_run_var,
            command=self.toggle_gift_draw,
            height=46,
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            font=("Segoe UI", 15, "bold"),
            corner_radius=12
        )
        self.gift_run_btn.pack(fill="x", padx=12, pady=12)

        # 2. Relic Claim Card
        relic_card = self._card(parent, "ระบบรับรางวัลโบราณวัตถุ (Relic Claim)")
        relic_main = ctk.CTkFrame(relic_card, fg_color=CARD)
        relic_main.pack(fill="x", padx=18, pady=(0, 16))
        
        self.relic_run_var = tk.StringVar(value="🎁 เริ่มรับรางวัลโบราณวัตถุ")
        self.relic_run_btn = ctk.CTkButton(
            relic_main,
            textvariable=self.relic_run_var,
            command=self.run_relic_claim_manual,
            height=46,
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            font=("Segoe UI", 15, "bold"),
            corner_radius=12
        )
        self.relic_run_btn.pack(fill="x", padx=12, pady=12)

        # 3. Send Hearts Card (Beta)
        hearts_card = self._card(parent, "ระบบส่งหัวใจ (Send Hearts) (Beta)")
        hearts_main = ctk.CTkFrame(hearts_card, fg_color=CARD)
        hearts_main.pack(fill="x", padx=18, pady=(0, 16))
        
        self.hearts_run_var = tk.StringVar(value="▶ เริ่มส่งหัวใจ (Send Hearts) (Beta)")
        self.hearts_run_btn = ctk.CTkButton(
            hearts_main,
            textvariable=self.hearts_run_var,
            command=self.toggle_send_hearts,
            height=46,
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            font=("Segoe UI", 15, "bold"),
            corner_radius=12
        )
        self.hearts_run_btn.pack(fill="x", padx=12, pady=12)

        # 4. Treasure Extract Card (Beta)
        tr_card = self._card(parent, "ระบบสุ่มและย่อยสมบัติ (Treasure Draw & Extract) (Beta)")
        tr_main = ctk.CTkFrame(tr_card, fg_color=CARD)
        tr_main.pack(fill="x", padx=18, pady=(0, 16))
        
        # Warning label
        warning_lbl = ctk.CTkLabel(
            tr_main,
            text="⚠️ คำเตือน: โปรดกดล็อค (⭐) สมบัติที่ต้องการเก็บให้ครบถ้วนในเกมก่อน!\nบอทจะทำการย่อยสมบัติทั้งหมดที่ไม่ถูกล็อค",
            text_color="#FF8787",
            font=("Segoe UI", 12, "bold"),
            justify="left"
        )
        warning_lbl.pack(fill="x", padx=12, pady=(12, 4))
        
        self.tr_extract_run_var = tk.StringVar(value="▶ เริ่มสุ่มและย่อยสมบัติ (Beta)")
        self.tr_extract_run_btn = ctk.CTkButton(
            tr_main,
            textvariable=self.tr_extract_run_var,
            command=self.toggle_tr_extract,
            height=46,
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            font=("Segoe UI", 15, "bold"),
            corner_radius=12
        )
        self.tr_extract_run_btn.pack(fill="x", padx=12, pady=(4, 12))

    def toggle_gift_draw(self):
        if getattr(self, "gift_running", False):
            self.stop_gift_draw()
        else:
            self.start_gift_draw()

    def start_gift_draw(self):
        self._apply_config()
        bot.STOP_FLAG.clear()
        self.gift_running = True
        self.gift_run_var.set("■ หยุดสุ่มกล่องของขวัญ")
        self.gift_run_btn.configure(fg_color=BERRY, hover_color="#FF8787", text_color="white")
        self.status_var.set("สุ่มของขวัญ...")
        self.status_lbl.configure(text_color=GOLD)
        self._log("[app] เริ่มการสุ่มกล่องของขวัญอัตโนมัติ\n")
        
        def worker():
            try:
                if not bot.check_connection():
                    self._log("[app] เชื่อมต่อ ADB ไม่ได้ หยุดสุ่ม\n")
                    return
                bot.draw_gifts_loop()
            except Exception as e:
                self._log(f"[app] ระบบสุ่มกล่องทำงานขัดข้อง: {e}\n")
            finally:
                self.root.after(0, self._on_gift_draw_stopped)
                
        threading.Thread(target=worker, daemon=True).start()

    def stop_gift_draw(self):
        bot.STOP_FLAG.set()
        self.status_var.set("กำลังหยุด...")
        self.gift_run_btn.configure(state="disabled")
        self._log("[app] ส่งคำสั่งหยุดสุ่มกล่องของขวัญ...\n")

    def _on_gift_draw_stopped(self):
        self.gift_running = False
        self.gift_run_var.set("▶ เริ่มสุ่มกล่องของขวัญ")
        self.gift_run_btn.configure(
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            state="normal"
        )
        self.status_var.set("Ready")
        self.status_lbl.configure(text_color=MUTED)

    def toggle_send_hearts(self):
        if getattr(self, "hearts_running", False):
            self.stop_send_hearts()
        else:
            self.start_send_hearts()

    def start_send_hearts(self):
        self._apply_config()
        bot.STOP_FLAG.clear()
        self.hearts_running = True
        self.hearts_run_var.set("■ หยุดส่งหัวใจ")
        self.hearts_run_btn.configure(fg_color=BERRY, hover_color="#FF8787", text_color="white")
        self.status_var.set("ส่งหัวใจ...")
        self.status_lbl.configure(text_color=GOLD)
        self._log("[app] เริ่มส่งหัวใจให้เพื่อนอัตโนมัติ (Beta)\n")
        
        def worker():
            try:
                if not bot.check_connection():
                    self._log("[app] เชื่อมต่อ ADB ไม่ได้ หยุดส่งหัวใจ\n")
                    return
                bot.send_hearts_loop()
            except Exception as e:
                self._log(f"[app] ระบบส่งหัวใจทำงานขัดข้อง: {e}\n")
            finally:
                self.root.after(0, self._on_send_hearts_stopped)
                
        threading.Thread(target=worker, daemon=True).start()

    def stop_send_hearts(self):
        bot.STOP_FLAG.set()
        self.status_var.set("กำลังหยุด...")
        self.hearts_run_btn.configure(state="disabled")
        self._log("[app] ส่งคำสั่งหยุดส่งหัวใจ...\n")

    def _on_send_hearts_stopped(self):
        self.hearts_running = False
        self.hearts_run_var.set("▶ เริ่มส่งหัวใจ (Send Hearts) (Beta)")
        self.hearts_run_btn.configure(
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            state="normal"
        )
        self.status_var.set("Ready")
        self.status_lbl.configure(text_color=MUTED)

    def toggle_tr_extract(self):
        if getattr(self, "tr_extract_running", False):
            self.stop_tr_extract()
        else:
            self.start_tr_extract()

    def start_tr_extract(self):
        self._apply_config()
        bot.STOP_FLAG.clear()
        self.tr_extract_running = True
        self.tr_extract_run_var.set("■ หยุดสุ่มและย่อยสมบัติ")
        self.tr_extract_run_btn.configure(fg_color=BERRY, hover_color="#FF8787", text_color="white")
        self.status_var.set("สุ่มและย่อยสมบัติ...")
        self.status_lbl.configure(text_color=GOLD)
        self._log("[app] เริ่มระบบสุ่มและย่อยสมบัติอัตโนมัติ (Beta)\n")
        
        def worker():
            try:
                if not bot.check_connection():
                    self._log("[app] เชื่อมต่อ ADB ไม่ได้ หยุดทำงาน\n")
                    return
                bot.draw_and_extract_loop()
            except Exception as e:
                self._log(f"[app] ระบบสุ่มและย่อยสมบัติทำงานขัดข้อง: {e}\n")
            finally:
                self.root.after(0, self._on_tr_extract_stopped)
                
        threading.Thread(target=worker, daemon=True).start()

    def stop_tr_extract(self):
        bot.STOP_FLAG.set()
        self.status_var.set("กำลังหยุด...")
        self.tr_extract_run_btn.configure(state="disabled")
        self._log("[app] ส่งคำสั่งหยุดสุ่มและย่อยสมบัติ...\n")

    def _on_tr_extract_stopped(self):
        self.tr_extract_running = False
        self.tr_extract_run_var.set("▶ เริ่มสุ่มและย่อยสมบัติ (Beta)")
        self.tr_extract_run_btn.configure(
            fg_color=CARAMEL,
            hover_color=GOLD,
            text_color="#2B1D14",
            state="normal"
        )
        self.status_var.set("Ready")
        self.status_lbl.configure(text_color=MUTED)

    def run_relic_claim_manual(self):
        self._apply_config()
        self.relic_run_btn.configure(state="disabled", text="กำลังเคลม Relic...")
        self.status_var.set("เคลม Relic...")
        self.status_lbl.configure(text_color=GOLD)
        self._log("[app] เริ่มรับรางวัลโบราณวัตถุแบบกำหนดเอง\n")
        
        def worker():
            try:
                if not bot.check_connection():
                    self._log("[app] เชื่อมต่อ ADB ไม่ได้ หยุดเคลม\n")
                    return
                bot.collect_relic()
            except Exception as e:
                self._log(f"[app] ระบบเคลม Relic ทำงานขัดข้อง: {e}\n")
            finally:
                self.root.after(0, self._on_relic_claim_done)
                
        threading.Thread(target=worker, daemon=True).start()

    def _on_relic_claim_done(self):
        self.relic_run_btn.configure(state="normal", text="🎁 เริ่มรับรางวัลโบราณวัตถุ")
        self.status_var.set("Ready")
        self.status_lbl.configure(text_color=MUTED)

    def _build_control_card(self):
        card = self._card(self.control_main_parent, "Run Control")

        self.status_var = tk.StringVar(value="Ready")
        self.status_lbl = ctk.CTkLabel(card, textvariable=self.status_var, text_color=MUTED, font=("Segoe UI", 14, "bold"))
        self.status_lbl.pack(pady=(0, 10))

        loop_row = ctk.CTkFrame(card, fg_color=CARD)
        loop_row.pack(fill="x", padx=18, pady=(0, 12))
        loop_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(loop_row, text="รอบบอท", text_color=TEXT, font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.loops_var = tk.StringVar(value="0")
        ctk.CTkEntry(
            loop_row,
            textvariable=self.loops_var,
            fg_color=ENTRY,
            border_color=LINE,
            text_color=TEXT,
            width=92,
            height=34,
            justify="center",
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(loop_row, text="0 = วิ่งต่อเนื่อง", text_color=MUTED, font=("Segoe UI", 12)).grid(
            row=0, column=2, sticky="e", padx=(12, 0)
        )

        self.toggle_btn = ctk.CTkButton(
            card,
            text="▶ Run",
            command=self.toggle,
            height=58,
            fg_color=MINT,
            hover_color="#9BEA79",
            text_color="#1A2614",
            font=("Segoe UI", 22, "bold"),
            corner_radius=18,
        )
        self.toggle_btn.pack(fill="x", padx=18, pady=(0, 12))

        self.coins_var = tk.StringVar(value="Coin: -    Total: 0")
        coin = ctk.CTkFrame(card, fg_color=GOLD, corner_radius=999)
        coin.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkLabel(
            coin,
            textvariable=self.coins_var,
            text_color="#2B1D14",
            font=("Segoe UI", 15, "bold"),
        ).pack(padx=14, pady=10)

        self.captcha_var = tk.StringVar(value="พบแคปช่าทั้งหมด: 0 ครั้ง")
        self.captcha_lbl = ctk.CTkLabel(
            card,
            textvariable=self.captcha_var,
            text_color=GOLD,
            font=("Segoe UI", 13, "bold"),
        )
        self.captcha_lbl.pack(anchor="w", padx=18, pady=(0, 10))

        ctk.CTkLabel(card, text="Activity", text_color=GOLD, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18)
        self.log = ctk.CTkTextbox(
            card,
            height=210,
            fg_color=CARD_DARK,
            border_width=1,
            border_color=LINE,
            text_color=TEXT,
            font=("Consolas", 11),
            corner_radius=14,
            wrap="word",
        )
        self.log.pack(fill="both", expand=True, padx=18, pady=(8, 18))
        self._configure_log_tags()
        self.log.configure(state="disabled")

    def _init_emu_default(self):
        names = list(bot.EMU_PROFILES.keys())
        selected = names[0] if names else ""
        for name in names:
            try:
                if bot.EMU_PROFILES[name]["find_adb"]():
                    selected = name
                    break
            except Exception:
                pass
        if selected:
            self.emu_var.set(selected)
            self._on_emu_change(selected)

    def _on_emu_change(self, selected=None):
        emu = (selected or self.emu_var.get()).strip()
        if not emu:
            return
        adb_path = bot.adb_path_for_emu(emu)
        self.adb_var.set(adb_path)
        bot.ADB_PATH = adb_path
        self.dev_var.set("")
        bot.ADB_DEVICE = None
        self._refresh_instances()

    def _refresh_instances(self):
        emu = self.emu_var.get().strip()
        if not emu:
            return
        self.refresh_btn.configure(state="disabled", text="...")
        self.inst_combo.configure(values=["กำลังค้นหา..."])
        self.inst_var.set("กำลังค้นหา...")
        self.inst_serials = {}

        def worker():
            serials = bot.list_emu_instances(emu)

            def done():
                try:
                    labels = [bot._label_for_serial(serial, emu) for serial in serials]
                    self.inst_serials = dict(zip(labels, serials))
                    if labels:
                        self.inst_combo.configure(values=labels)
                        self.inst_var.set(labels[0])
                        self._on_inst_change(labels[0])
                    else:
                        self.inst_combo.configure(values=["ไม่พบ instance"])
                        self.inst_var.set("ไม่พบ instance")
                        self.dev_var.set("")
                        bot.ADB_DEVICE = None
                    self.refresh_btn.configure(state="normal", text="⟳")
                except Exception:
                    pass

            try:
                self.root.after(0, done)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _on_inst_change(self, selected=None):
        label = selected or self.inst_var.get()
        serial = self.inst_serials.get(label)
        if serial:
            self.dev_var.set(serial)
            bot.ADB_DEVICE = serial

    def _toggle_advanced(self):
        self.advanced_open = not self.advanced_open
        if self.advanced_open:
            self.advanced_btn.configure(text="▾ ตั้งค่าขั้นสูง")
            self.advanced_frame.pack(fill="x", padx=14, pady=(0, 14), after=self.advanced_btn)
        else:
            self.advanced_btn.configure(text="▸ ตั้งค่าขั้นสูง")
            self.advanced_frame.pack_forget()

    def auto_find_adb(self):
        path = bot.find_adb()
        self.adb_var.set(path)
        bot.ADB_PATH = path
        self._log(f"[app] ADB path updated: {path}\n")

    def _apply_config(self):
        bot.ADB_PATH = self.adb_var.get().strip()
        bot.ADB_DEVICE = self.dev_var.get().strip() or None
        for key, var in getattr(self, "opt_vars", {}).items():
            bot.SETTINGS[key] = bool(var.get())
        multi_selected = any(
            bool(bot.SETTINGS.get("multi_" + boost["key"], False))
            for boost in getattr(bot, "MULTI_BOOSTS", [])
        )
        bot.SETTINGS["use_multibuy"] = multi_selected
        try:
            val = int(self.mail_count_var.get().strip() or "0")
            bot.MAIL_MIN_COUNT = max(0, val)
        except ValueError:
            bot.MAIL_MIN_COUNT = 0

    def test_connection(self):
        self._apply_config()
        self._log("[app] Checking device link...\n")

        def worker():
            ok = bot.check_connection()
            if ok:
                self._log("[app] Device ready\n")
            else:
                self._log("[app] Device link failed. Check emulator, ADB path, and device id\n")

        threading.Thread(target=worker, daemon=True).start()

    def toggle(self):
        if not self.running:
            self.start_bot()
        else:
            self.stop_bot()

    def start_bot(self):
        self._apply_config()
        try:
            max_loops = max(0, int(self.loops_var.get().strip() or "0"))
        except ValueError:
            max_loops = 0
        self._max_loops = max_loops
        bot.STOP_FLAG.clear()
        self.running = True
        self.toggle_btn.configure(text="■ Stop", fg_color=BERRY, hover_color="#FF8787", text_color="white")
        self.status_var.set("Running")
        self.status_lbl.configure(text_color=MINT)
        self.coins_var.set("Coin: -    Total: 0")
        bot.CAPTCHA_COUNT = 0
        self.captcha_var.set("พบแคปช่าทั้งหมด: 0 ครั้ง")
        if max_loops:
            self._log(f"[app] Run started: {max_loops} loop(s)\n")
        else:
            self._log("[app] Run started: continuous mode\n")

        def worker():
            heartbeat_stop = threading.Event()
            try:
                if license_core.is_enabled():
                    # self._log("[license] กำลังตรวจสิทธิ์ใช้งาน...\n")
                    ok, info = license_core.check_license(force_online=True)
                    if not ok:
                        # self._log(f"[license] ใช้งานไม่ได้: {info}\n")
                        self.root.after(0, lambda: self._set_license_status(str(info), BERRY))
                        return
                    msg = self._license_text(info)
                    # self._log(f"[license] ตรวจสิทธิ์ผ่าน: {msg}\n")
                    self.root.after(0, lambda: (self._set_license_info(info), self._set_license_status(msg, MINT)))
                    self._start_license_heartbeat(heartbeat_stop)

                if not bot.check_connection():
                    self._log("[app] เชื่อมต่อ ADB ไม่ได้ หยุด\n")
                    return
                bot.run_state_machine(max_loops, on_loop_done=self._on_loop_done)
            except Exception as exc:
                if RELEASE_MODE:
                    self._log("[app] บอทหยุดเพราะข้อผิดพลาด กรุณาตรวจอีมูเลเตอร์และลองใหม่\n")
                else:
                    import traceback
                    self._log(f"[app] บอทหยุดเพราะข้อผิดพลาด: {exc}\n{traceback.format_exc()}\n")
            finally:
                try:
                    self.root.after(0, self._on_bot_stopped)
                except Exception:
                    pass
                heartbeat_stop.set()

        self.bot_thread = threading.Thread(target=worker, daemon=True)
        self.bot_thread.start()

    def _start_license_heartbeat(self, stop_event):
        def heartbeat():
            while not stop_event.wait(600):
                ok, info = license_core.check_license(force_online=True)
                if ok:
                    msg = self._license_text(info)
                    self.root.after(0, lambda i=info, m=msg: (self._set_license_info(i), self._set_license_status(m, MINT)))
                    continue
                # self._log(f"[license] สิทธิ์ไม่ผ่านระหว่างใช้งาน: {info}\n")
                bot.STOP_FLAG.set()
                self.root.after(0, lambda: self._set_license_status(str(info), BERRY))
                break

        threading.Thread(target=heartbeat, daemon=True).start()

    def _on_loop_done(self, loops_done):
        if self._max_loops:
            remaining = max(0, self._max_loops - loops_done)
            self.root.after(0, lambda: self.loops_var.set(str(remaining)))

    def _update_coins(self, coins, total):
        last = f"{coins:,}" if coins is not None else "N/A"
        self.coins_var.set(f"Coin: {last}    Total: {total:,}")

    def _update_captcha(self, cnt):
        self.captcha_var.set(f"พบแคปช่าทั้งหมด: {cnt} ครั้ง")

    def stop_bot(self):
        bot.STOP_FLAG.set()
        self.status_var.set("Stopping...")
        self.status_lbl.configure(text_color=GOLD)
        self.toggle_btn.configure(state="disabled")
        self._log("[app] Stop requested. Waiting for current step...\n")

    def _on_bot_stopped(self):
        self.running = False
        self.toggle_btn.configure(
            text="▶ Run",
            fg_color=MINT,
            hover_color="#9BEA79",
            text_color="#1A2614",
            state="normal",
        )
        self.status_var.set("Ready")
        self.status_lbl.configure(text_color=MUTED)

    def _enqueue_bot_log(self, message):
        for line in str(message).splitlines():
            line = line.strip()
            if RELEASE_MODE and self._is_internal_log_line(line):
                continue
            if not line or not self._should_show_bot_log(line):
                continue
            self.log_queue.put(self._friendly_bot_log(line) + "\n")

    def _is_internal_log_line(self, line):
        lower = line.lower()
        internal = (
            "traceback",
            'file "',
            "line ",
            "cv2.",
            "numpy",
            "subprocess",
            "c:\\",
            "adb.exe",
            "score=",
            "confidence=",
            "ความมั่นใจ=",
            "คะแนน",
            "พิกัด",
        )
        return any(token in lower for token in internal)

    def _should_show_bot_log(self, line):
        raw = line.strip()
        lower = raw.lower()
        if raw.startswith("====="):
            return True
        important = (
            "[warn]",
            "[err]",
            "[fatal]",
            "[coins]",
            "[loop]",
        )
        if any(token in lower for token in important):
            return True
        if "เจอหน้า result" in lower or "ครบ" in raw and "รอบ" in raw:
            return True
        if "บอทหยุด" in raw or "ctrl+c" in lower:
            return True
        return False

    def _friendly_bot_log(self, line):
        raw = line.strip()
        lower = raw.lower()
        if "[state 1]" in lower:
            return "[run] เตรียมรอบใหม่"
        if "[state 2]" in lower:
            return "[run] กำลังเล่น"
        if "[state 3]" in lower:
            return "[run] เข้าหน้าสรุปผล"
        if lower.startswith("[coins]"):
            return raw.replace("[coins]", "[coin]").replace("เหรียญรอบนี้", "Coin")
        if lower.startswith("[loop]"):
            return raw.replace("[loop]", "[run]")
        if "เจอหน้า result" in lower:
            return "[run] เจอหน้าผลลัพธ์"
        return raw

    def _log(self, text):
        if RELEASE_MODE:
            text = str(text)
            if "Traceback" in text or 'File "' in text:
                text = "[app] เกิดข้อผิดพลาด กรุณาลองใหม่\n"
        self.log_queue.put(text)

    def _configure_log_tags(self):
        try:
            self.log.tag_config("log_time", foreground=LOG_TIME)
            self.log.tag_config("log_ok", foreground=LOG_OK)
            self.log.tag_config("log_warn", foreground=LOG_WARN)
            self.log.tag_config("log_coin", foreground=LOG_COIN)
            self.log.tag_config("log_info", foreground=LOG_INFO)
            self.log.tag_config("log_state", foreground=LOG_STATE)
            self.log.tag_config("log_text", foreground=TEXT)
        except Exception:
            pass

    def _tag_for_log_line(self, line):
        raw = line.strip()
        lower = raw.lower()
        if "=====" in raw or "[state" in lower:
            return "log_state"
        if "[coins]" in lower or "[coin]" in lower or "coin" in lower or "เหรียญ" in raw:
            return "log_coin"
        if "[warn]" in lower or "[err]" in lower or "❌" in raw or "ผิดพลาด" in raw or "ไม่ได้" in raw or "⚠️" in raw:
            return "log_warn"
        if "[ok]" in lower or "✅" in raw or "สำเร็จ" in raw:
            return "log_ok"
        if raw.startswith("[") or "[app]" in lower or "[license]" in lower or "[run]" in lower or "[ระบบ" in raw or "[โบราณ" in raw or "[จดหมาย" in raw:
            return "log_info"
        return "log_text"

    def _emit(self, text):
        lines = str(text).splitlines(True)
        if not lines:
            return
        self.log.configure(state="normal")
        try:
            for line in lines:
                if not line:
                    continue
                if line == "\n":
                    self.log.insert("end", line)
                    continue
                has_newline = line.endswith("\n")
                body = line[:-1] if has_newline else line
                if not body:
                    self.log.insert("end", "\n")
                    continue
                stamp = datetime.datetime.now().strftime("%H:%M:%S")
                tag = self._tag_for_log_line(body)
                self.log.insert("end", stamp + " ", "log_time")
                self.log.insert("end", body, tag)
                if has_newline:
                    self.log.insert("end", "\n")
        finally:
            self.log.configure(state="disabled")

    def _poll_log(self):
        if self._window_is_moving():
            self.root.after(120, self._poll_log)
            return
        inserted = False
        batch = []
        try:
            count = 0
            while count < 300:
                batch.append(self.log_queue.get_nowait())
                count += 1
        except queue.Empty:
            pass
        except Exception:
            pass

        if batch:
            self._emit("".join(batch))
            inserted = True

        if inserted:
            try:
                self.log.see("end")
                if int(self.log.index("end-1c").split(".")[0]) > 800:
                    self.log.configure(state="normal")
                    self.log.delete("1.0", "300.0")
                    self.log.configure(state="disabled")
            except Exception:
                pass

        self.root.after(220, self._poll_log)

    def on_close(self):
        bot.STOP_FLAG.set()
        time.sleep(0.1)
        self.root.destroy()


def main():
    root = ctk.CTk()
    JLMainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
