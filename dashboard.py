"""
快打 SmarType — 管理介面 dashboard.py  v3  (CustomTkinter)
獨立視窗，開機自動啟動，× 最小化到托盤
"""
import customtkinter as ctk
from tkinter import ttk, messagebox
import tkinter as tk
import json, sys, subprocess, datetime, threading, time
from pathlib import Path

# ── 路徑 ──────────────────────────────────────────────────────────────────────
CONFIG_DIR   = Path(__file__).parent / "userdata"
CONFIG_FILE  = CONFIG_DIR / "config.json"
LOG_FILE     = CONFIG_DIR / "history.jsonl"
DICT_FILE    = CONFIG_DIR / "smart_dict.json"
STATUS_FILE  = CONFIG_DIR / "status.json"
SIGNAL_FILE  = CONFIG_DIR / "dashboard_signal.json"
RULES_FILE   = CONFIG_DIR / "app_rules.json"
DIARY_DIR    = CONFIG_DIR / "diary"

# ── 主題設定 ──────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

# ── DPI 縮放（高解析度螢幕必備）──────────────────────────────────────────────
try:
    import ctypes as _ctypes
    _ctypes.windll.shcore.SetProcessDpiAwareness(1)   # System DPI Aware
except Exception:
    pass
ctk.set_widget_scaling(1.2)    # 所有 CTK 元件放大 1.2×
ctk.set_window_scaling(1.2)

ACCENT  = "#1D9E75"
ACCENT2 = "#17876A"
BG      = "#1a1a1a"
CARD    = "#242424"
SIDEBAR = "#1e1e1e"
TEXT    = "#e8e8e8"
DIM     = "#888888"
INPUT   = "#2e2e2e"
RED     = "#e05555"
ORANGE  = "#e08020"

FONT_TITLE  = ("Microsoft YaHei", 18, "bold")
FONT_HEAD   = ("Microsoft YaHei", 13, "bold")
FONT_BODY   = ("Microsoft YaHei", 12)
FONT_SMALL  = ("Microsoft YaHei", 10)
FONT_MONO   = ("Consolas", 11)


# ── 工具函式 ──────────────────────────────────────────────────────────────────
def load_config():
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def read_status():
    try:
        if STATUS_FILE.exists():
            return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"state": "idle", "text": "", "ts": "", "model": "--"}

def get_stats():
    chars, sessions = 0, 0
    try:
        if LOG_FILE.exists():
            for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                    chars   += r.get("chars", 0)
                    sessions += 1
                except Exception:
                    pass
    except Exception:
        pass
    return chars, sessions

def get_mic_list():
    """列出可用麥克風，過濾重複名稱和無效裝置"""
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        default_idx = -1
        try:
            default_idx = pa.get_default_input_device_info().get("index", -1)
        except Exception:
            pass

        raw = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) <= 0:
                continue
            rate = info.get("defaultSampleRate", 0)
            if rate <= 0:
                continue  # 無效裝置
            name = info["name"].strip()
            if not name:
                continue
            raw.append({"index": i, "name": name,
                        "default": i == default_idx, "rate": rate})

        # 去重：同名裝置只保留第一個（或 default 的那個）
        seen, deduped = {}, []
        for m in raw:
            key = m["name"]
            if key in seen:
                # 如果新的是 default，替換舊的
                if m["default"]:
                    deduped[seen[key]] = m
                continue
            seen[key] = len(deduped)
            deduped.append(m)

        # 排序：default 排第一，其餘按名稱
        deduped.sort(key=lambda m: (not m["default"], m["name"]))

        mics = {}
        for m in deduped:
            prefix = "★ " if m["default"] else ""
            mics[m["index"]] = f"[{m['index']}] {prefix}{m['name'][:36]}"

        pa.terminate()
        return mics
    except Exception:
        return {}


# ── 主視窗 ────────────────────────────────────────────────────────────────────
class Dashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        self._current_page = "home"
        self._mic_meter_active = False
        self._mic_stream = None
        self._mic_pa     = None
        # 歷史分頁
        self._hist_page  = 0
        self._hist_data  = []   # 全部已載入紀錄 (list of dict)
        self._HIST_PAGE_SIZE = 25

        self.title("快打 SmarType")
        self.geometry("1100x720")
        self.minsize(780, 560)
        self.configure(fg_color=BG)
        self.after(150, lambda: self.state("zoomed"))  # 延遲最大化避免 DPI 崩潰
        self._is_fullscreen = False   # F11 真全螢幕狀態

        self.protocol("WM_DELETE_WINDOW", self._hide_window)
        self.bind("<F11>", self._toggle_fullscreen)
        self.bind("<Escape>", self._exit_fullscreen)

        self._build_ui()
        self._start_status_poll()

    # ── 界面建構 ─────────────────────────────────────────────────────────────
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

        self._pages = {}
        self._pages["home"]     = self._build_home()
        self._pages["history"]  = self._build_history()
        self._pages["diary"]    = self._build_diary()
        self._pages["vocab"]    = self._build_vocab()
        self._pages["settings"] = self._build_settings()

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
            ("home",     "⌂",  "首頁"),
            ("history",  "🕐", "歷史紀錄"),
            ("diary",    "📓", "語音日記"),
            ("vocab",    "📚", "字典"),
            ("settings", "⚙",  "設定"),
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
        self._status_dot = ctk.CTkLabel(sb, text="● 待機中",
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

        # 切頁時停止麥克風電平表
        self._stop_mic_meter()
        if key == "home":
            self._refresh_recent()

        if key == "history":  self._refresh_history()
        if key == "vocab":    self._refresh_vocab()
        if key == "diary":    self._refresh_diary()

    # ── 首頁 ─────────────────────────────────────────────────────────────────
    def _build_home(self):
        page = ctk.CTkFrame(self._main, fg_color=BG, corner_radius=0)

        # 標題
        header = ctk.CTkFrame(page, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 0))
        ctk.CTkLabel(header, text="自然說話，快速成文",
                     font=FONT_TITLE, text_color=TEXT,
                     anchor="w").pack(side="left")

        cfg = self.config_data
        hk  = cfg.get("hotkey", "right shift").upper()
        ctk.CTkLabel(page,
                     text=f"熱鍵：{hk}（按住說話，放開停止）  ·  自動偵測前景視窗語言",
                     font=FONT_SMALL, text_color=DIM,
                     anchor="w").pack(anchor="w", padx=20, pady=(2, 12))

        # 狀態卡片列
        chars, sessions = get_stats()
        card_row = ctk.CTkFrame(page, fg_color="transparent")
        card_row.pack(fill="x", padx=16)
        card_row.columnconfigure(0, weight=1)
        card_row.columnconfigure(1, weight=1)
        card_row.columnconfigure(2, weight=1)

        for col, (title, val, sub, color) in enumerate([
            ("狀態",    "待機中",      "系統運行中",     ACCENT),
            ("累積字數", f"{chars:,}", "已貼上內容統計", TEXT),
            ("錄音次數", str(sessions), "本機歷史計數",   TEXT),
        ]):
            card = ctk.CTkFrame(card_row, fg_color=CARD, corner_radius=12, height=75)
            card.grid(row=0, column=col, sticky="ew", padx=(0 if col==0 else 6, 0), pady=4)
            card.grid_propagate(False)
            if title == "狀態":
                self._status_card_label = ctk.CTkLabel(
                    card, text=val,
                    font=("Microsoft YaHei", 17, "bold"), text_color=color)
                self._status_card_label.pack(anchor="w", padx=14, pady=(14, 2))
            else:
                ctk.CTkLabel(card, text=val,
                             font=("Microsoft YaHei", 17, "bold"),
                             text_color=color).pack(anchor="w", padx=14, pady=(14, 2))
            ctk.CTkLabel(card, text=title, font=FONT_SMALL,
                         text_color=DIM).pack(anchor="w", padx=14)

        # 下半：麥克風設定 + 最近輸出
        bottom = ctk.CTkFrame(page, fg_color="transparent")
        bottom.pack(fill="both", expand=True, padx=16, pady=8)
        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(0, weight=1)

        # 左：麥克風設定
        left = ctk.CTkFrame(bottom, fg_color=CARD, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ctk.CTkLabel(left, text="輸入設定", font=FONT_HEAD,
                     text_color=TEXT).pack(anchor="w", padx=14, pady=(12, 8))

        # 麥克風 + 語言（同一行）
        mic_list = get_mic_list()
        cur_idx  = self.config_data.get("mic_index", 1)
        mic_vals = list(mic_list.values()) or ["預設麥克風"]
        cur_mic  = mic_list.get(cur_idx, mic_vals[0])
        self._mic_var = ctk.StringVar(value=cur_mic)

        mic_lang_row = ctk.CTkFrame(left, fg_color="transparent")
        mic_lang_row.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(mic_lang_row, text="麥克風", font=FONT_SMALL,
                     text_color=DIM, width=50, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(mic_lang_row, values=mic_vals,
                          variable=self._mic_var,
                          fg_color=INPUT, button_color=ACCENT,
                          font=FONT_SMALL, width=180,
                          command=lambda _: self._restart_mic_meter()).pack(side="left", padx=(0, 10))

        self._lang_var = ctk.StringVar(value=self.config_data.get("default_lang","zh-TW"))
        ctk.CTkLabel(mic_lang_row, text="語言", font=FONT_SMALL,
                     text_color=DIM, width=35, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(mic_lang_row, values=["zh-TW","zh-CN","en","ja"],
                          variable=self._lang_var,
                          fg_color=INPUT, button_color=ACCENT,
                          font=FONT_SMALL, width=90).pack(side="left")

        # 收音靈敏度（閾值）
        sep = ctk.CTkFrame(left, fg_color="#333", height=1)
        sep.pack(fill="x", padx=14, pady=(8, 6))

        ctk.CTkLabel(left, text="麥克風靈敏度校準",
                     font=("Microsoft YaHei", 11, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=14, pady=(0, 2))
        ctk.CTkLabel(left,
                     text="閾值越低=越靈敏（容易誤觸）  閾值越高=越穩定（需要更大聲）",
                     font=FONT_SMALL, text_color=DIM,
                     justify="left").pack(anchor="w", padx=14, pady=(0, 6))

        # 即時電平表
        meter_frame = ctk.CTkFrame(left, fg_color=INPUT, corner_radius=8)
        meter_frame.pack(fill="x", padx=14, pady=(0, 4))

        meter_top = ctk.CTkFrame(meter_frame, fg_color="transparent")
        meter_top.pack(fill="x", padx=8, pady=(6, 2))
        self._mic_test_btn = ctk.CTkButton(meter_top, text="🎤 測試麥克風",
                      fg_color="#333", hover_color="#444", text_color=TEXT,
                      font=FONT_SMALL, corner_radius=6, height=26, width=110,
                      command=self._toggle_mic_meter)
        self._mic_test_btn.pack(side="left")
        self._rms_label = ctk.CTkLabel(meter_top, text="點擊測試",
                                        font=FONT_MONO, text_color=DIM)
        self._rms_label.pack(side="right")

        self._meter_bar = ctk.CTkProgressBar(meter_frame, height=12,
                                              progress_color=ACCENT,
                                              fg_color="#1a1a1a",
                                              corner_radius=4)
        self._meter_bar.set(0)
        self._meter_bar.pack(fill="x", padx=8, pady=(0, 8))

        # 閾值滑桿
        thr_row = ctk.CTkFrame(left, fg_color="transparent")
        thr_row.pack(fill="x", padx=14, pady=(0, 2))
        self._thr_var = ctk.IntVar(value=self.config_data.get("energy_thr", 20))
        ctk.CTkLabel(thr_row, text="閾值", font=FONT_BODY,
                     text_color=DIM, width=40, anchor="w").pack(side="left")
        ctk.CTkSlider(thr_row, from_=5, to=200,
                      variable=self._thr_var,
                      progress_color=ORANGE,
                      button_color=ORANGE,
                      width=140,
                      command=lambda v: self._thr_val_label.configure(
                          text=str(int(v)))).pack(side="left", padx=6)
        self._thr_val_label = ctk.CTkLabel(thr_row,
                                            text=str(self._thr_var.get()),
                                            font=FONT_MONO, text_color=ORANGE, width=36)
        self._thr_val_label.pack(side="left")

        # 標示線說明
        ctk.CTkLabel(left,
                     text="「建議閾值」= 環境噪音 RMS × 2",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=14, pady=(0, 2))

        # 自動校準 + 儲存（同一行）
        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkButton(btn_row, text="⚡ 自動校準",
                      fg_color=INPUT, hover_color="#3a3a3a",
                      text_color=TEXT,
                      font=FONT_BODY, corner_radius=8, height=30,
                      command=self._auto_calibrate).pack(side="left", padx=(0, 6))
        self._calibrate_label = ctk.CTkLabel(btn_row, text="",
                                              font=FONT_SMALL, text_color=DIM)
        self._calibrate_label.pack(side="left")

        # ── 朗讀校準 ──
        read_card = ctk.CTkFrame(left, fg_color=INPUT, corner_radius=8)
        read_card.pack(fill="x", padx=14, pady=(6, 4))

        ctk.CTkLabel(read_card, text="📖 朗讀校準",
                     font=FONT_HEAD, text_color=TEXT).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(read_card, text="朗讀下方文字，系統比對辨識結果來評估收音品質",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=10, pady=(0, 4))

        self._read_passage = ctk.CTkTextbox(read_card, fg_color="#1a1a1a",
                                             font=FONT_BODY, text_color="#bbddcc",
                                             height=60, wrap="word")
        self._read_passage.pack(fill="x", padx=10, pady=(0, 6))
        self._read_passage.insert("1.0", self._get_test_passage())
        self._read_passage.configure(state="disabled")

        read_btn_row = ctk.CTkFrame(read_card, fg_color="transparent")
        read_btn_row.pack(fill="x", padx=10, pady=(0, 4))
        self._read_test_btn = ctk.CTkButton(
            read_btn_row, text="🎙 開始朗讀測試",
            fg_color="#333", hover_color="#444",
            text_color=TEXT, font=FONT_BODY,
            corner_radius=8, height=30,
            command=self._toggle_read_test)
        self._read_test_btn.pack(side="left", padx=(0, 6))
        ctk.CTkButton(read_btn_row, text="🔄", width=30,
                      fg_color="#333", hover_color="#444",
                      text_color=DIM, font=FONT_BODY,
                      corner_radius=8, height=30,
                      command=self._refresh_passage).pack(side="left")

        self._read_result_label = ctk.CTkLabel(read_card, text="",
                                                font=FONT_SMALL, text_color=DIM,
                                                wraplength=360, justify="left")
        self._read_result_label.pack(anchor="w", padx=10, pady=(0, 8))

        self._read_test_active = False

        ctk.CTkButton(left, text="儲存設定",
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_BODY, corner_radius=8,
                      height=32,
                      command=self._save_quick).pack(anchor="w", padx=14, pady=(4, 12))

        # 右：最近輸出
        right = ctk.CTkFrame(bottom, fg_color=CARD, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="最近輸出", font=FONT_HEAD,
                     text_color=TEXT).grid(row=0, column=0, sticky="w",
                                           padx=14, pady=(12, 6))
        self._recent_box = ctk.CTkTextbox(right, fg_color="transparent",
                                           font=FONT_BODY,
                                           text_color=TEXT,
                                           state="disabled",
                                           wrap="word")
        self._recent_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        return page

    def _row_widget(self, parent, label, widget):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=5)
        ctk.CTkLabel(row, text=label, font=FONT_BODY,
                     text_color=DIM, width=80, anchor="w").pack(side="left")
        widget.pack(side="left")

    # ── 麥克風電平表 ─────────────────────────────────────────────────────────
    def _get_selected_mic_index(self):
        mic_list = get_mic_list()
        sel = self._mic_var.get()
        for idx, name in mic_list.items():
            if name == sel:
                return idx
        return self.config_data.get("mic_index", 1)

    def _toggle_mic_meter(self):
        if self._mic_meter_active:
            self._stop_mic_meter()
            self._mic_test_btn.configure(text="🎤 測試麥克風", fg_color="#333")
            self._rms_label.configure(text="已停止", text_color=DIM)
        else:
            self._start_mic_meter()
            self._mic_test_btn.configure(text="⏹ 停止測試", fg_color=RED)

    def _start_mic_meter(self):
        if self._mic_meter_active:
            return
        self._mic_meter_active = True
        self._mic_meter_start = time.time()
        threading.Thread(target=self._mic_meter_loop, daemon=True).start()

    def _stop_mic_meter(self):
        self._mic_meter_active = False
        if self._mic_stream:
            try:
                self._mic_stream.stop_stream()
                self._mic_stream.close()
            except Exception:
                pass
            self._mic_stream = None
        if self._mic_pa:
            try:
                self._mic_pa.terminate()
            except Exception:
                pass
            self._mic_pa = None

    def _restart_mic_meter(self):
        self._stop_mic_meter()
        time.sleep(0.1)
        self._start_mic_meter()
        self._mic_test_btn.configure(text="⏹ 停止測試", fg_color=RED)

    def _mic_meter_loop(self):
        import pyaudio, audioop
        CHUNK = 512
        RATE  = 16000
        dev   = self._get_selected_mic_index()
        try:
            self._mic_pa = pyaudio.PyAudio()
            self._mic_stream = self._mic_pa.open(
                format=pyaudio.paInt16, channels=1, rate=RATE,
                input=True, input_device_index=dev,
                frames_per_buffer=CHUNK)
        except Exception as e:
            self.after(0, lambda: self._rms_label.configure(
                text=f"麥克風錯誤", text_color=RED))
            self._mic_meter_active = False
            return

        while self._mic_meter_active:
            # 自動停止：15 秒後
            if time.time() - self._mic_meter_start > 15:
                self.after(0, lambda: (
                    self._mic_test_btn.configure(text="🎤 測試麥克風", fg_color="#333"),
                    self._rms_label.configure(text="已停止（15s）", text_color=DIM),
                    self._meter_bar.set(0)
                ))
                break
            try:
                data = self._mic_stream.read(CHUNK, exception_on_overflow=False)
                rms  = audioop.rms(data, 2)
                thr  = self._thr_var.get()
                fill = min(1.0, rms / 300.0)
                color = "#ff5555" if rms > thr else (ORANGE if rms > thr * 0.6 else ACCENT)
                rms_copy = rms
                fill_copy = fill
                color_copy = color
                thr_copy = thr
                self.after(0, lambda r=rms_copy, f=fill_copy, c=color_copy, t=thr_copy: (
                    self._rms_label.configure(
                        text=f"RMS: {r:>4d}  閾值: {t}",
                        text_color=c),
                    self._meter_bar.configure(progress_color=c),
                    self._meter_bar.set(f)
                ))
                time.sleep(0.05)
            except Exception:
                break

        self._stop_mic_meter()

    def _auto_calibrate(self):
        """錄製 2 秒背景噪音，自動設定建議閾值"""
        self._calibrate_label.configure(text="校準中…請保持安靜", text_color=ORANGE)
        self.update()

        def _run():
            import pyaudio, audioop
            CHUNK = 512
            RATE  = 16000
            dev   = self._get_selected_mic_index()
            try:
                pa = pyaudio.PyAudio()
                stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                                  input=True, input_device_index=dev,
                                  frames_per_buffer=CHUNK)
                samples = []
                for _ in range(int(RATE / CHUNK * 2)):
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    samples.append(audioop.rms(data, 2))
                stream.stop_stream(); stream.close(); pa.terminate()

                noise_avg = sum(samples) // len(samples)
                suggested = max(10, int(noise_avg * 2.5))
                suggested = min(suggested, 150)

                def _apply():
                    self._thr_var.set(suggested)
                    self._thr_val_label.configure(text=str(suggested))
                    self._calibrate_label.configure(
                        text=f"噪音 avg={noise_avg}  →  建議閾值={suggested}",
                        text_color=ACCENT)
                self.after(0, _apply)
            except Exception as e:
                self.after(0, lambda: self._calibrate_label.configure(
                    text=f"校準失敗：{e}", text_color=RED))

        threading.Thread(target=_run, daemon=True).start()

    # ── 朗讀校準 ─────────────────────────────────────────────────────────────
    _TEST_PASSAGES = [
        "今天天氣很好，我打算去公園散步，順便買一杯咖啡。",
        "這個程式需要修改一下，把函數的參數從字串改成數字。",
        "我們下週三開會討論新專案的進度，請大家準備好資料。",
        "語音辨識的準確度取決於麥克風品質和環境噪音的控制。",
        "台灣的夜市小吃非常有名，臭豆腐和珍珠奶茶是必吃的。",
        "請幫我查一下這個 API 的文件，看看有沒有支援批次處理。",
        "明天早上九點有一個線上會議，記得提前測試一下網路連線。",
    ]

    def _get_test_passage(self):
        import random
        return random.choice(self._TEST_PASSAGES)

    def _refresh_passage(self):
        self._read_passage.configure(state="normal")
        self._read_passage.delete("1.0", "end")
        self._read_passage.insert("1.0", self._get_test_passage())
        self._read_passage.configure(state="disabled")
        self._read_result_label.configure(text="", text_color=DIM)

    def _toggle_read_test(self):
        if self._read_test_active:
            self._stop_read_test()
        else:
            self._start_read_test()

    def _start_read_test(self):
        self._read_test_active = True
        self._read_test_btn.configure(text="⏹ 停止朗讀", fg_color=RED)
        self._read_result_label.configure(text="請朗讀上方綠色文字…", text_color=ORANGE)
        threading.Thread(target=self._read_test_loop, daemon=True).start()

    def _stop_read_test(self):
        self._read_test_active = False
        self._read_test_btn.configure(text="🎙 開始朗讀測試", fg_color="#333")

    def _read_test_loop(self):
        import pyaudio, audioop, wave, io, tempfile
        CHUNK = 1024
        RATE  = 16000
        dev   = self._get_selected_mic_index()

        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                             input=True, input_device_index=dev,
                             frames_per_buffer=CHUNK)
        except Exception as e:
            self.after(0, lambda: self._read_result_label.configure(
                text=f"麥克風錯誤：{e}", text_color=RED))
            self._read_test_active = False
            return

        frames = []
        rms_values = []
        start_t = time.time()
        max_secs = 15  # 最長 15 秒

        while self._read_test_active and (time.time() - start_t) < max_secs:
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                rms = audioop.rms(data, 2)
                rms_values.append(rms)
                elapsed = time.time() - start_t
                self.after(0, lambda e=elapsed, r=rms: self._read_result_label.configure(
                    text=f"錄音中… {e:.1f}s  RMS: {r}",
                    text_color=ORANGE))
                time.sleep(0.02)
            except Exception:
                break

        stream.stop_stream()
        stream.close()
        pa.terminate()

        self._read_test_active = False
        self.after(0, lambda: self._read_test_btn.configure(
            text="🎙 開始朗讀測試", fg_color="#333"))

        if not frames:
            self.after(0, lambda: self._read_result_label.configure(
                text="未錄到音訊", text_color=RED))
            return

        # 組裝 WAV
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(RATE)
            wf.writeframes(b"".join(frames))
        wav_bytes = wav_buf.getvalue()

        # 送 Groq 辨識
        self.after(0, lambda: self._read_result_label.configure(
            text="辨識中…", text_color=ORANGE))

        try:
            from groq import Groq
            cfg = self.config_data
            client = Groq(api_key=cfg.get("groq_api_key", ""))
            result = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=("audio.wav", wav_bytes, "audio/wav"),
                language="zh",
                prompt="台灣國語，繁體中文。",
                response_format="text",
            )
            recognized = (result if isinstance(result, str) else getattr(result, 'text', '')).strip()
        except Exception as e:
            self.after(0, lambda: self._read_result_label.configure(
                text=f"辨識失敗：{str(e)[:40]}", text_color=RED))
            return

        # 比對原文
        original = self._read_passage.get("1.0", "end").strip()
        score, detail = self._calc_match_score(original, recognized)
        avg_rms = sum(rms_values) // max(len(rms_values), 1)
        thr = self._thr_var.get()

        if score >= 90:
            grade = "🟢 優秀"
            color = ACCENT
        elif score >= 70:
            grade = "🟡 良好"
            color = ORANGE
        else:
            grade = "🔴 偏差"
            color = RED

        report = (
            f"{grade}  匹配度 {score}%  |  平均RMS: {avg_rms}  閾值: {thr}\n"
            f"原文：{original}\n"
            f"辨識：{recognized}\n"
            f"{detail}"
        )
        self.after(0, lambda: self._read_result_label.configure(
            text=report, text_color=color))

    @staticmethod
    def _calc_match_score(original: str, recognized: str) -> tuple:
        """計算兩段文字的字元匹配度（0-100）"""
        import re
        # 移除標點和空白，只比較有意義的字
        clean = lambda s: re.sub(r'[，。！？、；：\u201c\u201d\u2018\u2019（）\s,.\-!?;:\'"()\[\]{}]', '', s)
        orig_chars = list(clean(original))
        reco_chars = list(clean(recognized))

        if not orig_chars:
            return 0, "原文為空"

        # 用 LCS（最長公共子序列）計算匹配
        m, n = len(orig_chars), len(reco_chars)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if orig_chars[i-1] == reco_chars[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])

        lcs_len = dp[m][n]
        score = round(lcs_len / m * 100)

        missed = m - lcs_len
        extra = n - lcs_len
        parts = []
        if missed > 0:
            parts.append(f"漏字 {missed}")
        if extra > 0:
            parts.append(f"多字 {extra}")
        detail = "  ".join(parts) if parts else "完全匹配"

        return score, detail

    # ── 歷史紀錄 ─────────────────────────────────────────────────────────────
    def _build_history(self):
        page = ctk.CTkFrame(self._main, fg_color=BG, corner_radius=0)

        # 標題列
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(20, 2))
        ctk.CTkLabel(hdr, text="歷史紀錄", font=FONT_TITLE,
                     text_color=TEXT).pack(side="left")
        ctk.CTkButton(hdr, text="🔄 重建詞庫",
                      fg_color=INPUT, hover_color="#3a3a3a",
                      text_color=TEXT,
                      font=FONT_SMALL, corner_radius=8, height=30, width=100,
                      command=self._rebuild_vocab).pack(side="right")
        self._hist_count_label = ctk.CTkLabel(hdr, text="",
                                               font=FONT_SMALL, text_color=DIM)
        self._hist_count_label.pack(side="right", padx=10)

        # 操作 + 分頁列（先 pack，讓 expand=True 的表格不把它擠走）
        foot = ctk.CTkFrame(page, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=(4, 10), side="bottom")

        # 表格
        frame = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=16, pady=(2, 0))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("H.Treeview",
                        background=CARD, foreground=TEXT,
                        fieldbackground=CARD,
                        font=("Microsoft YaHei", 12),
                        rowheight=36)
        style.configure("H.Treeview.Heading",
                        background="#2e2e2e", foreground=ACCENT,
                        font=("Microsoft YaHei", 12, "bold"))
        style.map("H.Treeview", background=[("selected", ACCENT)])

        cols = ("時間", "語言", "文字", "字數")
        self._hist_tree = ttk.Treeview(frame, columns=cols,
                                        show="headings", style="H.Treeview",
                                        selectmode="browse")
        for col, w in zip(cols, [168, 85, 0, 70]):
            self._hist_tree.heading(col, text=col)
            self._hist_tree.column(col, width=w, anchor="w",
                                   stretch=(col == "文字"))
        self._hist_tree.bind("<Double-1>", lambda e: self._edit_entry())

        vsb = ttk.Scrollbar(frame, orient="vertical",
                             command=self._hist_tree.yview)
        self._hist_tree.configure(yscrollcommand=vsb.set)
        self._hist_tree.pack(side="left", fill="both", expand=True, padx=(12,0), pady=12)
        vsb.pack(side="right", fill="y", pady=12, padx=(0,8))

        ctk.CTkButton(foot, text="✏  修正", width=90,
                      fg_color=INPUT, hover_color=ACCENT2,
                      text_color=TEXT, font=FONT_BODY,
                      corner_radius=8, height=34,
                      command=self._edit_entry).pack(side="left", padx=(0, 8))
        ctk.CTkButton(foot, text="🗑  刪除", width=90,
                      fg_color=INPUT, hover_color=RED,
                      text_color=TEXT, font=FONT_BODY,
                      corner_radius=8, height=34,
                      command=self._delete_entry).pack(side="left", padx=(0, 24))

        # 分頁控制（靠右）
        ctk.CTkButton(foot, text="下一頁 ›", width=90,
                      fg_color=INPUT, hover_color="#3a3a3a",
                      text_color=TEXT, font=FONT_BODY,
                      corner_radius=8, height=34,
                      command=self._hist_next).pack(side="right")
        self._hist_page_label = ctk.CTkLabel(foot, text="第 1 / 1 頁",
                                              font=FONT_BODY, text_color=DIM)
        self._hist_page_label.pack(side="right", padx=10)
        ctk.CTkButton(foot, text="‹ 上一頁", width=90,
                      fg_color=INPUT, hover_color="#3a3a3a",
                      text_color=TEXT, font=FONT_BODY,
                      corner_radius=8, height=34,
                      command=self._hist_prev).pack(side="right")

        return page

    # ── 語音日記 ─────────────────────────────────────────────────────────────
    def _build_diary(self):
        page = ctk.CTkFrame(self._main, fg_color=BG, corner_radius=0)

        ctk.CTkLabel(page, text="語音日記", font=FONT_TITLE,
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(20, 2))
        ctk.CTkLabel(page, text="每次語音輸入自動分類 · 每晚 22:00 生成當日摘要",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=20, pady=(0, 10))

        ctrl = ctk.CTkFrame(page, fg_color="transparent")
        ctrl.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(ctrl, text="日期：", font=FONT_BODY,
                     text_color=DIM).pack(side="left")
        self._diary_date = ctk.CTkEntry(ctrl, width=120, font=FONT_MONO,
                                         fg_color=INPUT,
                                         placeholder_text="YYYY-MM-DD")
        self._diary_date.insert(0, datetime.date.today().isoformat())
        self._diary_date.pack(side="left", padx=(4, 10))
        ctk.CTkButton(ctrl, text="載入", width=70,
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=self._refresh_diary).pack(side="left", padx=(0, 12))
        ctk.CTkButton(ctrl, text="⚡ 生成今日摘要", width=160,
                      fg_color=INPUT, hover_color="#3a3a3a",
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=self._generate_summary).pack(side="left")

        tab_frame = ctk.CTkFrame(page, fg_color="transparent")
        tab_frame.pack(fill="x", padx=16, pady=(0, 6))
        self._diary_cat = ctk.StringVar(value="all")
        self._diary_tabs = {}
        for cat, icon, label in [
            ("all",     "📋", "全部"),
            ("work",    "💼", "工作"),
            ("life",    "🌿", "生活"),
            ("finance", "💰", "財務"),
            ("misc",    "📝", "雜記"),
            ("summary", "✨", "摘要"),
        ]:
            btn = ctk.CTkButton(
                tab_frame, text=f"{icon} {label}",
                fg_color=ACCENT if cat == "all" else INPUT,
                hover_color=ACCENT2 if cat == "all" else "#3a3a3a",
                text_color="white",
                font=FONT_SMALL, corner_radius=8,
                width=82, height=32,
                command=lambda c=cat: self._switch_diary_tab(c))
            btn.pack(side="left", padx=(0, 6))
            self._diary_tabs[cat] = btn

        self._diary_box = ctk.CTkTextbox(page, fg_color=CARD,
                                          font=FONT_BODY,
                                          text_color=TEXT,
                                          corner_radius=12,
                                          state="disabled", wrap="word")
        self._diary_box.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        return page

    # ── 字典 ─────────────────────────────────────────────────────────────────
    def _build_vocab(self):
        page = ctk.CTkFrame(self._main, fg_color=BG, corner_radius=0)
        ctk.CTkLabel(page, text="智能字典", font=FONT_TITLE,
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(20, 2))
        ctk.CTkLabel(page, text="由每次語音輸入自動學習累積 · 支援手動新增/刪除/修改",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=20, pady=(0, 8))

        # 工具欄：新增詞彙
        toolbar = ctk.CTkFrame(page, fg_color="transparent")
        toolbar.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(toolbar, text="詞彙：", font=FONT_BODY,
                     text_color=DIM).pack(side="left")
        self._vocab_entry = ctk.CTkEntry(toolbar, width=160, font=FONT_BODY,
                                          fg_color=INPUT, placeholder_text="輸入新詞彙")
        self._vocab_entry.pack(side="left", padx=(0, 6))
        ctk.CTkButton(toolbar, text="+ 新增", width=70,
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_SMALL, corner_radius=8, height=30,
                      command=self._add_vocab_word).pack(side="left", padx=(0, 4))
        ctk.CTkButton(toolbar, text="修改", width=60,
                      fg_color=INPUT, hover_color="#3a3a3a", text_color=TEXT,
                      font=FONT_SMALL, corner_radius=8, height=30,
                      command=self._edit_vocab_word).pack(side="left", padx=(0, 4))
        ctk.CTkButton(toolbar, text="刪除", width=60,
                      fg_color=INPUT, hover_color=RED, text_color=TEXT,
                      font=FONT_SMALL, corner_radius=8, height=30,
                      command=self._del_vocab_word).pack(side="left")
        self._vocab_count_label = ctk.CTkLabel(toolbar, text="",
                                                font=FONT_SMALL, text_color=DIM)
        self._vocab_count_label.pack(side="right")

        # 詞彙 Treeview
        vocab_frame = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        vocab_frame.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        style = ttk.Style()
        style.configure("V.Treeview",
                        background=CARD, foreground=TEXT,
                        fieldbackground=CARD,
                        font=("Microsoft YaHei", 12),
                        rowheight=32)
        style.configure("V.Treeview.Heading",
                        background="#2e2e2e", foreground=ACCENT,
                        font=("Microsoft YaHei", 12, "bold"))
        style.map("V.Treeview", background=[("selected", ACCENT)])

        vcols = ("詞彙", "頻次")
        self._vocab_tree = ttk.Treeview(vocab_frame, columns=vcols,
                                         show="headings", style="V.Treeview",
                                         selectmode="browse")
        self._vocab_tree.heading("詞彙", text="詞彙")
        self._vocab_tree.heading("頻次", text="頻次")
        self._vocab_tree.column("詞彙", width=300, anchor="w", stretch=True)
        self._vocab_tree.column("頻次", width=80, anchor="center", stretch=False)

        vsb = ttk.Scrollbar(vocab_frame, orient="vertical",
                             command=self._vocab_tree.yview)
        self._vocab_tree.configure(yscrollcommand=vsb.set)
        self._vocab_tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=10)
        vsb.pack(side="right", fill="y", padx=(0, 4), pady=10)

        # 糾正映射區
        ctk.CTkLabel(page, text="糾正映射（聽到 → 改成）",
                     font=FONT_HEAD, text_color=TEXT).pack(anchor="w", padx=20, pady=(4, 4))

        corr_toolbar = ctk.CTkFrame(page, fg_color="transparent")
        corr_toolbar.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(corr_toolbar, text="聽到：", font=FONT_SMALL,
                     text_color=DIM).pack(side="left")
        self._corr_from = ctk.CTkEntry(corr_toolbar, width=120, font=FONT_BODY,
                                        fg_color=INPUT, placeholder_text="錯誤詞")
        self._corr_from.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(corr_toolbar, text="→", font=FONT_BODY,
                     text_color=DIM).pack(side="left", padx=4)
        self._corr_to = ctk.CTkEntry(corr_toolbar, width=120, font=FONT_BODY,
                                      fg_color=INPUT, placeholder_text="正確詞")
        self._corr_to.pack(side="left", padx=(0, 6))
        ctk.CTkButton(corr_toolbar, text="+ 新增", width=70,
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_SMALL, corner_radius=8, height=30,
                      command=self._add_correction).pack(side="left", padx=(0, 4))
        ctk.CTkButton(corr_toolbar, text="刪除", width=60,
                      fg_color=INPUT, hover_color=RED, text_color=TEXT,
                      font=FONT_SMALL, corner_radius=8, height=30,
                      command=self._del_correction).pack(side="left")

        corr_frame = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        corr_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        style.configure("C.Treeview",
                        background=CARD, foreground=TEXT,
                        fieldbackground=CARD,
                        font=("Microsoft YaHei", 12),
                        rowheight=32)
        style.configure("C.Treeview.Heading",
                        background="#2e2e2e", foreground=ACCENT,
                        font=("Microsoft YaHei", 12, "bold"))
        style.map("C.Treeview", background=[("selected", ACCENT)])

        ccols = ("聽到", "改成")
        self._corr_tree = ttk.Treeview(corr_frame, columns=ccols,
                                        show="headings", style="C.Treeview",
                                        selectmode="browse", height=5)
        self._corr_tree.heading("聽到", text="聽到")
        self._corr_tree.heading("改成", text="改成")
        self._corr_tree.column("聽到", width=200, anchor="w", stretch=True)
        self._corr_tree.column("改成", width=200, anchor="w", stretch=True)

        csb = ttk.Scrollbar(corr_frame, orient="vertical",
                             command=self._corr_tree.yview)
        self._corr_tree.configure(yscrollcommand=csb.set)
        self._corr_tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=8)
        csb.pack(side="right", fill="y", padx=(0, 4), pady=8)

        return page

    def _add_vocab_word(self):
        word = self._vocab_entry.get().strip()
        if not word:
            return
        try:
            data = json.loads(DICT_FILE.read_text(encoding="utf-8")) if DICT_FILE.exists() else {"words": {}}
            data.setdefault("words", {})[word] = data.get("words", {}).get(word, 0) + 1
            DICT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            # 同步到 vocabulary.json custom_words
            vocab_file = CONFIG_DIR / "vocabulary.json"
            if vocab_file.exists():
                vdata = json.loads(vocab_file.read_text(encoding="utf-8"))
                cw = vdata.get("custom_words", [])
                if word not in cw:
                    cw.append(word)
                    vdata["custom_words"] = cw
                    vocab_file.write_text(json.dumps(vdata, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._vocab_entry.delete(0, "end")
        self._refresh_vocab()

    def _del_vocab_word(self):
        sel = self._vocab_tree.selection()
        if not sel:
            return
        word = self._vocab_tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("刪除詞彙", f"確定刪除「{word}」？"):
            return
        try:
            data = json.loads(DICT_FILE.read_text(encoding="utf-8"))
            data.get("words", {}).pop(word, None)
            DICT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._refresh_vocab()

    def _edit_vocab_word(self):
        sel = self._vocab_tree.selection()
        if not sel:
            return
        old_word, count_str = self._vocab_tree.item(sel[0], "values")
        dlg = ctk.CTkToplevel(self)
        dlg.title("修改詞彙")
        dlg.geometry("350x150")
        dlg.transient(self)
        dlg.grab_set()
        ctk.CTkLabel(dlg, text="修改詞彙：", font=FONT_BODY).pack(padx=14, pady=(14, 4))
        entry = ctk.CTkEntry(dlg, width=280, font=FONT_BODY, fg_color=INPUT)
        entry.insert(0, old_word)
        entry.pack(padx=14, pady=4)
        def _save():
            new_word = entry.get().strip()
            if new_word and new_word != old_word:
                try:
                    data = json.loads(DICT_FILE.read_text(encoding="utf-8"))
                    words = data.get("words", {})
                    cnt = words.pop(old_word, 0)
                    words[new_word] = cnt
                    DICT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            dlg.destroy()
            self._refresh_vocab()
        ctk.CTkButton(dlg, text="儲存", fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_BODY, corner_radius=8, height=32,
                      command=_save).pack(pady=10)

    def _add_correction(self):
        frm = self._corr_from.get().strip()
        to = self._corr_to.get().strip()
        if not frm or not to:
            return
        try:
            vocab_file = CONFIG_DIR / "vocabulary.json"
            vdata = json.loads(vocab_file.read_text(encoding="utf-8")) if vocab_file.exists() else {}
            corr = vdata.get("corrections", {})
            corr[frm] = to
            vdata["corrections"] = corr
            vocab_file.write_text(json.dumps(vdata, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._corr_from.delete(0, "end")
        self._corr_to.delete(0, "end")
        self._refresh_vocab()

    def _del_correction(self):
        sel = self._corr_tree.selection()
        if not sel:
            return
        frm = self._corr_tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("刪除糾正", f"確定刪除「{frm}」的糾正規則？"):
            return
        try:
            vocab_file = CONFIG_DIR / "vocabulary.json"
            vdata = json.loads(vocab_file.read_text(encoding="utf-8"))
            vdata.get("corrections", {}).pop(frm, None)
            vocab_file.write_text(json.dumps(vdata, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._refresh_vocab()

    # ── 設定 ─────────────────────────────────────────────────────────────────
    def _build_settings(self):
        page = ctk.CTkFrame(self._main, fg_color=BG, corner_radius=0)
        ctk.CTkLabel(page, text="設定", font=FONT_TITLE,
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(20, 10))

        scroll = ctk.CTkScrollableFrame(page, fg_color="transparent",
                                         corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # API Keys
        api_card = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=12)
        api_card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(api_card, text="API 金鑰", font=FONT_HEAD,
                     text_color=TEXT).pack(anchor="w", padx=18, pady=(16, 10))
        for lbl, key in [("Groq API Key",   "groq_api_key"),
                          ("GLM API Key",    "glm_api_key"),
                          ("Gemini API Key", "gemini_api_key"),
                          ("OpenAI API Key", "api_key")]:
            v = self.config_data.get(key, "")
            disp = v[:10] + "·····" + v[-4:] if len(v) > 14 else (v or "（未設定）")
            row = ctk.CTkFrame(api_card, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=5)
            ctk.CTkLabel(row, text=lbl, font=FONT_BODY,
                         text_color=DIM, width=140, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=disp, font=FONT_MONO,
                         text_color=TEXT).pack(side="left")

        ctk.CTkFrame(api_card, height=1, fg_color="#333").pack(fill="x", padx=18, pady=10)

        # 熱鍵
        hk_row = ctk.CTkFrame(api_card, fg_color="transparent")
        hk_row.pack(fill="x", padx=18, pady=5)
        ctk.CTkLabel(hk_row, text="熱鍵", font=FONT_BODY,
                     text_color=DIM, width=140, anchor="w").pack(side="left")
        self._hotkey_entry = ctk.CTkEntry(hk_row, width=210, font=FONT_BODY,
                                           fg_color=INPUT)
        self._hotkey_entry.insert(0, self.config_data.get("hotkey", "right shift"))
        self._hotkey_entry.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(hk_row, text="例: right shift / ctrl+alt+r",
                     font=FONT_SMALL, text_color=DIM).pack(side="left")

        # 開機自啟
        as_row = ctk.CTkFrame(api_card, fg_color="transparent")
        as_row.pack(fill="x", padx=18, pady=5)
        ctk.CTkLabel(as_row, text="開機自動啟動", font=FONT_BODY,
                     text_color=DIM, width=140, anchor="w").pack(side="left")
        self._autostart = ctk.CTkSwitch(as_row, text="",
                                         progress_color=ACCENT,
                                         button_color="white")
        if self.config_data.get("auto_start", False):
            self._autostart.select()
        self._autostart.pack(side="left")

        # LLM 潤色
        lp_row = ctk.CTkFrame(api_card, fg_color="transparent")
        lp_row.pack(fill="x", padx=18, pady=5)
        ctk.CTkLabel(lp_row, text="AI 自動潤色", font=FONT_BODY,
                     text_color=DIM, width=140, anchor="w").pack(side="left")
        self._llm_polish = ctk.CTkSwitch(lp_row, text="",
                                          progress_color=ACCENT,
                                          button_color="white")
        if self.config_data.get("llm_polish", True):
            self._llm_polish.select()
        self._llm_polish.pack(side="left")

        ctk.CTkButton(api_card, text="儲存所有設定",
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_BODY, corner_radius=8, height=38,
                      command=self._save_all).pack(anchor="w", padx=18, pady=(10, 18))

        # 視窗語言規則
        lang_card = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=12)
        lang_card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(lang_card, text="🌐  視窗語言規則", font=FONT_HEAD,
                     text_color=TEXT).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(lang_card,
                     text="按下熱鍵的瞬間偵測前景視窗，自動切換繁體 / 簡體",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=18, pady=(0, 10))

        tree_frame = ctk.CTkFrame(lang_card, fg_color=INPUT, corner_radius=8)
        tree_frame.pack(fill="x", padx=18, pady=(0, 8))
        style2 = ttk.Style()
        style2.configure("L.Treeview",
                         background=INPUT, foreground=TEXT,
                         fieldbackground=INPUT,
                         font=("Microsoft YaHei", 12), rowheight=28)
        style2.configure("L.Treeview.Heading",
                         background="#222222", foreground=ACCENT,
                         font=("Microsoft YaHei", 12, "bold"))
        style2.map("L.Treeview", background=[("selected", ACCENT)])
        cols2 = ("視窗進程 / 關鍵字", "輸出語言")
        self._rules_tree = ttk.Treeview(tree_frame, columns=cols2,
                                         show="headings", style="L.Treeview",
                                         height=7)
        self._rules_tree.heading("視窗進程 / 關鍵字", text="視窗進程 / 關鍵字")
        self._rules_tree.heading("輸出語言",           text="輸出語言")
        self._rules_tree.column("視窗進程 / 關鍵字", width=320, anchor="w")
        self._rules_tree.column("輸出語言",           width=200, anchor="center")
        vsb2 = ttk.Scrollbar(tree_frame, orient="vertical",
                              command=self._rules_tree.yview)
        self._rules_tree.configure(yscrollcommand=vsb2.set)
        self._rules_tree.pack(side="left", fill="x", expand=True,
                               padx=(8, 0), pady=8)
        vsb2.pack(side="right", fill="y", pady=8, padx=(0, 4))
        self._load_rules_table()

        add_row = ctk.CTkFrame(lang_card, fg_color="transparent")
        add_row.pack(fill="x", padx=18, pady=(0, 6))
        ctk.CTkLabel(add_row, text="進程名稱", font=FONT_BODY,
                     text_color=DIM).pack(side="left")
        self._rule_proc = ctk.CTkEntry(add_row, width=160, font=FONT_BODY,
                                        fg_color=INPUT,
                                        placeholder_text="WeChat / Notion ...")
        self._rule_proc.pack(side="left", padx=(8, 12))
        self._rule_lang = ctk.StringVar(value="zh-TW")
        ctk.CTkOptionMenu(add_row, values=["zh-TW","zh-CN","en","ja"],
                          variable=self._rule_lang,
                          fg_color=INPUT, button_color=ACCENT,
                          font=FONT_BODY, width=130).pack(side="left", padx=(0, 10))
        ctk.CTkButton(add_row, text="＋ 新增", width=90,
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=self._add_rule).pack(side="left", padx=(0, 8))
        ctk.CTkButton(add_row, text="－ 刪除", width=90,
                      fg_color=INPUT, hover_color=RED,
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=self._del_rule).pack(side="left")

        ctk.CTkLabel(lang_card,
                     text="✎ 亮綠色 = 自訂規則（可刪）  |  灰色 = 內建預設  |  藍色 = Chrome 標題規則",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=18, pady=(0, 16))

        return page

    # ── 即時狀態輪詢 ─────────────────────────────────────────────────────────
    def _start_status_poll(self):
        self._poll_status()

    def _poll_status(self):
        try:
            s = read_status()
            state = s.get("state", "idle")
            if state == "recording":
                self._status_dot.configure(text="🔴 錄音中", text_color="#ff5555")
                if hasattr(self, "_status_card_label"):
                    self._status_card_label.configure(text="錄音中", text_color="#ff5555")
            elif state == "processing":
                self._status_dot.configure(text="⏳ 識別中", text_color=ORANGE)
                if hasattr(self, "_status_card_label"):
                    self._status_card_label.configure(text="識別中", text_color=ORANGE)
            elif state == "done":
                self._status_dot.configure(text="✓ 完成", text_color=ACCENT)
                if hasattr(self, "_status_card_label"):
                    self._status_card_label.configure(text="完成", text_color=ACCENT)
            else:
                self._status_dot.configure(text="● 待機中", text_color=DIM)
                if hasattr(self, "_status_card_label"):
                    self._status_card_label.configure(text="待機中", text_color=ACCENT)
        except Exception:
            pass
        # 檢查信號文件（dictation 叫我顯示視窗）
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
        self._stop_mic_meter()
        self.withdraw()

    def show_window(self):
        self.deiconify()
        self.after(100, lambda: (self.lift(), self.focus_force()))

    # ── 資料刷新 ─────────────────────────────────────────────────────────────
    def _refresh_recent(self):
        self._recent_box.configure(state="normal")
        self._recent_box.delete("1.0", "end")
        try:
            if LOG_FILE.exists():
                lines = [l for l in LOG_FILE.read_text(encoding="utf-8").splitlines()
                         if l.strip()]
                for line in reversed(lines[-5:]):
                    r    = json.loads(line)
                    ts   = r.get("ts", "")[:16].replace("T", " ")
                    text = r.get("text", "")
                    self._recent_box.insert("end", f"{ts}\n")
                    self._recent_box.insert("end",
                        f"{text[:120]}{'…' if len(text)>120 else ''}\n\n")
        except Exception:
            self._recent_box.insert("end", "（尚無歷史紀錄）")
        self._recent_box.configure(state="disabled")

    def _refresh_history(self):
        """讀取全部歷史，倒序存入 _hist_data，重設到第 0 頁"""
        self._hist_data = []
        try:
            if LOG_FILE.exists():
                lines = [l for l in LOG_FILE.read_text(
                    encoding="utf-8").splitlines() if l.strip()]
                for line in reversed(lines):
                    try:
                        self._hist_data.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass
        self._hist_page = 0
        total = len(self._hist_data)
        self._hist_count_label.configure(text=f"共 {total} 筆")
        self._hist_render_page()

    def _hist_render_page(self):
        """把目前頁面的資料渲染到 Treeview"""
        for item in self._hist_tree.get_children():
            self._hist_tree.delete(item)
        ps    = self._HIST_PAGE_SIZE
        total = len(self._hist_data)
        pages = max(1, (total + ps - 1) // ps)
        start = self._hist_page * ps
        end   = min(start + ps, total)
        for r in self._hist_data[start:end]:
            ts   = r.get("ts","")[:19].replace("T"," ")
            lang = r.get("lang","")
            text = r.get("text","")
            chars = r.get("chars", len(text))
            self._hist_tree.insert("", "end",
                iid=r.get("ts",""),   # 用 ts 作唯一 iid
                values=(ts, lang, text, chars))
        self._hist_page_label.configure(
            text=f"第 {self._hist_page+1} / {pages} 頁")

    def _hist_prev(self):
        if self._hist_page > 0:
            self._hist_page -= 1
            self._hist_render_page()

    def _hist_next(self):
        ps    = self._HIST_PAGE_SIZE
        total = len(self._hist_data)
        pages = max(1, (total + ps - 1) // ps)
        if self._hist_page < pages - 1:
            self._hist_page += 1
            self._hist_render_page()

    def _get_selected_record(self):
        """返回目前選取行的 dict，或 None"""
        sel = self._hist_tree.selection()
        if not sel:
            messagebox.showwarning("快打 SmarType", "請先選取一筆紀錄")
            return None
        ts = sel[0]
        for r in self._hist_data:
            if r.get("ts","") == ts:
                return r
        return None

    def _edit_entry(self):
        """彈出修正視窗，讓用戶修改文字"""
        r = self._get_selected_record()
        if r is None:
            return
        dlg = ctk.CTkToplevel(self)
        dlg.title("修正紀錄")
        dlg.geometry("640x280")
        dlg.configure(fg_color=BG)
        dlg.grab_set()
        dlg.resizable(True, False)

        ts = r.get("ts","")[:19].replace("T"," ")
        ctk.CTkLabel(dlg, text=f"修正  {ts}", font=FONT_HEAD,
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 8))
        txt = ctk.CTkTextbox(dlg, font=FONT_BODY, fg_color=INPUT,
                              text_color=TEXT, height=120, wrap="word")
        txt.insert("1.0", r.get("text",""))
        txt.pack(fill="x", padx=20, pady=(0, 12))
        txt.focus()

        def _save():
            new_text = txt.get("1.0","end").strip()
            if not new_text:
                messagebox.showwarning("快打 SmarType", "文字不能為空")
                return
            r["text"]  = new_text
            r["chars"] = len(new_text)
            self._save_history_data()
            self._refresh_history()
            dlg.destroy()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(anchor="e", padx=20, pady=(0, 16))
        ctk.CTkButton(btn_row, text="儲存", width=90,
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=_save).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="取消", width=90,
                      fg_color=INPUT, hover_color="#3a3a3a",
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=dlg.destroy).pack(side="left")

    def _delete_entry(self):
        r = self._get_selected_record()
        if r is None:
            return
        ts   = r.get("ts","")[:19].replace("T"," ")
        text = r.get("text","")[:30]
        if not messagebox.askyesno("快打 SmarType",
                f"確定刪除這筆紀錄？\n{ts}  {text}…"):
            return
        self._hist_data.remove(r)
        self._save_history_data()
        total = len(self._hist_data)
        self._hist_count_label.configure(text=f"共 {total} 筆")
        # 調整頁碼避免越界
        ps    = self._HIST_PAGE_SIZE
        pages = max(1, (total + ps - 1) // ps)
        if self._hist_page >= pages:
            self._hist_page = pages - 1
        self._hist_render_page()

    def _save_history_data(self):
        """把 _hist_data（倒序）寫回 history.jsonl（正序）"""
        try:
            lines = [json.dumps(r, ensure_ascii=False) for r in reversed(self._hist_data)]
            LOG_FILE.write_text("\n".join(lines) + ("\n" if lines else ""),
                                encoding="utf-8")
        except Exception as e:
            messagebox.showerror("快打 SmarType", f"儲存失敗：{e}")

    def _rebuild_vocab(self):
        """從目前 history.jsonl 重建 smart_dict.json，過濾掉已刪除/已修正的紀錄"""
        if not messagebox.askyesno("快打 SmarType",
                "重建詞庫將清除舊詞庫，並從現有歷史重新統計高頻詞。\n確定繼續？"):
            return
        import re
        word_count: dict = {}
        for r in self._hist_data:
            text = r.get("text", "")
            # 提取中文詞（2-6字）和英文詞
            for w in re.findall(r'[\u4e00-\u9fff]{2,6}|[A-Za-z]{3,}', text):
                word_count[w] = word_count.get(w, 0) + 1
        # 只保留出現 ≥2 次的詞
        word_count = {w: c for w, c in word_count.items() if c >= 2}
        try:
            DICT_FILE.write_text(
                json.dumps({"words": word_count}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            messagebox.showinfo("快打 SmarType",
                f"詞庫重建完成，共 {len(word_count)} 個有效詞彙（出現 ≥2 次）")
        except Exception as e:
            messagebox.showerror("快打 SmarType", f"重建失敗：{e}")

    def _refresh_vocab(self):
        # 刷新詞彙 Treeview
        for item in self._vocab_tree.get_children():
            self._vocab_tree.delete(item)
        try:
            if DICT_FILE.exists():
                data  = json.loads(DICT_FILE.read_text(encoding="utf-8"))
                words = sorted(data.get("words", {}).items(), key=lambda x: -x[1])
                self._vocab_count_label.configure(text=f"共 {len(words)} 個詞")
                for w, cnt in words:
                    self._vocab_tree.insert("", "end", values=(w, cnt))
        except Exception:
            pass
        # 刷新糾正映射 Treeview
        for item in self._corr_tree.get_children():
            self._corr_tree.delete(item)
        try:
            vocab_file = CONFIG_DIR / "vocabulary.json"
            if vocab_file.exists():
                vdata = json.loads(vocab_file.read_text(encoding="utf-8"))
                for frm, to in vdata.get("corrections", {}).items():
                    self._corr_tree.insert("", "end", values=(frm, to))
        except Exception:
            pass

    def _switch_diary_tab(self, cat):
        self._diary_cat.set(cat)
        for k, btn in self._diary_tabs.items():
            btn.configure(
                fg_color=ACCENT if k == cat else INPUT,
                hover_color=ACCENT2 if k == cat else "#3a3a3a")
        self._refresh_diary()

    def _refresh_diary(self):
        date     = self._diary_date.get().strip()
        cat_filt = self._diary_cat.get()
        self._diary_box.configure(state="normal")
        self._diary_box.delete("1.0", "end")

        if cat_filt == "summary":
            sf = DIARY_DIR / f"{date}_summary.md"
            if sf.exists():
                self._diary_box.insert("end", sf.read_text(encoding="utf-8"))
            else:
                self._diary_box.insert("end",
                    f"尚無 {date} 的摘要。\n點擊「⚡ 生成今日摘要」產生。")
            self._diary_box.configure(state="disabled")
            return

        diary_file = DIARY_DIR / f"{date}.jsonl"
        if not diary_file.exists():
            self._diary_box.insert("end",
                f"尚無 {date} 的語音日記。\n語音輸入後自動分類存入。")
            self._diary_box.configure(state="disabled")
            return

        cat_label = {"work":"💼 工作","life":"🌿 生活",
                     "finance":"💰 財務","misc":"📝 雜記"}
        scene_emoji = {"chat":"💬","coding":"💻","email":"📧",
                       "browser":"🌐","general":"📝"}
        by_cat = {"work":[],"life":[],"finance":[],"misc":[]}
        for line in diary_file.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                c = r.get("category","misc")
                if c in by_cat:
                    by_cat[c].append(r)
            except Exception:
                pass

        total = 0
        for cat, entries in by_cat.items():
            if cat_filt != "all" and cat != cat_filt:
                continue
            if not entries:
                continue
            self._diary_box.insert("end",
                f"{cat_label.get(cat,cat)}  ({len(entries)} 條)\n")
            for r in entries:
                ts      = r.get("ts","")[:16].replace("T"," ")
                text    = r.get("text","")
                raw     = r.get("raw","")
                contact = r.get("contact","")
                scene   = r.get("app_scene","")
                window  = r.get("window","")
                emoji   = scene_emoji.get(scene, "")

                # 組裝顯示行：[時間] 💬 對象（應用）— 內容
                prefix = f"  {ts[11:]}  "
                if contact:
                    app_hint = window.replace(".exe","") if window else ""
                    prefix += f"{emoji} {contact}"
                    if app_hint and app_hint.lower() not in contact.lower():
                        prefix += f"（{app_hint}）"
                    prefix += " — "
                elif window:
                    prefix += f"{emoji} {window.replace('.exe','')} — "

                self._diary_box.insert("end", f"{prefix}{text}\n")
                if raw and raw != text:
                    self._diary_box.insert("end",
                        f"    原始：{raw[:60]}{'…' if len(raw)>60 else ''}\n")
                total += 1
            self._diary_box.insert("end", "\n")

        if total == 0:
            self._diary_box.insert("end", "此分類今日尚無記錄。")
        self._diary_box.configure(state="disabled")

    def _generate_summary(self):
        date = self._diary_date.get().strip()
        self._diary_box.configure(state="normal")
        self._diary_box.delete("1.0", "end")
        self._diary_box.insert("end", f"正在生成 {date} 摘要，請稍候…")
        self._diary_box.configure(state="disabled")
        def _run():
            try:
                from diary_engine import generate_daily_summary
                generate_daily_summary(date)
                self.after(0, lambda: self._switch_diary_tab("summary"))
            except Exception as e:
                self.after(0, lambda: (
                    self._diary_box.configure(state="normal"),
                    self._diary_box.insert("end", f"\n錯誤：{e}"),
                    self._diary_box.configure(state="disabled")))
        threading.Thread(target=_run, daemon=True).start()

    # ── 語言規則 ─────────────────────────────────────────────────────────────
    def _load_rules_table(self):
        for item in self._rules_tree.get_children():
            self._rules_tree.delete(item)
        try:
            from window_detector import DEFAULT_APP_RULES, BROWSER_TITLE_RULES
        except ImportError:
            DEFAULT_APP_RULES, BROWSER_TITLE_RULES = {}, {}
        custom = {}
        try:
            if RULES_FILE.exists():
                custom = json.loads(RULES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        ll = {"zh-TW":"TW 繁體中文","zh-CN":"CN 簡體中文",
              "en":"EN 英文","ja":"JA 日文"}
        for proc, lang in custom.items():
            self._rules_tree.insert("", "end", tags=("custom",),
                values=(proc, ll.get(lang, lang) + "  ✎"))
        shown = set(k.lower() for k in custom)
        for proc, lang in sorted(DEFAULT_APP_RULES.items()):
            if proc.lower() not in shown:
                self._rules_tree.insert("", "end", tags=("builtin",),
                    values=(proc, ll.get(lang, lang)))
        for kw, lang in sorted(BROWSER_TITLE_RULES.items()):
            self._rules_tree.insert("", "end", tags=("browser",),
                values=(f"[Chrome標題] {kw}", ll.get(lang, lang)))
        self._rules_tree.tag_configure("custom",  foreground="#7de8c0")
        self._rules_tree.tag_configure("builtin", foreground=DIM)
        self._rules_tree.tag_configure("browser", foreground="#7ab8e8")

    def _add_rule(self):
        proc = self._rule_proc.get().strip()
        lang = self._rule_lang.get()
        if not proc:
            messagebox.showwarning("快打 SmarType", "請輸入視窗進程名稱")
            return
        try:
            rules = json.loads(RULES_FILE.read_text(encoding="utf-8")) \
                    if RULES_FILE.exists() else {}
            rules[proc] = lang
            RULES_FILE.write_text(json.dumps(rules, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
            self._load_rules_table()
            self._rule_proc.delete(0, "end")
            messagebox.showinfo("快打 SmarType", f"已新增：{proc} → {lang}，立即生效")
        except Exception as e:
            messagebox.showerror("快打 SmarType", f"儲存失敗：{e}")

    def _del_rule(self):
        sel = self._rules_tree.selection()
        if not sel:
            messagebox.showwarning("快打 SmarType", "請先選取要刪除的規則")
            return
        item = self._rules_tree.item(sel[0])
        if "builtin" in item["tags"] or "browser" in item["tags"]:
            messagebox.showinfo("快打 SmarType",
                "內建規則無法刪除。若要覆蓋，請新增同名規則。")
            return
        proc = item["values"][0].replace("  ✎", "")
        try:
            rules = json.loads(RULES_FILE.read_text(encoding="utf-8")) \
                    if RULES_FILE.exists() else {}
            rules.pop(proc, None)
            RULES_FILE.write_text(json.dumps(rules, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
            self._load_rules_table()
        except Exception as e:
            messagebox.showerror("快打 SmarType", f"刪除失敗：{e}")

    # ── 儲存設定 ─────────────────────────────────────────────────────────────
    def _save_quick(self):
        cfg = load_config()
        cfg["energy_thr"]   = self._thr_var.get()
        cfg["default_lang"] = self._lang_var.get()
        mic_list = get_mic_list()
        for idx, name in mic_list.items():
            if name == self._mic_var.get():
                cfg["mic_index"] = idx
                break
        save_config(cfg)
        self.config_data = cfg
        messagebox.showinfo("快打 SmarType", "設定已儲存，重啟 SmarType 後完全生效")

    def _save_all(self):
        cfg = load_config()
        cfg["hotkey"]     = self._hotkey_entry.get().strip()
        cfg["auto_start"] = bool(self._autostart.get())
        cfg["llm_polish"] = bool(self._llm_polish.get())
        save_config(cfg)
        self.config_data = cfg
        messagebox.showinfo("快打 SmarType", "設定已儲存，重啟 SmarType 後完全生效")


# ── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import ctypes as _ct
    _mutex = _ct.windll.kernel32.CreateMutexW(None, True, "SmarType_Dashboard_v1")
    if _ct.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        # 已有實例在運行 → 寫信號讓它顯示，然後退出
        try:
            import json as _j
            SIGNAL_FILE.write_text(_j.dumps({"cmd": "show"}), encoding="utf-8")
        except Exception:
            pass
        sys.exit(0)
    app = Dashboard()
    app.mainloop()
