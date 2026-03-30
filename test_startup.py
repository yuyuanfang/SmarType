"""
SmarType / 快打 — 啟動與環境自檢（硬體 + 軟體）

用途：
  - 驗證設定檔、麥克風、Python 依賴、Groq 連線（可選）
  - 偵測主程式是否已在執行（單實例 Mutex）
  - 從 debug.log 粗查「重複觸發」類問題（雙重 on_release）

執行：
  python test_startup.py              # 完整自檢（含 1 秒懸浮球預覽）
  python test_startup.py --quick      # 略過 Tk 懸浮球與 Groq 轉錄
  python test_startup.py --transcribe # 額外：錄 3 秒並呼叫 Groq（耗 API）

若從 PyInstaller 目錄執行，請將本檔與 dictation 同目錄，或從該目錄執行 python。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path


def _base_dir() -> Path:
    return Path(__file__).resolve().parent


def _ensure_utf8_stdio() -> None:
    """避免 Windows 預設 GBK 主控台無法輸出 ✅⚠ 等字元。"""
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _resolve_config(base: Path) -> tuple[Path, dict | None, str]:
    """回傳 (實際使用的 config 路徑, 內容或 None, 說明)."""
    candidates = [
        (base / "userdata" / "config.json", "專案 userdata（與 dictation.py 一致）"),
        (Path.home() / ".whisper-dictation" / "config.json", "使用者目錄 .whisper-dictation（舊版/工具腳本）"),
    ]
    for path, note in candidates:
        if path.is_file():
            try:
                with open(path, encoding="utf-8") as f:
                    return path, json.load(f), note
            except Exception as e:
                return path, None, f"{note}（讀取失敗: {e}）"
    return candidates[0][0], None, "未找到 config.json"


def _check_mutex_smartype() -> str:
    """偵測 SmarType 單實例鎖是否已被占用。"""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        name = "SmarType_v6_SingleInstance"
        handle = kernel32.CreateMutexW(None, True, name)
        err = kernel32.GetLastError()
        if handle:
            if err == ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(handle)
                return "⚠ Mutex 已被占用 → 主程式可能已在執行；若已關閉仍顯示此訊息，請工作管理員結束殘留行程。"
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
        return "✅ 單實例 Mutex 可用（目前無其他 SmarType 佔用）。"
    except Exception as e:
        return f"⚠ 無法檢測 Mutex（非 Windows 或權限）: {e}"


def _scan_debug_log_for_double_release(log_path: Path, tail_lines: int = 120) -> str:
    if not log_path.is_file():
        return f"（無 {log_path.name}，略過日誌分析）"
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"（無法讀取 debug.log: {e}）"
    recent = lines[-tail_lines:]
    # 找連續兩行「on_release: stopping」且時間戳極接近（已知重複注入問題徵兆）
    pat = re.compile(r"^\[(\d{2}:\d{2}:\d{2}\.\d{3})\].*on_release: stopping")
    hits: list[tuple[str, int]] = []
    for i, line in enumerate(recent):
        m = pat.search(line)
        if m:
            hits.append((m.group(1), i))
    suspicious = 0
    for a, b in zip(hits, hits[1:]):
        # 同一分鐘內連續兩次 stopping（簡化：僅比較字串相鄰行）
        if b[1] == a[1] + 1:
            suspicious += 1
    if suspicious:
        return (
            f"⚠ 最近日誌中發現 {suspicious} 處「連續兩行 on_release: stopping」"
            " — 與「重複貼上/雙重熱鍵」問題相符，請檢查 dictation 是否重複啟動 _poll_hotkey 或需加鎖。"
        )
    return "✅ 最近日誌未見明顯「連續雙重 on_release」模式。"


def _rms_int16_mono(fragment: bytes) -> int:
    """與 audioop.rms(fragment, 2) 等價，避免 Python 3.13+ 移除 audioop。"""
    if not fragment or len(fragment) < 2:
        return 0
    import struct

    n = len(fragment) // 2
    vals = struct.unpack(f"<{n}h", fragment[: n * 2])
    if not vals:
        return 0
    return int((sum(v * v for v in vals) / len(vals)) ** 0.5)


def _deps() -> list[tuple[str, str]]:
    """(模組 import 名稱, 顯示名稱)"""
    return [
        ("groq", "groq"),
        ("openai", "openai"),
        ("pyaudio", "pyaudio"),
        ("keyboard", "keyboard"),
        ("pyautogui", "pyautogui"),
        ("pyperclip", "pyperclip"),
        ("pystray", "pystray"),
        ("PIL", "Pillow"),
        ("win32api", "pywin32"),
    ]


def _mic_probe(mic_index: int | None) -> str:
    import pyaudio

    pa = pyaudio.PyAudio()
    try:
        n = pa.get_device_count()
        if n <= 0:
            return "❌ PyAudio 裝置數為 0"
        default = pa.get_default_input_device_info()
        idx = mic_index if mic_index is not None else default["index"]
        info = pa.get_device_info_by_index(idx)
        if info.get("maxInputChannels", 0) < 1:
            return f"❌ 裝置索引 {idx} 不是輸入裝置"
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            input_device_index=idx,
            frames_per_buffer=1024,
        )
        chunk = stream.read(1024, exception_on_overflow=False)
        stream.stop_stream()
        stream.close()
        rms = _rms_int16_mono(chunk)
        return (
            f"✅ 麥克風可讀取（索引 {idx}: {info.get('name', '?')[:50]}…）"
            f" 試讀 RMS={rms}（靜音時通常較低）"
        )
    except Exception as e:
        return f"❌ 麥克風開啟/讀取失敗: {e}"
    finally:
        pa.terminate()


def _groq_ping(cfg: dict) -> str:
    key = (cfg.get("groq_api_key") or "").strip()
    if not key:
        return "（略過 Groq：未設定 groq_api_key）"
    try:
        from groq import Groq

        Groq(api_key=key)
        return "✅ Groq 客戶端可建立（未送轉錄請求）。"
    except Exception as e:
        return f"❌ Groq 初始化失敗: {e}"


def _groq_transcribe_3s(cfg: dict) -> str:
    import io
    import wave

    key = (cfg.get("groq_api_key") or "").strip()
    if not key:
        return "❌ 無 groq_api_key，無法轉錄測試"
    import pyaudio

    from groq import Groq

    RATE, CHUNK, CHANNELS = 16000, 1024, 1
    pa = pyaudio.PyAudio()
    mic = cfg.get("mic_index")
    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=mic,
            frames_per_buffer=CHUNK,
        )
        frames = []
        for _ in range(int(RATE / CHUNK * 3)):
            frames.append(stream.read(CHUNK, exception_on_overflow=False))
        stream.stop_stream()
        stream.close()
    finally:
        pa.terminate()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))
    wav_bytes = buf.getvalue()
    client = Groq(api_key=key)
    result = client.audio.transcriptions.create(
        model="whisper-large-v3-turbo",
        file=("audio.wav", wav_bytes, "audio/wav"),
        language="zh",
        response_format="text",
    )
    text = result.strip() if isinstance(result, str) else (getattr(result, "text", None) or "").strip()
    return f"✅ Groq 轉錄（3 秒）: [{text or '(空)'}]"


def main() -> int:
    _ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="SmarType 環境與硬體自檢")
    ap.add_argument("--quick", action="store_true", help="略過 Tk 懸浮球與 Groq 建立")
    ap.add_argument("--transcribe", action="store_true", help="錄 3 秒並呼叫 Groq（會耗用 API）")
    args = ap.parse_args()

    base = _base_dir()
    print("=" * 60)
    print("SmarType 自檢 — 硬體 / 軟體 / 設定")
    print(f"專案目錄: {base}")
    print("=" * 60)

    cfg_path, config, cfg_note = _resolve_config(base)
    print(f"\n[1] 設定檔\n    路徑: {cfg_path}\n    來源: {cfg_note}")
    if config is None:
        print("    ❌ 無法載入設定；請執行 setup 或建立 userdata/config.json")
        return 1
    print(f"    hotkey      : {config.get('hotkey', '(未設)')}")
    print(f"    mic_index   : {config.get('mic_index', 'None → 系統預設')}")
    print(f"    groq_api_key: {'已設定' if config.get('groq_api_key') else '未設定'}")
    print(f"    api_key     : {'已設定' if config.get('api_key') else '未設定'}")

    print("\n[2] 單實例與日誌")
    print("   ", _check_mutex_smartype())
    debug_log = base / "userdata" / "debug.log"
    print("   ", _scan_debug_log_for_double_release(debug_log))

    print("\n[3] Python 依賴")
    failed = False
    for mod, label in _deps():
        try:
            __import__(mod)
            print(f"    ✅ {label}")
        except ImportError:
            print(f"    ❌ {label} 未安裝")
            failed = True
    if failed:
        print("\n請: pip install -r requirements.txt（或依專案說明安裝）")
        return 1

    print("\n[4] 麥克風（與主程式相同取樣率 16k/mono）")
    mic_i = config.get("mic_index")
    if mic_i is not None and not isinstance(mic_i, int):
        try:
            mic_i = int(mic_i)
        except (TypeError, ValueError):
            mic_i = None
    print("   ", _mic_probe(mic_i))

    if not args.quick:
        print("\n[5] Groq 客戶端")
        print("   ", _groq_ping(config))
    else:
        print("\n[5] Groq 客戶端（--quick 已略過）")

    if args.transcribe:
        print("\n[5b] Groq 轉錄測試（請對麥克風說話約 3 秒）…")
        time.sleep(0.3)
        try:
            print("   ", _groq_transcribe_3s(config))
        except Exception as e:
            print(f"    ❌ 轉錄測試失敗: {e}")
            traceback.print_exc()
            return 1

    if args.quick:
        print("\n[6] Tk 介面（--quick 已略過懸浮球預覽）")
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            root.destroy()
            print("    ✅ tkinter 基本可用")
        except Exception as e:
            print(f"    ❌ tkinter: {e}")
            return 1
    else:
        print("\n[6] Tkinter 與懸浮球預覽（約 1 秒）")
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            print("    ✅ Tk root OK")
            root.destroy()

            root2 = tk.Tk()
            root2.overrideredirect(True)
            root2.attributes("-topmost", True)
            root2.attributes("-transparentcolor", "#010101")
            root2.configure(bg="#010101")
            root2.geometry("300x220+500+300")
            canvas = tk.Canvas(root2, width=300, height=220, bg="#010101", highlightthickness=0)
            canvas.pack()
            canvas.create_oval(90, 10, 210, 130, fill="#1D9E75", outline="")
            root2.after(1000, root2.destroy)
            root2.mainloop()
            print("    ✅ CenterBall 風格視窗 OK")

            from PIL import Image, ImageDraw

            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([4, 4, 60, 60], fill="#1D9E75")
            print("    ✅ 托盤圖示用影像 OK")
        except Exception as e:
            print(f"    ❌ GUI 測試失敗: {e}")
            traceback.print_exc()
            return 1

        try:
            from PIL import Image, ImageDraw
            import pystray

            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([4, 4, 60, 60], fill="#1D9E75")
            print("    ✅ pystray / PIL 已載入（未實際顯示托盤圖示）")
        except Exception as e:
            print(f"    ❌ pystray: {e}")
            return 1

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED — 環境可支援 SmarType 正常運作")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        print("\n已取消。")
        code = 130
    input("\n按 Enter 關閉…")
    sys.exit(code)
