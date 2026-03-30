"""
錄音控制模組 — PyAudio 初始化、錄音 start/stop、WAV 編碼、文字注入
"""

import io, time, wave, threading
import pyaudio
import pyperclip
import pyautogui

from config_manager import _dbg

# ── 音頻常數 ──────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
CHANNELS    = 1
CHUNK       = 1024
FORMAT      = pyaudio.paInt16


# ── 錄音器（支援分段回呼）────────────────────────────────────────────────────
class Recorder:
    def __init__(self, mic_index=None):
        self.pa         = pyaudio.PyAudio()
        self.frames     = []
        self.recording  = False
        self.stream     = None
        self.mic_index  = mic_index
        self.on_pcm     = None  # 每幀 PCM 回呼 fn(bytes)，用於串流 ASR

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
        """停止錄音，返回完整音頻的 WAV bytes"""
        self.recording = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        # 最短 0.8 秒才送辨識（約 12 幀），防止極短按鍵產生幻覺文字
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


# ── 文字注入 ──────────────────────────────────────────────────────────────────
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


# ── 上下文輔助 ────────────────────────────────────────────────────────────────
def get_chat_context():
    """從剪貼簿取得上下文，提取關鍵詞給 Whisper 提升準確度"""
    try:
        text = pyperclip.paste()
        if not text or len(text) < 5:
            return ""
        return text[-300:].strip()
    except Exception:
        pass
    return ""


def load_history_context() -> str:
    """從本地歷史記錄中提取最近 10 條的關鍵詞，作為 Whisper prompt 的補充上下文"""
    import json
    from config_manager import LOG_FILE
    try:
        if not LOG_FILE.exists():
            return ""
        lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
        recent = lines[-10:]
        texts = []
        for line in recent:
            try:
                r = json.loads(line)
                texts.append(r.get("text", ""))
            except Exception:
                pass
        combined = " ".join(texts)
        return combined[-200:] if len(combined) > 200 else combined
    except Exception:
        return ""
