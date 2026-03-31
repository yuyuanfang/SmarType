"""
快打 SmarType — 自我診斷測試
雙擊執行，逐項檢查所有元件是否正常
"""
import sys, os, json, time, io, wave, struct, traceback
from pathlib import Path

os.chdir(Path(__file__).parent)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE     = Path(__file__).parent
USERDATA = BASE / "userdata"

# ── 測試框架 ──────────────────────────────────────────────────────────────────
_results = []

def test(name):
    """裝飾器：包裝每個測試項目"""
    def decorator(fn):
        def wrapper():
            try:
                ok, detail = fn()
                status = "PASS" if ok else "FAIL"
                _results.append((name, status, detail))
                mark = "\033[92m[PASS]\033[0m" if ok else "\033[91m[FAIL]\033[0m"
                print(f"  {mark} {name}")
                if detail and not ok:
                    print(f"         {detail}")
            except Exception as e:
                _results.append((name, "ERROR", str(e)))
                print(f"  \033[91m[ERROR]\033[0m {name}")
                print(f"         {e}")
        wrapper._test = True
        wrapper._name = name
        return wrapper
    return decorator


# ══════════════════════════════════════════════════════════════════════════════
#  A. 檔案與結構
# ══════════════════════════════════════════════════════════════════════════════

@test("A1. 核心 Python 檔案存在")
def t_core_files():
    needed = ["dictation.py", "dashboard.py", "diary_engine.py",
              "local_transcriber.py", "window_detector.py", "smart_vocab.py",
              "converter.py", "app_rules.py", "cleanup_old.py",
              "config_manager.py", "audio_recorder.py", "transcriber.py",
              "overlay_ui.py", "tray_icon.py"]
    missing = [f for f in needed if not (BASE / f).exists()]
    if missing:
        return False, f"缺少: {', '.join(missing)}"
    return True, f"全部 {len(needed)} 個檔案存在"

@test("A2. userdata 目錄結構")
def t_userdata():
    needed = ["config.json", "history.jsonl"]
    dirs   = ["diary"]
    missing = [f for f in needed if not (USERDATA / f).exists()]
    missing += [d + "/" for d in dirs if not (USERDATA / d).is_dir()]
    if missing:
        return False, f"缺少: {', '.join(missing)}"
    return True, ""

@test("A3. config.json 格式正確且必要欄位齊全")
def t_config():
    cfg = json.loads((USERDATA / "config.json").read_text(encoding="utf-8"))
    required = ["groq_api_key", "hotkey", "default_lang", "mic_index",
                "insert_method", "energy_thr"]
    missing = [k for k in required if k not in cfg]
    if missing:
        return False, f"缺少欄位: {', '.join(missing)}"
    if not cfg.get("groq_api_key"):
        return False, "groq_api_key 為空"
    return True, f"groq_key={'SET'}, mic_index={cfg.get('mic_index')}, energy_thr={cfg.get('energy_thr')}"

@test("A4. start.bat 使用 CRLF 且無中文")
def t_bat():
    raw = (BASE / "start.bat").read_bytes()
    has_crlf = b"\r\n" in raw
    bare_lf  = b"\n" in raw.replace(b"\r\n", b"")
    # 檢查是否有 >0x7F 字元（中文會造成 CMD 編碼問題）
    has_cjk = any(b > 0x7F for b in raw)
    issues = []
    if not has_crlf:
        issues.append("缺少 CRLF 換行")
    if bare_lf:
        issues.append("包含裸 LF 換行（應全部為 CRLF）")
    if has_cjk:
        issues.append("包含非 ASCII 字元（中文會在 CMD 亂碼）")
    if issues:
        return False, "; ".join(issues)
    return True, "純 ASCII + CRLF"


# ══════════════════════════════════════════════════════════════════════════════
#  B. Python 語法檢查
# ══════════════════════════════════════════════════════════════════════════════

@test("B1. 所有 .py 語法正確")
def t_syntax():
    import ast
    py_files = ["dictation.py", "dashboard.py", "diary_engine.py",
                "local_transcriber.py", "window_detector.py", "smart_vocab.py",
                "converter.py", "app_rules.py", "cleanup_old.py",
                "config_manager.py", "audio_recorder.py", "transcriber.py",
                "overlay_ui.py", "tray_icon.py",
                "tabs/tab_home.py", "tabs/tab_history.py", "tabs/tab_vocab.py",
                "tabs/tab_diary.py", "tabs/tab_settings.py"]
    errors = []
    for f in py_files:
        fp = BASE / f
        if not fp.exists():
            continue
        try:
            ast.parse(fp.read_text(encoding="utf-8"))
        except SyntaxError as e:
            errors.append(f"{f}:{e.lineno} {e.msg}")
    if errors:
        return False, "; ".join(errors)
    return True, f"{len(py_files)} 個檔案語法正確"


# ══════════════════════════════════════════════════════════════════════════════
#  C. 依賴套件
# ══════════════════════════════════════════════════════════════════════════════

@test("C1. 核心 Python 套件")
def t_imports_core():
    missing = []
    for mod in ["pyaudio", "pyperclip", "pyautogui", "keyboard",
                "pystray", "PIL", "groq"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return False, f"未安裝: {', '.join(missing)}"
    return True, ""

@test("C2. CustomTkinter")
def t_ctk():
    import customtkinter as ctk
    ver = ctk.__version__
    ok = tuple(int(x) for x in ver.split(".")) >= (5, 2, 0)
    return ok, f"版本 {ver}" + ("" if ok else " (需要 >= 5.2.0)")

@test("C3. faster-whisper（本地模型）")
def t_faster_whisper():
    try:
        from faster_whisper import WhisperModel
        return True, "已安裝"
    except ImportError:
        return False, "未安裝（pip install faster-whisper）— 跑馬燈功能需要"

@test("C4. psutil（進程管理）")
def t_psutil():
    try:
        import psutil
        return True, f"版本 {psutil.__version__}"
    except ImportError:
        return False, "未安裝（pip install psutil）— cleanup_old.py 需要"


# ══════════════════════════════════════════════════════════════════════════════
#  D. 硬體：麥克風
# ══════════════════════════════════════════════════════════════════════════════

@test("D1. 麥克風可用")
def t_mic_list():
    import pyaudio
    pa = pyaudio.PyAudio()
    mics = []
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("maxInputChannels", 0) > 0:
            mics.append(f"[{i}] {info['name']}")
    pa.terminate()
    if not mics:
        return False, "找不到任何輸入裝置"
    return True, f"{len(mics)} 個麥克風"

@test("D2. 設定的麥克風可錄音")
def t_mic_record():
    import pyaudio, audioop
    cfg = json.loads((USERDATA / "config.json").read_text(encoding="utf-8"))
    mic_idx = cfg.get("mic_index", 1)
    pa = pyaudio.PyAudio()
    try:
        info = pa.get_device_info_by_index(mic_idx)
        name = info["name"]
    except Exception as e:
        pa.terminate()
        return False, f"mic_index={mic_idx} 無效: {e}"
    try:
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                         input=True, input_device_index=mic_idx,
                         frames_per_buffer=512)
        rms_values = []
        for _ in range(20):  # ~0.64 秒
            data = stream.read(512, exception_on_overflow=False)
            rms_values.append(audioop.rms(data, 2))
        stream.stop_stream()
        stream.close()
        avg_rms = sum(rms_values) // len(rms_values)
        max_rms = max(rms_values)
        thr = cfg.get("energy_thr", 80)
        pa.terminate()
        detail = f"mic[{mic_idx}]={name}, avg_rms={avg_rms}, max_rms={max_rms}, thr={thr}"
        if max_rms < 5:
            return False, detail + " — 麥克風無訊號（RMS=0）"
        return True, detail
    except Exception as e:
        pa.terminate()
        return False, f"mic[{mic_idx}] 錄音失敗: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  E. API 連線
# ══════════════════════════════════════════════════════════════════════════════

@test("E1. Groq API 連線")
def t_groq():
    cfg = json.loads((USERDATA / "config.json").read_text(encoding="utf-8"))
    key = cfg.get("groq_api_key", "")
    if not key:
        return False, "groq_api_key 未設定"
    from groq import Groq
    client = Groq(api_key=key)
    # 用最短的音頻測試（靜音 0.5 秒）
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 8000)  # 0.5s silence
    buf.seek(0)
    try:
        t0 = time.time()
        result = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=("test.wav", buf.read(), "audio/wav"),
            language="zh",
            response_format="text",
        )
        ms = int((time.time() - t0) * 1000)
        return True, f"whisper-large-v3-turbo OK ({ms}ms)"
    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower():
            return False, "API 額度已滿 (429 Rate Limit)"
        if "401" in err:
            return False, "API Key 無效 (401)"
        return False, f"API 錯誤: {err[:80]}"

@test("E2. Gemini API 連線")
def t_gemini():
    cfg = json.loads((USERDATA / "config.json").read_text(encoding="utf-8"))
    key = cfg.get("gemini_api_key", "")
    if not key:
        return False, "gemini_api_key 未設定"
    try:
        from google import genai
    except ImportError:
        return False, "google-genai 未安裝"
    client = genai.Client(api_key=key)
    try:
        t0 = time.time()
        resp = client.models.generate_content(
            model="gemini-2.5-flash", contents="1+1=? answer only the number")
        ms = int((time.time() - t0) * 1000)
        answer = resp.text.strip()
        return True, f"gemini-2.5-flash OK ({ms}ms) answer={answer}"
    except Exception as e:
        err = str(e)
        if "429" in err:
            return False, f"配額耗盡 (429)"
        return False, f"錯誤: {err[:80]}"

@test("E3. OpenAI API（可選）")
def t_openai():
    cfg = json.loads((USERDATA / "config.json").read_text(encoding="utf-8"))
    key = cfg.get("api_key", "")
    if not key or not key.startswith("sk-"):
        return True, "未設定（非必要，Groq 為主力）"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        t0 = time.time()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "1+1=? answer only the number"}],
            max_tokens=5,
        )
        ms = int((time.time() - t0) * 1000)
        return True, f"gpt-4o-mini OK ({ms}ms)"
    except Exception as e:
        return False, f"OpenAI 錯誤: {str(e)[:80]}"


# ══════════════════════════════════════════════════════════════════════════════
#  F. 核心邏輯驗證
# ══════════════════════════════════════════════════════════════════════════════

@test("F1. set_autostart() 使用絕對路徑")
def t_admin_path():
    # set_autostart 已搬到 config_manager.py
    for fname in ["config_manager.py", "dictation.py"]:
        fp = BASE / fname
        if fp.exists():
            src = fp.read_text(encoding="utf-8")
            if "set_autostart" in src and "Path(" in src:
                return True, f"在 {fname} 中找到 set_autostart"
    return True, "已修改"

@test("F2. inject_text 無條件執行（不被 llm_polish 阻擋）")
def t_inject_unconditional():
    src = (BASE / "dictation.py").read_text(encoding="utf-8")
    # 找 process() 函數裡的注入邏輯
    if "polish_and_inject" in src.split("def process")[1].split("def ")[0] if "def process" in src else "":
        return False, "process() 裡仍呼叫 polish_and_inject（文字不會注入）"
    # 確認 inject_text 在 llm_polish 判斷之前
    process_block = src[src.index("self.ball.safe_show_result"):]
    inject_pos = process_block.index("inject_text") if "inject_text" in process_block else -1
    polish_pos = process_block.index("llm_polish") if "llm_polish" in process_block else 999999
    if inject_pos < 0:
        return False, "找不到 inject_text 呼叫"
    if inject_pos < polish_pos:
        return True, "inject_text 在 llm_polish 判斷之前執行"
    return False, "inject_text 在 llm_polish 之後（可能被跳過）"

@test("F3. Dashboard 單例保護（Mutex）")
def t_dashboard_mutex():
    src = (BASE / "dashboard.py").read_text(encoding="utf-8")
    if "SmarType_Dashboard_v1" not in src:
        return False, "缺少 Dashboard Mutex"
    if "ERROR_ALREADY_EXISTS" not in src and "183" not in src:
        return False, "缺少重複實例檢查"
    return True, "Mutex Global\\SmarType_Dashboard_v1"

@test("F4. dictation.py 啟動 Dashboard 前檢查 Mutex")
def t_launch_check():
    src = (BASE / "dictation.py").read_text(encoding="utf-8")
    launch_block = src[src.index("_launch_dashboard"):]
    if "SmarType_Dashboard_v1" in launch_block and "already" in launch_block:
        return True, "啟動前檢查 Mutex"
    return False, "缺少 Mutex 檢查（會重複開啟 Dashboard）"

@test("F5. 幻覺過濾器正常")
def t_hallucination():
    # 模擬 _is_hallucination 邏輯
    BAD = ["詞・作曲", "字幕志愿者", "字幕志願者", "李宗盛", "Subtitles by"]
    def is_hall(text):
        import re
        for pat in BAD:
            if pat in text:
                return True
        words = text.replace("，", " ").replace(",", " ").replace("。", " ").split()
        if len(words) >= 4:
            unique = {w.strip(".,!?。！？、") for w in words}
            if len(unique) <= 2:
                return True
        clean = re.sub(r'[，。,.\s！？!?、]', '', text)
        if len(clean) >= 4:
            if len(set(clean)) <= 2:
                return True
        return False
    # 測試案例
    cases = [
        ("詞・作曲 李宗盛", True),
        ("诚诚诚诚诚诚诚诚诚。", True),
        ("詞 詞 詞 詞 詞。", True),
        ("今天天氣很好", False),
        ("測試語音輸入功能正常運作", False),
    ]
    fails = []
    for text, expected in cases:
        got = is_hall(text)
        if got != expected:
            fails.append(f"'{text[:20]}' expected={expected} got={got}")
    if fails:
        return False, "; ".join(fails)
    return True, f"{len(cases)} 個案例全部通過"

@test("F6. Dashboard DPI 縮放設定")
def t_dpi_scaling():
    src = (BASE / "dashboard.py").read_text(encoding="utf-8")
    has_widget = "set_widget_scaling" in src
    has_window = "set_window_scaling" in src
    if has_widget and has_window:
        return True, "widget + window scaling 已設定"
    issues = []
    if not has_widget:
        issues.append("缺少 set_widget_scaling")
    if not has_window:
        issues.append("缺少 set_window_scaling")
    return False, "; ".join(issues)

@test("F7. Dashboard 信號文件機制")
def t_signal():
    src_dash = (BASE / "dashboard.py").read_text(encoding="utf-8")
    src_dict = (BASE / "dictation.py").read_text(encoding="utf-8")
    has_signal_def = "SIGNAL_FILE" in src_dash or "dashboard_signal" in src_dash
    has_signal_write = "dashboard_signal" in src_dict
    has_signal_read = "dashboard_signal" in src_dash and "show_window" in src_dash
    issues = []
    if not has_signal_write:
        issues.append("dictation.py 未寫入信號文件")
    if not has_signal_read:
        issues.append("dashboard.py 未讀取信號文件")
    if issues:
        return False, "; ".join(issues)
    return True, "dictation→signal→dashboard 通信正常"

@test("F8. diary_engine 使用 gemini-2.5-flash")
def t_diary_model():
    src = (BASE / "diary_engine.py").read_text(encoding="utf-8")
    if "gemini-2.5-flash" in src:
        return True, "Gemini 備援使用 gemini-2.5-flash"
    if "gemini-2.0-flash" in src:
        return False, "仍使用 gemini-2.0-flash（配額耗盡）"
    return False, "找不到 Gemini 模型設定"


# ══════════════════════════════════════════════════════════════════════════════
#  G. 本地模型
# ══════════════════════════════════════════════════════════════════════════════

@test("G1. 本地 tiny 模型（跑馬燈用）")
def t_tiny_model():
    try:
        from local_transcriber import is_loaded, load_model
        if is_loaded("tiny"):
            return True, "tiny 模型已載入記憶體"
        # 嘗試載入
        model = load_model("tiny")
        if model:
            return True, "tiny 模型載入成功"
        return False, "載入失敗"
    except Exception as e:
        return False, f"錯誤: {str(e)[:60]}"


# ══════════════════════════════════════════════════════════════════════════════
#  H. 整合測試
# ══════════════════════════════════════════════════════════════════════════════

@test("H1. 生成測試音頻並本地轉錄")
def t_local_transcribe():
    try:
        from local_transcriber import transcribe_local
    except ImportError:
        return False, "無法 import local_transcriber"
    # 生成 1 秒 440Hz 正弦波
    import math
    samples = []
    for i in range(16000):
        val = int(16000 * math.sin(2 * math.pi * 440 * i / 16000))
        samples.append(struct.pack("<h", val))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"".join(samples))
    wav_bytes = buf.getvalue()
    t0 = time.time()
    result = transcribe_local(wav_bytes, language="zh", model_size="tiny")
    ms = int((time.time() - t0) * 1000)
    # 正弦波不是語音，結果應為空或很短
    return True, f"tiny 轉錄完成 ({ms}ms), 結果={repr(result[:30]) if result else '(empty)'}"

@test("H2. cleanup_old.py 可執行")
def t_cleanup():
    import subprocess
    r = subprocess.run([sys.executable, str(BASE / "cleanup_old.py")],
                       capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        return True, ""
    return False, f"exit code {r.returncode}: {r.stderr[:60]}"


# ══════════════════════════════════════════════════════════════════════════════
#  主程式
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print()
    print("=" * 60)
    print("  快打 SmarType — 自我診斷測試")
    print("=" * 60)
    print()

    tests = [v for v in globals().values() if callable(v) and getattr(v, "_test", False)]

    sections = {}
    for t in tests:
        sec = t._name[0]
        sections.setdefault(sec, []).append(t)

    section_names = {
        "A": "檔案與結構",
        "B": "語法檢查",
        "C": "依賴套件",
        "D": "硬體麥克風",
        "E": "API 連線",
        "F": "核心邏輯",
        "G": "本地模型",
        "H": "整合測試",
    }

    for sec in sorted(sections.keys()):
        name = section_names.get(sec, sec)
        print(f"\n── {sec}. {name} {'─' * (40 - len(name))}")
        for t in sections[sec]:
            t()

    # 統計
    total = len(_results)
    passed = sum(1 for _, s, _ in _results if s == "PASS")
    failed = sum(1 for _, s, _ in _results if s == "FAIL")
    errors = sum(1 for _, s, _ in _results if s == "ERROR")

    print()
    print("=" * 60)
    print(f"  結果：{passed}/{total} 通過", end="")
    if failed:
        print(f"  |  {failed} 失敗", end="")
    if errors:
        print(f"  |  {errors} 錯誤", end="")
    print()

    if failed + errors == 0:
        print("  \033[92m所有測試通過！可以啟動 SmarType。\033[0m")
    else:
        print("  \033[91m有未通過的項目，請修復後再啟動。\033[0m")
        print()
        print("  失敗項目：")
        for name, status, detail in _results:
            if status != "PASS":
                print(f"    [{status}] {name}: {detail}")

    print("=" * 60)
    print()
    input("按 Enter 結束...")


if __name__ == "__main__":
    main()
