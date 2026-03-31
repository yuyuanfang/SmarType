"""
快打 SmarType — 管理介面 dashboard.py  v3  (CustomTkinter)
獨立視窗，開機自動啟動，× 最小化到托盤
"""
import customtkinter as ctk
import json, sys, threading
from pathlib import Path

from tabs.tab_home     import TabHome
from tabs.tab_history  import TabHistory
from tabs.tab_diary    import TabDiary
from tabs.tab_vocab    import TabVocab
from tabs.tab_settings import TabSettings

# ── 路徑 ──────────────────────────────────────────────────────────────────────
CONFIG_DIR   = Path(__file__).parent / "userdata"
STATUS_FILE  = CONFIG_DIR / "status.json"
SIGNAL_FILE  = CONFIG_DIR / "dashboard_signal.json"

# ── 主題設定 ──────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

# ── DPI 縮放（高解析度螢幕必備）──────────────────────────────────────────────
try:
    import ctypes as _ctypes
    _ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass
ctk.set_widget_scaling(1.2)
ctk.set_window_scaling(1.2)

ACCENT  = "#1D9E75"
ACCENT2 = "#17876A"
BG      = "#1a1a1a"
SIDEBAR = "#1e1e1e"
TEXT    = "#e8e8e8"
DIM     = "#888888"
ORANGE  = "#e08020"

FONT_BODY  = ("Microsoft YaHei", 12)
FONT_SMALL = ("Microsoft YaHei", 10)


# ── 工具函式 ──────────────────────────────────────────────────────────────────
def load_config():
    try:
        cfg_file = CONFIG_DIR / "config.json"
        if cfg_file.exists():
            return json.loads(cfg_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def read_status():
    try:
        if STATUS_FILE.exists():
            return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"state": "idle", "text": "", "ts": "", "model": "--"}


# ── 主視窗 ────────────────────────────────────────────────────────────────────
class Dashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        self._current_page = "home"

        self.title("快打 SmarType")
        self.geometry("1100x720")
        self.minsize(780, 560)
        self.configure(fg_color=BG)
        self.after(150, lambda: self.state("zoomed"))
        self._is_fullscreen = False

        self.protocol("WM_DELETE_WINDOW", self._hide_window)
        self.bind("<F11>", self._toggle_fullscreen)
        self.bind("<Escape>", self._exit_fullscreen)

        self._build_ui()
        self._start_status_poll()

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._sidebar = ctk.CTkFrame(self, width=170, fg_color=SIDEBAR,
                                      corner_radius=0)
        self._sidebar.grid(row=0, column=0, sticky="nsew")
        self._sidebar.grid_propagate(False)
        self._build_sidebar()

        self._main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._main.grid(row=0, column=1, sticky="nsew")
        self._main.grid_columnconfigure(0, weight=1)
        self._main.grid_rowconfigure(0, weight=1)

        # 建立各分頁
        self._tab_home     = TabHome(self._main, self)
        self._tab_history  = TabHistory(self._main, self)
        self._tab_diary    = TabDiary(self._main, self)
        self._tab_vocab    = TabVocab(self._main, self)
        self._tab_settings = TabSettings(self._main, self)

        self._pages = {
            "home":     self._tab_home,
            "history":  self._tab_history,
            "diary":    self._tab_diary,
            "vocab":    self._tab_vocab,
            "settings": self._tab_settings,
        }

        self._switch("home")

    def _build_sidebar(self):
        sb = self._sidebar

        ctk.CTkLabel(sb, text="快打", font=("Microsoft YaHei", 24, "bold"),
                     text_color=ACCENT).pack(anchor="w", padx=16, pady=(20, 0))
        ctk.CTkLabel(sb, text="SmarType",
                     font=("Segoe UI", 12), text_color=TEXT).pack(anchor="w", padx=16)
        ctk.CTkLabel(sb, text="語音聽寫 · 快打成文",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=16, pady=(4, 16))

        ctk.CTkFrame(sb, height=1, fg_color="#333").pack(fill="x", padx=12, pady=(0, 10))

        self._nav_btns = {}
        for key, icon, label in [
            ("home",     "\u2302",  "首頁"),
            ("history",  "\U0001f550", "歷史紀錄"),
            ("diary",    "\U0001f4d3", "語音日記"),
            ("vocab",    "\U0001f4da", "字典"),
            ("settings", "\u2699",  "設定"),
        ]:
            btn = ctk.CTkButton(
                sb, text=f"  {icon}  {label}",
                font=FONT_BODY, anchor="w",
                fg_color="transparent", text_color=DIM,
                hover_color="#2a2a2a",
                corner_radius=8, height=40,
                command=lambda k=key: self._switch(k))
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_btns[key] = btn

        ctk.CTkFrame(sb, height=1, fg_color="#333").pack(fill="x", padx=12, pady=(12, 6),
                                                          side="bottom")
        self._status_dot = ctk.CTkLabel(sb, text="\u25cf 待機中",
                                         font=FONT_SMALL, text_color=DIM)
        self._status_dot.pack(anchor="w", padx=16, pady=(0, 12), side="bottom")

    def _switch(self, key):
        for p in self._pages.values():
            p.place_forget()
        self._pages[key].place(in_=self._main, x=0, y=0, relwidth=1, relheight=1)

        for k, btn in self._nav_btns.items():
            if k == key:
                btn.configure(fg_color=ACCENT, text_color="white",
                              hover_color=ACCENT2)
            else:
                btn.configure(fg_color="transparent", text_color=DIM,
                              hover_color="#2a2a2a")
        self._current_page = key

        # 切頁時停止首頁麥克風電平表
        self._tab_home._stop_mic_meter()

        if key == "home":     self._tab_home.refresh_recent()
        if key == "history":  self._tab_history.refresh()
        if key == "vocab":    self._tab_vocab.refresh()
        if key == "diary":    self._tab_diary.refresh()

    # ── 即時狀態輪詢 ─────────────────────────────────────────────────────────
    def _start_status_poll(self):
        self._poll_status()

    def _poll_status(self):
        try:
            s = read_status()
            state = s.get("state", "idle")
            if state == "recording":
                self._status_dot.configure(text="\U0001f534 錄音中", text_color="#ff5555")
                if hasattr(self._tab_home, "_status_card_label"):
                    self._tab_home._status_card_label.configure(text="錄音中", text_color="#ff5555")
            elif state == "processing":
                self._status_dot.configure(text="\u23f3 識別中", text_color=ORANGE)
                if hasattr(self._tab_home, "_status_card_label"):
                    self._tab_home._status_card_label.configure(text="識別中", text_color=ORANGE)
            elif state == "done":
                self._status_dot.configure(text="\u2713 完成", text_color=ACCENT)
                if hasattr(self._tab_home, "_status_card_label"):
                    self._tab_home._status_card_label.configure(text="完成", text_color=ACCENT)
            else:
                self._status_dot.configure(text="\u25cf 待機中", text_color=DIM)
                if hasattr(self._tab_home, "_status_card_label"):
                    self._tab_home._status_card_label.configure(text="待機中", text_color=ACCENT)
        except Exception:
            pass
        try:
            if SIGNAL_FILE.exists():
                sig = json.loads(SIGNAL_FILE.read_text(encoding="utf-8"))
                SIGNAL_FILE.unlink(missing_ok=True)
                if sig.get("cmd") == "show":
                    self.show_window()
        except Exception:
            pass
        self.after(600, self._poll_status)

    # ── 全螢幕 ───────────────────────────────────────────────────────────────
    def _toggle_fullscreen(self, event=None):
        self._is_fullscreen = not self._is_fullscreen
        self.attributes("-fullscreen", self._is_fullscreen)

    def _exit_fullscreen(self, event=None):
        if self._is_fullscreen:
            self._is_fullscreen = False
            self.attributes("-fullscreen", False)

    # ── 最小化到托盤 ─────────────────────────────────────────────────────────
    def _hide_window(self):
        self._tab_home._stop_mic_meter()
        self.withdraw()

    def show_window(self):
        self.deiconify()
        self.after(100, lambda: (self.lift(), self.focus_force()))


# ── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import ctypes as _ct
    _mutex = _ct.windll.kernel32.CreateMutexW(None, True, "SmarType_Dashboard_v1")
    if _ct.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        try:
            import json as _j
            SIGNAL_FILE.write_text(_j.dumps({"cmd": "show"}), encoding="utf-8")
        except Exception:
            pass
        sys.exit(0)
    app = Dashboard()
    app.mainloop()
