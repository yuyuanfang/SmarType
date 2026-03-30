"""
快打 SmarType v6
- Groq Whisper Large v3 Turbo（超快转录）
- 分段实时转录 + 圆球跑马灯边说边出字
- 屏幕正中微信样式绿球
- 管理员权限 + 修复右 Shift 冲突
"""

import os, sys, json, time, wave, tempfile, threading, datetime, ctypes, io, traceback
from pathlib import Path
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as Item
import tkinter as tk

import pyaudio
import pyperclip
import keyboard
import pyautogui

from window_detector import get_active_window_info, get_language_label
from smart_vocab import run_background_update, get_prompt_words
from converter import convert
from diary_engine import context_aware_post_process

# ── Groq 客户端 ───────────────────────────────────────────────────────────────
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# ── 路径 ──────────────────────────────────────────────────────────────────────
CONFIG_DIR  = Path(__file__).parent / "userdata"
CONFIG_FILE = CONFIG_DIR / "config.json"
VOCAB_FILE  = CONFIG_DIR / "vocabulary.json"
LOG_FILE    = CONFIG_DIR / "history.jsonl"

DEFAULT_CONFIG = {
    "api_key":       "",         # OpenAI（备用）
    "groq_api_key":  "",         # Groq（主力）
    "hotkey":        "right shift",
    "language":      "zh",
    "insert_method": "clipboard",
    "auto_lang":     True,
    "default_lang":  "zh-TW",
    "mic_index":     None,
    "auto_start":    False,
    "segment_secs":  3,          # 分段转录间隔（秒）
    "llm_polish":    False,      # 是否啟用 LLM 潤色（去贅字+糾錯），需 OpenAI/Gemini key
    "gemini_api_key": "",        # Gemini API key（備用）
}

SAMPLE_RATE = 16000
CHANNELS    = 1
CHUNK       = 1024
FORMAT      = pyaudio.paInt16


# ── 管理员权限 ────────────────────────────────────────────────────────────────

def disable_sticky_keys():
    try:
        import winreg
        # 禁用粘滞键
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Control Panel\Accessibility\StickyKeys",
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "Flags", 0, winreg.REG_SZ, "58")
        winreg.CloseKey(key)
        # 禁用筛选键（按住 Shift 8秒触发）
        key2 = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                              r"Control Panel\Accessibility\Keyboard Response",
                              0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key2, "Flags", 0, winreg.REG_SZ, "122")
        winreg.CloseKey(key2)
        # 禁用切换键
        key3 = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                              r"Control Panel\Accessibility\ToggleKeys",
                              0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key3, "Flags", 0, winreg.REG_SZ, "58")
        winreg.CloseKey(key3)
    except Exception:
        pass


def set_autostart(enable):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, "SmarType", 0, winreg.REG_SZ,
                              f'"{sys.executable}" "{Path(__file__).resolve()}"')
        else:
            try:
                winreg.DeleteValue(key, "SmarType")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


# ── 调试日志（写文件，因控制台窗口已被隐藏）────────────────────────────────
DEBUG_LOG     = Path(__file__).parent / "userdata" / "debug.log"
DEBUG_LOG_MAX = 5 * 1024 * 1024  # 5 MB → 輪替

def _dbg(msg: str):
    """写调试日志到 userdata/debug.log（超過 5MB 自動輪替）"""
    try:
        DEBUG_LOG.parent.mkdir(exist_ok=True)
        if DEBUG_LOG.exists() and DEBUG_LOG.stat().st_size > DEBUG_LOG_MAX:
            bak = DEBUG_LOG.with_suffix(".log.bak")
            if bak.exists():
                bak.unlink()
            DEBUG_LOG.rename(bak)
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ── 配置 ──────────────────────────────────────────────────────────────────────
def load_config():
    CONFIG_DIR.mkdir(exist_ok=True)
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── 词汇数据库 ────────────────────────────────────────────────────────────────
class VocabularyDB:
    def __init__(self):
        CONFIG_DIR.mkdir(exist_ok=True)
        if VOCAB_FILE.exists():
            with open(VOCAB_FILE, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            self.data = {"custom_words": [], "corrections": {},
                         "session_count": 0, "total_chars": 0}
            self._save()

    def _save(self):
        with open(VOCAB_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def apply_corrections(self, text):
        for w, c in self.data["corrections"].items():
            text = text.replace(w, c)
        return text

    def get_prompt(self, lang, context=""):
        if lang in ("zh-TW", "en"):
            base = "台灣國語，繁體中文，程式開發與技術討論，專有名詞保留英文。"
        elif lang == "zh-CN":
            base = "简体中文，技术讨论，专有名词保留英文。"
        else:
            base = ""
        parts = [base] if base else []
        # ★ 修复：Groq Whisper prompt 上限 224 tokens (~150 汉字)
        #   只取少量高频词，不加剪贴板/历史上下文（太长会报 400 错误）
        prompt_words = get_prompt_words(10)   # 最多10个词
        if prompt_words:
            parts.append(f"詞：{prompt_words}。")
        prompt = "".join(parts)
        # 硬截断：确保不超过 120 字符（约 80 tokens，安全边界）
        return prompt[:120]

    def log_session(self, text, lang, window):
        self.data["session_count"] = self.data.get("session_count", 0) + 1
        self.data["total_chars"]   = self.data.get("total_chars", 0) + len(text)
        self._save()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(),
                "text": text, "lang": lang,
                "window": window, "chars": len(text),
            }, ensure_ascii=False) + "\n")


# ── 录音器（支持分段回调）────────────────────────────────────────────────────
class Recorder:
    def __init__(self, mic_index=None):
        self.pa         = pyaudio.PyAudio()
        self.frames     = []
        self.recording  = False
        self.stream     = None
        self.mic_index  = mic_index
        self.on_pcm     = None  # 每幀 PCM 回調 fn(bytes)，用於串流 ASR

    def set_mic(self, index):
        self.mic_index = index

    def start(self, on_pcm=None):
        self.frames    = []
        self.recording = True
        self.on_pcm    = on_pcm

        kwargs = dict(format=FORMAT, channels=CHANNELS, rate=SAMPLE_RATE,
                      input=True, frames_per_buffer=CHUNK,
                      stream_callback=self._callback)
        if self.mic_index is not None:
            kwargs["input_device_index"] = self.mic_index
        self.stream = self.pa.open(**kwargs)
        self.stream.start_stream()

    def _callback(self, in_data, frame_count, time_info, status):
        if self.recording:
            self.frames.append(in_data)
            # ★ 每幀音頻直接送串流 ASR（Sherpa-ONNX 在此線程內同步處理）
            if self.on_pcm:
                try:
                    self.on_pcm(in_data)
                except Exception:
                    pass
        return (None, pyaudio.paContinue)

    def _frames_to_wav(self, frames) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.pa.get_sample_size(FORMAT))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()

    def stop(self) -> bytes | None:
        """停止录音，返回完整音频的 WAV bytes"""
        self.recording = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        # ★ 最短 0.8 秒才送识别（约 12 帧），防止极短按键产生幻觉文字
        if len(self.frames) < 12:
            _dbg(f"stop: frames={len(self.frames)} < 12, too short")
            return None
        return self._frames_to_wav(self.frames)

    def cleanup(self):
        self.pa.terminate()


def list_microphones():
    pa = pyaudio.PyAudio()
    mics, default_idx = [], -1
    try:
        default_idx = pa.get_default_input_device_info().get("index", -1)
    except Exception:
        pass
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("maxInputChannels", 0) > 0:
            mics.append({"index": i, "name": info["name"],
                         "default": i == default_idx})
    pa.terminate()
    return mics


def inject_text(text, method="clipboard"):
    if not text:
        return
    if method == "clipboard":
        try:
            original = pyperclip.paste()
        except Exception:
            original = ""
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
        def restore():
            time.sleep(0.5)
            try:
                pyperclip.copy(original)
            except Exception:
                pass
        threading.Thread(target=restore, daemon=True).start()


def get_chat_context():
    """
    从剪贴板获取上下文，提取关键词给 Whisper 提升准确度
    """
    try:
        text = pyperclip.paste()
        if not text or len(text) < 5:
            return ""
        # 取最后 300 字作为上下文
        context = text[-300:].strip()
        return context
    except Exception:
        pass
    return ""


def load_history_context() -> str:
    """
    从本地历史记录中提取最近 10 条的关键词，
    作为 Whisper prompt 的补充上下文
    """
    try:
        if not LOG_FILE.exists():
            return ""
        lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
        recent = lines[-10:]  # 最近10条
        texts = []
        for line in recent:
            try:
                r = json.loads(line)
                texts.append(r.get("text", ""))
            except Exception:
                pass
        combined = " ".join(texts)
        # 只取最后 200 字
        return combined[-200:] if len(combined) > 200 else combined
    except Exception:
        return ""


# ── 托盘图标 ──────────────────────────────────────────────────────────────────
def make_tray_icon(state="ready"):
    size  = 64
    img   = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(img)
    color = {"ready": "#555555", "recording": "#1D9E75",
             "processing": "#d4a017", "done": "#1D9E75"}.get(state, "#555555")
    draw.ellipse([4, 4, 60, 60], fill=color)
    draw.rounded_rectangle([24, 12, 40, 36], radius=8, fill="white")
    draw.arc([16, 28, 48, 52], start=0, end=180, fill="white", width=3)
    draw.line([32, 52, 32, 58], fill="white", width=3)
    draw.line([24, 58, 40, 58], fill="white", width=3)
    return img


# ── 底部居中胶囊条（对齐竞品 UI）────────────────────────────────────────────
class CenterBall:
    """
    固定寬度膠囊條（仿微信輸入法），屏幕底部居中。
    Sherpa-ONNX 串流辨識逐字送入 → 跑馬燈即時更新。
    """
    W, H = 480, 56

    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#010101")
        self.root.configure(bg="#010101")

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - self.W) // 2
        y  = sh - self.H - 60
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.root, width=self.W, height=self.H,
            bg="#010101", highlightthickness=0)
        self.canvas.pack()

        # ── 胶囊背景（圆角矩形）────────────────────────────────────────────
        r   = self.H // 2 - 2
        pad = 2
        W, H = self.W, self.H
        self.canvas.create_arc(
            pad, pad, pad + 2*r, H - pad,
            start=90, extent=180, fill="#1D9E75", outline="")
        self.canvas.create_arc(
            W - pad - 2*r, pad, W - pad, H - pad,
            start=270, extent=180, fill="#1D9E75", outline="")
        self.canvas.create_rectangle(
            pad + r, pad, W - pad - r, H - pad,
            fill="#1D9E75", outline="")

        # ── 左侧麦克风圆点 ─────────────────────────────────────────────────
        dot_cx = r + 6
        dot_cy = H // 2
        self._dot = self.canvas.create_oval(
            dot_cx - 11, dot_cy - 11,
            dot_cx + 11, dot_cy + 11,
            fill="white", outline="")
        self._dot_icon = self.canvas.create_text(
            dot_cx, dot_cy,
            text="🎙", font=("Segoe UI Emoji", 13), fill="#1D9E75")

        # ── 实时文字（胶囊右侧，支持平滑滾動）────────────────────────────
        self._txt_x0   = dot_cx + 22          # 文字起始 x
        self._txt_xmax = W - 16               # 文字區域右邊界
        self._txt_font = ("Microsoft YaHei", 13)

        self._live_txt = self.canvas.create_text(
            self._txt_x0, H // 2,
            text="", anchor="w",
            font=self._txt_font,
            fill="white")

        self._pulse_job    = None
        self._pulse_toggle = True
        self._last_text    = ""       # 已顯示在畫布上的文字
        self._scroll_job   = None     # 滾動動畫 job
        self._scroll_target_x = self._txt_x0  # 滾動目標 x
        self._typing_queue = []       # 待逐字顯示的字元佇列
        self._typing_job   = None     # 逐字動畫 job
        self._displayed_text = ""     # 畫布上目前顯示的文字（逐字累積）
        self._full_target  = ""       # 串流傳來的完整目標文字

        self.root.withdraw()

    # ── 公開方法 ──────────────────────────────────────────────────────────────
    def show_recording(self, lang: str):
        self._stop_pulse()
        self._cancel_scroll()
        self._cancel_typing()
        self._last_text = ""
        self._displayed_text = ""
        self._full_target = ""
        self._typing_queue = []
        self.canvas.itemconfig(self._dot_icon, text="🎙")
        self.canvas.itemconfig(
            self._live_txt,
            text=f"聆聽中... {get_language_label(lang)}")
        self.canvas.coords(self._live_txt, self._txt_x0, self.H // 2)
        self._start_pulse()
        self._show()

    def append_text(self, text: str):
        """串流辨識：文字立即更新，超出時勻速平滑滾動（微信風格）"""
        if not text:
            return
        self._last_text = text
        self._full_target = text
        self._displayed_text = text

        # 立即更新文字內容（不做逐字延遲）
        self.canvas.itemconfig(self._live_txt, text=text)
        self.canvas.update_idletasks()

        # 計算是否需要滾動
        bbox = self.canvas.bbox(self._live_txt)
        if not bbox:
            return
        text_width = bbox[2] - bbox[0]
        available  = self._txt_xmax - self._txt_x0

        if text_width > available:
            overflow = text_width - available
            self._scroll_target_x = self._txt_x0 - overflow
            if not self._scroll_job:
                self._tick_scroll()
        else:
            # 文字未超出，確保在起始位置
            self.canvas.coords(self._live_txt, self._txt_x0, self.H // 2)

    def _cancel_typing(self):
        pass  # 已移除逐字動畫，保留介面相容

    def _cancel_scroll(self):
        if self._scroll_job:
            self.root.after_cancel(self._scroll_job)
            self._scroll_job = None

    def _tick_scroll(self):
        """勻速滾動：固定每幀移動 2px，視覺上穩定不跳動"""
        coords = self.canvas.coords(self._live_txt)
        if not coords:
            self._scroll_job = None
            return
        cur_x = coords[0]
        target = self._scroll_target_x
        diff = target - cur_x

        if abs(diff) < 1:
            self.canvas.coords(self._live_txt, target, self.H // 2)
            self._scroll_job = None
            return

        # 勻速移動：每幀固定 2px，方向跟隨 diff
        speed = 2.0
        if diff < 0:
            new_x = max(cur_x - speed, target)
        else:
            new_x = min(cur_x + speed, target)
        self.canvas.coords(self._live_txt, new_x, self.H // 2)
        self._scroll_job = self.root.after(16, self._tick_scroll)  # ~60fps

    def show_processing(self):
        """放開按鍵，最終轉錄中"""
        self._stop_pulse()
        self._cancel_scroll()
        self._cancel_typing()
        self.canvas.itemconfig(self._dot_icon, text="⏳")
        hint = (self._last_text[-16:] + "  ⏳") if self._last_text else "識別中..."
        self.canvas.itemconfig(self._live_txt, text=hint)
        self.canvas.coords(self._live_txt, self._txt_x0, self.H // 2)

    def show_result(self, text: str, lang: str):
        self._stop_pulse()
        self._cancel_scroll()
        self._cancel_typing()
        self.canvas.itemconfig(self._dot_icon, text="✓")
        self.canvas.itemconfig(self._live_txt, text=text)
        self.canvas.coords(self._live_txt, self._txt_x0, self.H // 2)
        self.canvas.update_idletasks()
        # 如果最終文字也超出，平滑滾動到末尾
        bbox = self.canvas.bbox(self._live_txt)
        if bbox:
            text_width = bbox[2] - bbox[0]
            available  = self._txt_xmax - self._txt_x0
            if text_width > available:
                overflow = text_width - available
                self._scroll_target_x = self._txt_x0 - overflow
                if not self._scroll_job:
                    self._tick_scroll()
        self.root.after(2500, self._hide)

    def show_error(self, msg: str = "識別失敗，請查看 debug.log"):
        self._stop_pulse()
        self.canvas.itemconfig(self._dot_icon, text="❌")
        self.canvas.itemconfig(self._live_txt, text=msg)
        self.root.after(3000, self._hide)

    def hide(self):
        self._hide()

    # ── 脈衝動畫 ──────────────────────────────────────────────────────────────
    def _start_pulse(self):
        self._pulse_toggle = True
        self._tick_pulse()

    def _tick_pulse(self):
        color = "white" if self._pulse_toggle else "#88ccaa"
        self.canvas.itemconfig(self._dot, fill=color)
        self._pulse_toggle = not self._pulse_toggle
        self._pulse_job = self.root.after(500, self._tick_pulse)

    def _stop_pulse(self):
        if self._pulse_job:
            self.root.after_cancel(self._pulse_job)
            self._pulse_job = None
        self.canvas.itemconfig(self._dot, fill="white")

    def _show(self):
        self.root.deiconify()
        self.root.lift()

    def _hide(self):
        self._stop_pulse()
        self.root.withdraw()

    # ── 線程安全方法 ───────────────────────────────────────────────────────────
    def safe_show_recording(self, lang):
        self.root.after(0, self.show_recording, lang)

    def safe_show_processing(self):
        self.root.after(0, self.show_processing)

    def safe_show_result(self, text, lang):
        self.root.after(0, self.show_result, text, lang)

    def safe_hide(self):
        self.root.after(0, self._hide)

    def safe_show_error(self, msg="識別失敗，請查看 debug.log"):
        self.root.after(0, self.show_error, msg)

    def safe_append(self, text):
        self.root.after(0, self.append_text, text)

    def update(self):
        pass  # mainloop handles events now


# ── 麦克风选择 ────────────────────────────────────────────────────────────────
def show_mic_selector(current_index, on_select):
    mics = list_microphones()
    if not mics:
        return
    win = tk.Tk()
    win.title("选择麦克风 · 快打 SmarType")
    win.configure(bg="#1a1a1a")
    win.attributes("-topmost", True)
    win.resizable(False, False)
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"420x160+{(sw-420)//2}+{(sh-160)//2}")

    tk.Label(win, text="选择录音麦克风",
             font=("Microsoft YaHei", 12, "bold"),
             fg="#fff", bg="#1a1a1a").pack(pady=(14, 6))

    names = [f"{'★ ' if m['default'] else ''}{m['name'][:45]}" for m in mics]
    var   = tk.StringVar(value=names[0])
    if current_index is not None:
        for i, m in enumerate(mics):
            if m["index"] == current_index:
                var.set(names[i])
                break

    opt = tk.OptionMenu(win, var, *names)
    opt.config(bg="#2a2a2a", fg="#fff", activebackground="#333",
               highlightthickness=0, font=("Microsoft YaHei", 10))
    opt["menu"].config(bg="#2a2a2a", fg="#fff", font=("Microsoft YaHei", 10))
    opt.pack(fill=tk.X, padx=20, pady=4)

    def confirm():
        idx = names.index(var.get())
        on_select(mics[idx]["index"])
        win.destroy()

    tk.Button(win, text="确认", command=confirm,
              bg="#1D9E75", fg="#fff",
              font=("Microsoft YaHei", 10),
              relief="flat", padx=20, pady=4).pack(pady=6)
    win.mainloop()


# ── Groq 转录 ─────────────────────────────────────────────────────────────────
class Transcriber:
    def __init__(self, groq_key="", openai_key="", gemini_key=""):
        self.groq_client   = Groq(api_key=groq_key) if groq_key and GROQ_AVAILABLE else None
        valid_oai = openai_key and openai_key.startswith("sk-") and OPENAI_AVAILABLE
        self.openai_client = OpenAI(api_key=openai_key) if valid_oai else None
        # ── Gemini 音頻轉錄（多模態，台灣腔更準）──
        self.gemini_client = None
        if gemini_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=gemini_key)
            except ImportError:
                pass
        # ★ API 状态追踪（供托盘菜单显示）
        self.last_model    = "--"     # 最后成功使用的模型
        self.last_error    = None     # None / "rate_limit" / "auth" / "network"
        self.last_success  = None     # 最后成功时间字符串
        _dbg(f"Transcriber init: groq={'OK' if self.groq_client else 'MISSING'}, "
             f"gemini={'OK' if self.gemini_client else 'MISSING'}, "
             f"openai={'OK' if self.openai_client else 'MISSING/INVALID'}")

    def transcribe(self, wav_bytes: bytes, prompt: str = "",
                   use_local: bool = False, lang: str = "zh") -> str:
        """
        轉錄優先順序：
          local=True  → 本地 faster-whisper（離線）
          local=False → Gemini（最準）→ Groq（快速備援）→ OpenAI → 本地
        """
        if use_local:
            return self._local_transcribe(wav_bytes, prompt)
        # ★ Gemini 音頻轉錄（多模態，台灣腔最準）
        if self.gemini_client:
            result = self._gemini_transcribe(wav_bytes, lang)
            if result:
                return result
        if self.groq_client:
            result = self._groq_transcribe(wav_bytes, prompt)
            if result:
                return result
        if self.openai_client:
            result = self._openai_transcribe(wav_bytes, prompt)
            if result:
                return result
        _dbg("cloud transcribe all failed, falling back to local model")
        return self._local_transcribe(wav_bytes, prompt)

    def _local_transcribe(self, wav_bytes: bytes, prompt: str) -> str:
        try:
            from local_transcriber import transcribe_local
            text = transcribe_local(wav_bytes, language="zh", prompt=prompt[:120])
            if text:
                self.last_model   = "local-medium"
                self.last_success = datetime.datetime.now().strftime("%H:%M:%S")
                self.last_error   = None
            return text
        except Exception as e:
            _dbg(f"local_transcribe error: {e}")
            return ""

    def _groq_transcribe(self, wav_bytes: bytes, prompt: str) -> str:
        # ★ 安全截断 prompt，Groq 上限 224 tokens
        safe_prompt = (prompt or "台灣繁體中文。")[:120]
        _dbg(f"Groq call: wav={len(wav_bytes)}B, prompt={repr(safe_prompt[:40])}")

        self.last_error = None
        # 尝试顺序：turbo（最快）→ large-v3（备用）→ OpenAI
        models = ["whisper-large-v3-turbo", "whisper-large-v3"]
        for model in models:
            try:
                t0 = time.time()
                result = self.groq_client.audio.transcriptions.create(
                    model=model,
                    file=("audio.wav", wav_bytes, "audio/wav"),
                    language="zh",
                    prompt=safe_prompt,
                    response_format="text",
                )
                elapsed = round((time.time() - t0) * 1000)
                text = (result if isinstance(result, str) else getattr(result, 'text', '') or '').strip()
                _dbg(f"Groq [{model}] {elapsed}ms: {repr(text[:60]) if text else 'EMPTY'}")
                if text:
                    self.last_model   = model
                    self.last_success = datetime.datetime.now().strftime("%H:%M:%S")
                    self.last_error   = None
                    return text
                _dbg(f"Groq [{model}] empty result, trying next...")
            except Exception as e:
                err_name = type(e).__name__
                _dbg(f"Groq [{model}] {err_name}: {e}")
                # ★ 识别额度耗尽（429 Rate Limit）
                if "429" in str(e) or "rate_limit" in str(e).lower() or "RateLimitError" in err_name:
                    self.last_error = "rate_limit"
                    _dbg("RATE LIMITED — stopping Groq attempts")
                    break  # 额度耗尽时不继续尝试其他 Groq 模型
                elif "401" in str(e) or "auth" in str(e).lower():
                    self.last_error = "auth"
                else:
                    self.last_error = "network"

        # 所有 Groq 模型失败，尝试 OpenAI
        _dbg(f"All Groq models failed (last_error={self.last_error}), trying OpenAI")
        if self.openai_client:
            return self._openai_transcribe(wav_bytes, safe_prompt)
        return ""

    def _gemini_transcribe(self, wav_bytes: bytes, lang: str = "zh") -> str:
        """Gemini 2.5 Flash 多模態音頻轉錄 — 台灣國語最準"""
        try:
            from google.genai import types
            t0 = time.time()

            if lang in ("zh-TW", "zh"):
                lang_hint = "繁體中文（台灣國語）"
            elif lang == "zh-CN":
                lang_hint = "简体中文"
            else:
                lang_hint = "中文"

            resp = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(parts=[
                        types.Part(inline_data=types.Blob(
                            mime_type="audio/wav", data=wav_bytes)),
                        types.Part(text=(
                            f"請將這段語音精確轉錄為{lang_hint}文字。"
                            "保留原始語句，不要改寫、不要摘要、不要添加內容。"
                            "專有名詞和英文保持原樣。"
                            "只輸出轉錄的文字，不要其他任何內容。"
                            "如果沒有語音內容，回覆空字串。"
                        )),
                    ])
                ],
            )
            elapsed = round((time.time() - t0) * 1000)
            text = (resp.text or "").strip()
            # 過濾掉 Gemini 回傳的「無語音」類回覆
            if text in ("（無語音）", "(無語音)", "（没有语音）", "", "空"):
                _dbg(f"Gemini [2.5-flash] {elapsed}ms: no speech detected")
                return ""
            _dbg(f"Gemini [2.5-flash] {elapsed}ms: {repr(text[:60])}")
            if text:
                self.last_model   = "gemini-2.5-flash"
                self.last_success = datetime.datetime.now().strftime("%H:%M:%S")
                self.last_error   = None
            return text
        except Exception as e:
            _dbg(f"Gemini transcribe error: {e}")
            return ""

    def _openai_transcribe(self, wav_bytes: bytes, prompt: str) -> str:
        try:
            buf = io.BytesIO(wav_bytes)
            buf.name = "audio.wav"
            result = self.openai_client.audio.transcriptions.create(
                model="whisper-1", file=buf,
                language="zh", prompt=prompt,
                response_format="text",
            )
            return (result if isinstance(result, str) else "").strip()
        except Exception as e:
            _dbg(f"OpenAI error: {e}")
            return ""


# ── 主应用 ────────────────────────────────────────────────────────────────────
class SmarTypeApp:
    def __init__(self):
        self.config       = load_config()
        self.vocab        = VocabularyDB()
        self.recorder     = Recorder(mic_index=self.config.get("mic_index"))
        self.is_recording = False
        self.last_window  = {}
        self.ball         = CenterBall()
        self.tray         = None
        self._seg_texts   = []   # 分段转录结果列表
        self._processing  = False  # 防止并行 process 线程重复注入
        self._press_guard   = threading.Lock()   # 防止 on_press 双重触发（键盘重复事件）
        self._release_guard = threading.Lock()   # 防止 on_release 双重触发

        self.transcriber = Transcriber(
            groq_key=self.config.get("groq_api_key", ""),
            openai_key=self.config.get("api_key", ""),
            gemini_key=self.config.get("gemini_api_key", ""),
        )

        disable_sticky_keys()

    # ── 托盘 ──────────────────────────────────────────────────────────────────
    def _api_status_label(self):
        """生成托盘显示的 API 状态字符串"""
        t = self.transcriber
        if t.last_error == "rate_limit":
            return "⚠️ Groq 額度已滿"
        if t.last_error == "auth":
            return "❌ API Key 錯誤"
        if t.last_success:
            short = t.last_model.replace("whisper-large-v3-", "")
            return f"✅ {short} · {t.last_success}"
        return "⏳ 尚未使用"

    def _build_menu(self):
        return pystray.Menu(
            Item(lambda _: f"快打 SmarType  ·  {self._api_status_label()}",
                 None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("🖥  顯示管理介面",  self._on_show_dashboard),
            pystray.Menu.SEPARATOR,
            Item("❌  退出",          self._on_quit),
        )

    _dashboard_proc = None

    def _on_show_dashboard(self, icon=None, item=None):
        import subprocess
        # 如果 dashboard 進程還在跑，直接寫信號讓它顯示
        if self._dashboard_proc and self._dashboard_proc.poll() is None:
            try:
                signal_file = Path(__file__).parent / "userdata" / "dashboard_signal.json"
                signal_file.write_text('{"cmd": "show"}', encoding="utf-8")
                _dbg("dashboard signal: show (already running)")
            except Exception:
                pass
            return
        # 否則啟動新的 dashboard
        self._dashboard_proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).parent / "dashboard.py")],
            creationflags=subprocess.CREATE_NO_WINDOW
            if sys.platform == "win32" else 0)
        _dbg(f"dashboard launched pid={self._dashboard_proc.pid}")

    def _update_tray(self, state="ready"):
        if self.tray:
            self.tray.icon = make_tray_icon(state)

    def _on_select_mic(self, icon, item):
        def on_select(index):
            self.config["mic_index"] = index
            save_config(self.config)
            self.recorder.set_mic(index)
        threading.Thread(
            target=show_mic_selector,
            args=(self.config.get("mic_index"), on_select),
            daemon=True).start()

    def _on_open_dashboard(self, icon, item):
        import subprocess
        subprocess.Popen([sys.executable,
                          str(Path(__file__).parent / "dashboard.py")])

    def _on_open_rules(self, icon, item):
        import subprocess
        subprocess.Popen([sys.executable,
                          str(Path(__file__).parent / "app_rules.py")],
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

    def _on_open_vocab(self, icon, item):
        import subprocess
        subprocess.Popen([sys.executable,
                          str(Path(__file__).parent / "vocab_manager.py")],
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

    def _on_toggle_autostart(self, icon, item):
        new_val = not self.config.get("auto_start", False)
        if set_autostart(new_val):
            self.config["auto_start"] = new_val
            save_config(self.config)
        self.tray.update_menu()

    def _on_view_history(self, icon, item):
        import subprocess
        subprocess.Popen([sys.executable,
                          str(Path(__file__).parent / "history_viewer.py")],
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

    def _on_smart_vocab(self, icon, item):
        import subprocess
        subprocess.Popen([sys.executable,
                          str(Path(__file__).parent / "smart_vocab.py")],
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

    def _on_quit(self, icon, item):
        self.recorder.cleanup()
        icon.stop()
        os._exit(0)

    # ── 幻覺過濾 ──────────────────────────────────────────────────────────────
    _BAD_PATTERNS = [
        "Charleston", "字幕志愿者", "字幕志願者", "詞・作曲", "詞·作曲",
        "李宗盛", "Subtitles by", "Amara.org", "翻訳者", "MBC", "KBS", "SBS",
    ]

    def _is_hallucination(self, text: str) -> bool:
        if not text or len(text.strip()) < 2:
            return False
        for pat in self._BAD_PATTERNS:
            if pat in text:
                _dbg(f"hallucination pattern: {pat!r}")
                return True
        words = text.replace("，", " ").replace(",", " ").replace("。", " ").split()
        if len(words) >= 4:
            unique = {w.strip(".,!?。！？、") for w in words}
            if len(unique) <= 2:
                _dbg(f"hallucination: repeated words in: {repr(text[:60])}")
                return True
        # ★ 同一個字連續重複（無空格），如「诚诚诚诚诚」
        import re
        clean = re.sub(r'[，。,.\s！？!?、]', '', text)
        if len(clean) >= 4:
            unique_chars = set(clean)
            if len(unique_chars) <= 2:
                _dbg(f"hallucination: repeated chars in: {repr(text[:60])}")
                return True
        return False

    # ── 串流 ASR 回調（每幀音頻觸發，逐字更新跑馬燈）─────────────────────────
    def _on_streaming_text(self, text: str):
        """Sherpa-ONNX 串流辨識有新文字時回調（從音頻線程）"""
        if not self.is_recording:
            return
        self.ball.safe_append(text)

    # ── 录音开始 ──────────────────────────────────────────────────────────────
    def on_press(self):
        # ★ 先检查 is_recording，再取锁，避免竞态条件
        if self.is_recording:
            return
        # ★ 防抖锁：500ms 内重复的 on_press 调用（键盘重复事件）直接忽略
        if not self._press_guard.acquire(blocking=False):
            _dbg("on_press: BLOCKED by press_guard (duplicate key event)")
            return
        def _unlock_press():
            time.sleep(0.5)
            try: self._press_guard.release()
            except RuntimeError: pass
        threading.Thread(target=_unlock_press, daemon=True).start()

        if self.is_recording:
            self._press_guard.release()
            return
        _dbg("on_press: recording started")
        self.is_recording = True
        self._seg_texts   = []
        self.last_window  = get_active_window_info()
        lang = self.last_window.get("lang", "zh-TW")

        self.ball.safe_show_recording(lang)
        self._update_tray("recording")
        self._write_status("recording", "")

        # ★ 建立串流 ASR session，每幀音頻直接送 Sherpa-ONNX
        try:
            from streaming_transcriber import StreamingSession
            self._streaming_session = StreamingSession(
                on_text=self._on_streaming_text)
            _dbg("streaming session created — Sherpa-ONNX 即時預覽")
        except Exception as e:
            self._streaming_session = None
            _dbg(f"streaming session failed: {e}")

        def _on_pcm(raw_bytes):
            if self._streaming_session:
                self._streaming_session.feed_pcm(raw_bytes)

        self.recorder.start(on_pcm=_on_pcm)

    # ── 录音结束 ──────────────────────────────────────────────────────────────
    def on_release(self):
        # ★ 防抖锁：500ms 内重复的 on_release 调用（键盘重复事件）直接忽略
        if not self._release_guard.acquire(blocking=False):
            _dbg("on_release: BLOCKED by release_guard (duplicate key event)")
            return
        def _unlock_release():
            time.sleep(0.5)
            try: self._release_guard.release()
            except RuntimeError: pass
        threading.Thread(target=_unlock_release, daemon=True).start()

        if not self.is_recording:
            return
        if self._processing:          # 若上一次还在处理中，直接忽略本次触发
            _dbg("on_release: BLOCKED by _processing=True, dropping this release")
            return
        _dbg("on_release: stopping recorder...")
        self.is_recording = False
        self._processing  = True      # 标记正在处理，阻止并行 process 线程
        self.ball.safe_show_processing()
        self._update_tray("processing")

        wav_bytes = self.recorder.stop()
        _dbg(f"on_release: recorder stopped, wav_bytes={'None' if wav_bytes is None else f'{len(wav_bytes)}B'}")

        def process():
            try:
                _dbg("=== process() START ===")
                target_lang = self.last_window.get(
                    "lang", self.config.get("default_lang", "zh-TW"))
                _dbg(f"target_lang={target_lang}")

                context = get_chat_context()
                history_ctx = load_history_context()
                full_context = (context + " " + history_ctx).strip()
                prompt  = self.vocab.get_prompt(target_lang, full_context)

                # 用完整音频做最终转录（最准确）
                final_text = ""
                if wav_bytes:
                    # ★ 送出前靜音檢測：防止靜音音頻送 Groq 產生幻覺文字
                    try:
                        import audioop
                        wav_audio = wav_bytes[44:]  # 跳過 44 bytes WAV header
                        rms = audioop.rms(wav_audio, 2) if len(wav_audio) > 0 else 0
                        thr = self.config.get("energy_thr", 80)
                        _dbg(f"pre-send RMS={rms} thr={thr}")
                        if rms < thr:
                            _dbg(f"RMS too low ({rms}<{thr}), skipping Groq (prevent hallucination)")
                            self.ball.safe_show_error("未偵測到語音，請靠近麥克風說話")
                            self._update_tray("ready")
                            return
                    except Exception as rms_e:
                        _dbg(f"RMS check error: {rms_e}")
                    _dbg(f"wav_bytes size={len(wav_bytes)} bytes, calling transcribe...")
                    try:
                        raw = self.transcriber.transcribe(wav_bytes, prompt, lang=target_lang)
                        _dbg(f"transcribe returned: {repr(raw[:80]) if raw else 'EMPTY'}")
                    except Exception as te:
                        _dbg(f"transcribe EXCEPTION: {te}\n{traceback.format_exc()}")
                        self.ball.safe_show_error(f"API錯誤: {str(te)[:30]}")
                        self._update_tray("ready")
                        return
                    if raw:
                        if self._is_hallucination(raw):
                            _dbg(f"hallucination detected in final transcription, discarding: {repr(raw[:60])}")
                            self.ball.safe_show_error("識別結果異常，請重新說話")
                            self._update_tray("ready")
                            return
                        raw        = self.vocab.apply_corrections(raw)
                        final_text = convert(raw, target_lang)
                        # ★ 上下文感知後處理（Typeless 風格）
                        #   所有語言都經過 LLM 糾錯；en 目標同時翻譯
                        need_post = (
                            (target_lang == "en" and any('\u4e00' <= c <= '\u9fff' for c in final_text))
                            or self.config.get("llm_polish", False)
                        )
                        if need_post:
                            try:
                                app_name = self.last_window.get("process", "")
                                win_title = self.last_window.get("title", "")
                                # 用剪貼簿 + 歷史作為對話上下文
                                recent_ctx = full_context
                                _dbg(f"post_process: {target_lang}, app={app_name}, ctx_len={len(recent_ctx)}")
                                final_text = context_aware_post_process(
                                    final_text,
                                    target_lang=target_lang,
                                    app_name=app_name,
                                    window_title=win_title,
                                    recent_context=recent_ctx,
                                )
                            except Exception as te:
                                _dbg(f"post_process error: {te}")
                        _dbg(f"final_text: {repr(final_text[:80])}")
                    else:
                        _dbg("transcribe returned empty — no speech detected?")
                else:
                    _dbg("wav_bytes is None — recording too short (<5 frames)")

                if not final_text:
                    err = self.transcriber.last_error
                    if wav_bytes is None:
                        _dbg("wav_bytes=None → 録音太短")
                        self.ball.safe_show_error("錄音太短，請按住說話再放開")
                    elif err == "rate_limit":
                        _dbg("rate_limit → show quota error")
                        self.ball.safe_show_error("Groq 額度已滿，請稍後再試")
                    elif err == "auth":
                        self.ball.safe_show_error("API Key 錯誤，請檢查設定")
                    else:
                        _dbg("final_text empty → 靜音或識別失敗")
                        self.ball.safe_show_error("未識別到語音，請重試")
                    self._update_tray("ready")
                    return

                self.ball.safe_show_result(final_text, target_lang)
                self._update_tray("done")

                # ★ 立即注入文字（不等 LLM）
                method = self.config.get("insert_method", "clipboard")
                _dbg(f"inject_text: method={method}")
                inject_text(final_text, method)
                _dbg("inject done")

                # ★ 背景寫日記（含交談對象、場景上下文）
                try:
                    from diary_engine import process_entry
                    process_entry(final_text, window_info=self.last_window)
                except Exception as de:
                    _dbg(f"diary process_entry error: {de}")

                self.vocab.log_session(
                    final_text, target_lang,
                    self.last_window.get("process", "unknown"))

                # ★ 关键修复：在 sleep 之前重置 _processing，
                #   否则 2.5s 显示期间用户按键会被拦截
                self._processing = False
                _dbg("_processing reset (before sleep)")
                self._write_status("done", final_text)

                # 后台静默更新智能词典
                threading.Thread(target=run_background_update, daemon=True).start()

                time.sleep(2.5)
                self._update_tray("ready")
                self._write_status("idle", "")
                _dbg("=== process() END OK ===")

            except Exception as e:
                _dbg(f"process() UNHANDLED EXCEPTION: {e}\n{traceback.format_exc()}")
                self.ball.safe_show_error(f"程序錯誤: {str(e)[:30]}")
                self._update_tray("ready")

            finally:
                self._processing = False  # 无论成功/失败/异常，必定复位
                self._write_status("idle")  # 確保所有路徑都清回 idle（成功路徑已手動設定，此為冗余保護）

        threading.Thread(target=process, daemon=True).start()

    # ── 狀態寫入（供 Dashboard 輪詢）────────────────────────────────────────
    def _write_status(self, state: str, text: str = ""):
        try:
            status = {
                "state": state,
                "text":  text[:80] if text else "",
                "ts":    datetime.datetime.now().isoformat(),
                "model": self.transcriber.last_model,
            }
            status_file = CONFIG_DIR / "status.json"
            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False)
        except Exception:
            pass

    # ── 热键轮询 ──────────────────────────────────────────────────────────────
    def _poll_hotkey(self):
        hotkey       = self.config.get("hotkey", "right shift")
        keys         = [k.strip() for k in hotkey.split("+")]
        was_pressed  = False
        release_lock = threading.Lock()   # 确保 on_release 只执行一次

        while True:
            try:
                currently = all(keyboard.is_pressed(k) for k in keys)

                if currently and not was_pressed:
                    was_pressed = True
                    self.on_press()

                elif not currently and was_pressed:
                    was_pressed = False
                    # 用锁保证即使抖动触发多次，on_release 只执行一次
                    if release_lock.acquire(blocking=False):
                        try:
                            self.on_release()
                        finally:
                            # 500ms 后释放锁，防止同一次松开重复触发
                            def unlock():
                                time.sleep(0.5)
                                release_lock.release()
                            threading.Thread(target=unlock, daemon=True).start()

            except Exception:
                pass
            time.sleep(0.02)

    def _listen_enter(self):
        """监听 Enter 键，在发送前捕获剪贴板内容更新词典"""
        def on_enter():
            try:
                # 读取当前剪贴板（上次粘贴进去的语音文字还在里面）
                text = pyperclip.paste()
                if text and len(text) > 3:
                    # 后台静默学习这条文字
                    threading.Thread(
                        target=self._learn_from_text,
                        args=(text,), daemon=True).start()
            except Exception:
                pass

        keyboard.on_press_key("enter", lambda _: on_enter())
        keyboard.on_press_key("return", lambda _: on_enter())

    def _learn_from_text(self, text: str):
        """从一段文字中学习词汇"""
        try:
            from smart_vocab import extract_words, load_smart_dict, save_smart_dict
            words = extract_words(text)
            if not words:
                return
            smart_dict = load_smart_dict()
            updated = False
            for word in words:
                current = smart_dict["words"].get(word, 0)
                smart_dict["words"][word] = current + 1
                updated = True
            if updated:
                smart_dict["last_updated"] = datetime.datetime.now().isoformat()
                smart_dict["total_learned"] = len(smart_dict["words"])
                save_smart_dict(smart_dict)
                # 同步到 vocab
                from smart_vocab import _sync_to_vocab
                _sync_to_vocab(smart_dict["words"])
        except Exception:
            pass

    # ── 控制信號監聽 ────────────────────────────────────────────────────────
    CONTROL_SIGNAL = Path(__file__).parent / "userdata" / "control_signal.json"

    def _watch_control_signal(self):
        """監聽 userdata/control_signal.json，支援外部工具控制 SmarType"""
        while True:
            try:
                if self.CONTROL_SIGNAL.exists():
                    data = json.loads(self.CONTROL_SIGNAL.read_text(encoding="utf-8"))
                    cmd = data.get("cmd", "")
                    self.CONTROL_SIGNAL.unlink(missing_ok=True)
                    _dbg(f"control signal received: {cmd}")

                    if cmd == "restart":
                        _dbg("control: restarting SmarType...")
                        import subprocess
                        subprocess.Popen(
                            [sys.executable] + sys.argv,
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                        _dbg("control: new process launched, exiting old...")
                        os._exit(0)
                    elif cmd == "reload_config":
                        self.config = load_config()
                        _dbg("control: config reloaded")
                    elif cmd == "stop":
                        _dbg("control: stopping SmarType...")
                        os._exit(0)
            except Exception as e:
                _dbg(f"control signal error: {e}")
            time.sleep(1)

    # ── 启动 ──────────────────────────────────────────────────────────────────
    def run(self):
        # 单实例锁（防止多进程同时运行出现双球）
        try:
            self._mutex = ctypes.windll.kernel32.CreateMutexW(
                None, True, "SmarType_v6_SingleInstance")
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                root = tk.Tk()
                root.withdraw()
                tk.messagebox.showinfo(
                    "快打 SmarType", "程序已在运行中，请查看系统托盘。")
                root.destroy()
                sys.exit(0)
        except Exception:
            pass  # 非 Windows 环境或权限不足时跳过

        if not self.config.get("groq_api_key") and not self.config.get("api_key"):
            root = tk.Tk()
            root.withdraw()
            tk.messagebox.showerror(
                "快打 SmarType",
                "未设置 API Key！\n请运行 python setup.py")
            root.destroy()
            sys.exit(1)

        _dbg("=== SmarType v6 START ===")
        _dbg(f"groq_key={'SET' if self.config.get('groq_api_key') else 'MISSING'}")
        _dbg(f"openai_key_valid={'YES' if self.config.get('api_key','').startswith('sk-') else 'NO/EMPTY (OK if using Groq)'}")
        _dbg(f"hotkey={self.config.get('hotkey','right shift')}")
        _dbg(f"mic_index={self.config.get('mic_index', 'default')}")

        # ★ 背景預載 Sherpa-ONNX 串流模型（跑馬燈即時預覽用）
        def _preload_streaming():
            try:
                from streaming_transcriber import preload
                if preload():
                    _dbg("Sherpa-ONNX streaming model preloaded OK — 跑馬燈將使用串流辨識")
                else:
                    _dbg("Sherpa-ONNX preload returned False")
            except Exception as e:
                _dbg(f"Sherpa-ONNX preload failed: {e}")
        threading.Thread(target=_preload_streaming, daemon=True).start()

        # 控制信號監聽（讓外部工具如 Claude Code 可重啟/停止）
        threading.Thread(target=self._watch_control_signal, daemon=True).start()
        # 热键轮询子线程
        threading.Thread(target=self._poll_hotkey, daemon=True).start()
        # Enter 键监听（学习发送的文字）
        threading.Thread(target=self._listen_enter, daemon=True).start()
        # 日記排程（每晚10點自動生成摘要）
        try:
            from diary_engine import start_daily_scheduler
            start_daily_scheduler()
            _dbg("diary scheduler started")
        except Exception as de:
            _dbg(f"diary scheduler failed: {de}")
        # 開機自動啟動 Dashboard（dashboard.py 自己做單例判斷）
        def _launch_dashboard():
            time.sleep(1.5)
            try:
                import subprocess
                subprocess.Popen(
                    [sys.executable, str(Path(__file__).parent / "dashboard.py")],
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32" else 0)
                _dbg("dashboard launched on startup")
            except Exception as e:
                _dbg(f"dashboard launch failed: {e}")
        threading.Thread(target=_launch_dashboard, daemon=True).start()

        # 本地模型背景預載（若啟用）
        if self.config.get("use_local_model", False):
            try:
                from local_transcriber import preload_async
                preload_async(self.config.get("local_model_size", "medium"))
                _dbg("local model preloading in background")
            except Exception as le:
                _dbg(f"local model preload failed: {le}")

        # 托盘子线程
        self.tray = pystray.Icon(
            "SmarType",
            make_tray_icon("ready"),
            "快打 SmarType",
            menu=self._build_menu(),
        )
        threading.Thread(target=self.tray.run, daemon=True).start()

        # 主线程用 Tk mainloop（唯一正确方式）
        try:
            self.ball.root.mainloop()
        except Exception as e:
            _dbg(f"mainloop error: {e}")


if __name__ == "__main__":
    try:
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

    SmarTypeApp().run()
