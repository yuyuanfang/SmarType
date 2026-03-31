"""
首頁 / 狀態總覽分頁
"""

import customtkinter as ctk
from tkinter import ttk, messagebox
import json, time, threading, re, random

from pathlib import Path

CONFIG_DIR  = Path(__file__).parent.parent / "userdata"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE    = CONFIG_DIR / "history.jsonl"

# ── 共用常數（從 dashboard 匯入）─────────────────────────────────────────────
ACCENT  = "#1D9E75"
ACCENT2 = "#17876A"
BG      = "#1a1a1a"
CARD    = "#242424"
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


def _load_config():
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def _get_stats():
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

def _get_mic_list():
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
                continue
            name = info["name"].strip()
            if not name:
                continue
            raw.append({"index": i, "name": name,
                        "default": i == default_idx, "rate": rate})
        seen, deduped = {}, []
        for m in raw:
            key = m["name"]
            if key in seen:
                if m["default"]:
                    deduped[seen[key]] = m
                continue
            seen[key] = len(deduped)
            deduped.append(m)
        deduped.sort(key=lambda m: (not m["default"], m["name"]))
        mics = {}
        for m in deduped:
            prefix = "★ " if m["default"] else ""
            mics[m["index"]] = f"[{m['index']}] {prefix}{m['name'][:36]}"
        pa.terminate()
        return mics
    except Exception:
        return {}


class TabHome(ctk.CTkFrame):
    def __init__(self, parent, dashboard):
        super().__init__(parent, fg_color=BG, corner_radius=0)
        self.dashboard = dashboard
        self.config_data = dashboard.config_data
        self._mic_meter_active = False
        self._mic_stream = None
        self._mic_pa     = None
        self._read_test_active = False
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 0))
        ctk.CTkLabel(header, text="自然說話，快速成文",
                     font=FONT_TITLE, text_color=TEXT,
                     anchor="w").pack(side="left")

        cfg = self.config_data
        hk  = cfg.get("hotkey", "right shift").upper()
        ctk.CTkLabel(self,
                     text=f"熱鍵：{hk}（按住說話，放開停止）  ·  自動偵測前景視窗語言",
                     font=FONT_SMALL, text_color=DIM,
                     anchor="w").pack(anchor="w", padx=20, pady=(2, 12))

        chars, sessions = _get_stats()
        card_row = ctk.CTkFrame(self, fg_color="transparent")
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

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="both", expand=True, padx=16, pady=8)
        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(0, weight=1)

        # 左：麥克風設定
        left = ctk.CTkFrame(bottom, fg_color=CARD, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ctk.CTkLabel(left, text="輸入設定", font=FONT_HEAD,
                     text_color=TEXT).pack(anchor="w", padx=14, pady=(12, 8))

        mic_list = _get_mic_list()
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

        sep = ctk.CTkFrame(left, fg_color="#333", height=1)
        sep.pack(fill="x", padx=14, pady=(8, 6))

        ctk.CTkLabel(left, text="麥克風靈敏度校準",
                     font=("Microsoft YaHei", 11, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=14, pady=(0, 2))
        ctk.CTkLabel(left,
                     text="閾值越低=越靈敏（容易誤觸）  閾值越高=越穩定（需要更大聲）",
                     font=FONT_SMALL, text_color=DIM,
                     justify="left").pack(anchor="w", padx=14, pady=(0, 6))

        meter_frame = ctk.CTkFrame(left, fg_color=INPUT, corner_radius=8)
        meter_frame.pack(fill="x", padx=14, pady=(0, 4))

        meter_top = ctk.CTkFrame(meter_frame, fg_color="transparent")
        meter_top.pack(fill="x", padx=8, pady=(6, 2))
        self._mic_test_btn = ctk.CTkButton(meter_top, text="\U0001f3a4 測試麥克風",
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

        ctk.CTkLabel(left,
                     text="「建議閾值」= 環境噪音 RMS \u00d7 2",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=14, pady=(0, 2))

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkButton(btn_row, text="\u26a1 自動校準",
                      fg_color=INPUT, hover_color="#3a3a3a",
                      text_color=TEXT,
                      font=FONT_BODY, corner_radius=8, height=30,
                      command=self._auto_calibrate).pack(side="left", padx=(0, 6))
        self._calibrate_label = ctk.CTkLabel(btn_row, text="",
                                              font=FONT_SMALL, text_color=DIM)
        self._calibrate_label.pack(side="left")

        # 朗讀校準
        read_card = ctk.CTkFrame(left, fg_color=INPUT, corner_radius=8)
        read_card.pack(fill="x", padx=14, pady=(6, 4))

        ctk.CTkLabel(read_card, text="\U0001f4d6 朗讀校準",
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
            read_btn_row, text="\U0001f399 開始朗讀測試",
            fg_color="#333", hover_color="#444",
            text_color=TEXT, font=FONT_BODY,
            corner_radius=8, height=30,
            command=self._toggle_read_test)
        self._read_test_btn.pack(side="left", padx=(0, 6))
        ctk.CTkButton(read_btn_row, text="\U0001f504", width=30,
                      fg_color="#333", hover_color="#444",
                      text_color=DIM, font=FONT_BODY,
                      corner_radius=8, height=30,
                      command=self._refresh_passage).pack(side="left")

        self._read_result_label = ctk.CTkLabel(read_card, text="",
                                                font=FONT_SMALL, text_color=DIM,
                                                wraplength=360, justify="left")
        self._read_result_label.pack(anchor="w", padx=10, pady=(0, 8))

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

    # ── 麥克風電平表 ─────────────────────────────────────────────────────────
    def _get_selected_mic_index(self):
        mic_list = _get_mic_list()
        sel = self._mic_var.get()
        for idx, name in mic_list.items():
            if name == sel:
                return idx
        return self.config_data.get("mic_index", 1)

    def _toggle_mic_meter(self):
        if self._mic_meter_active:
            self._stop_mic_meter()
            self._mic_test_btn.configure(text="\U0001f3a4 測試麥克風", fg_color="#333")
            self._rms_label.configure(text="已停止", text_color=DIM)
        else:
            self._start_mic_meter()
            self._mic_test_btn.configure(text="\u23f9 停止測試", fg_color=RED)

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
        self._mic_test_btn.configure(text="\u23f9 停止測試", fg_color=RED)

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
                text="麥克風錯誤", text_color=RED))
            self._mic_meter_active = False
            return

        while self._mic_meter_active:
            if time.time() - self._mic_meter_start > 15:
                self.after(0, lambda: (
                    self._mic_test_btn.configure(text="\U0001f3a4 測試麥克風", fg_color="#333"),
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
                rms_copy, fill_copy, color_copy, thr_copy = rms, fill, color, thr
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
        self._read_test_btn.configure(text="\u23f9 停止朗讀", fg_color=RED)
        self._read_result_label.configure(text="請朗讀上方綠色文字…", text_color=ORANGE)
        threading.Thread(target=self._read_test_loop, daemon=True).start()

    def _stop_read_test(self):
        self._read_test_active = False
        self._read_test_btn.configure(text="\U0001f399 開始朗讀測試", fg_color="#333")

    def _read_test_loop(self):
        import pyaudio, audioop, wave, io
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
        max_secs = 15

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
            text="\U0001f399 開始朗讀測試", fg_color="#333"))

        if not frames:
            self.after(0, lambda: self._read_result_label.configure(
                text="未錄到音訊", text_color=RED))
            return

        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(RATE)
            wf.writeframes(b"".join(frames))
        wav_bytes = wav_buf.getvalue()

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

        original = self._read_passage.get("1.0", "end").strip()
        score, detail = self._calc_match_score(original, recognized)
        avg_rms = sum(rms_values) // max(len(rms_values), 1)
        thr = self._thr_var.get()

        if score >= 90:
            grade, color = "\U0001f7e2 優秀", ACCENT
        elif score >= 70:
            grade, color = "\U0001f7e1 良好", ORANGE
        else:
            grade, color = "\U0001f534 偏差", RED

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
        clean = lambda s: re.sub(r'[，。！？、；：\u201c\u201d\u2018\u2019（）\s,.\-!?;:\'"()\[\]{}]', '', s)
        orig_chars = list(clean(original))
        reco_chars = list(clean(recognized))
        if not orig_chars:
            return 0, "原文為空"
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

    # ── 資料刷新 ─────────────────────────────────────────────────────────────
    def refresh_recent(self):
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

    def _save_quick(self):
        cfg = _load_config()
        cfg["energy_thr"]   = self._thr_var.get()
        cfg["default_lang"] = self._lang_var.get()
        mic_list = _get_mic_list()
        for idx, name in mic_list.items():
            if name == self._mic_var.get():
                cfg["mic_index"] = idx
                break
        _save_config(cfg)
        self.config_data = cfg
        self.dashboard.config_data = cfg
        messagebox.showinfo("快打 SmarType", "設定已儲存，重啟 SmarType 後完全生效")
