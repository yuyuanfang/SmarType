"""
設定管理模組 — 路徑常數、設定讀寫、除錯日誌
"""

import os, sys, json, datetime
from pathlib import Path

# ── 路徑常數 ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
CONFIG_DIR  = BASE_DIR / "userdata"
CONFIG_FILE = CONFIG_DIR / "config.json"
VOCAB_FILE  = CONFIG_DIR / "vocabulary.json"
LOG_FILE    = CONFIG_DIR / "history.jsonl"

DEFAULT_CONFIG = {
    "api_key":       "",         # OpenAI（備用）
    "groq_api_key":  "",         # Groq（主力）
    "hotkey":        "right shift",
    "language":      "zh",
    "insert_method": "clipboard",
    "auto_lang":     True,
    "default_lang":  "zh-TW",
    "mic_index":     None,
    "auto_start":    False,
    "segment_secs":  3,          # 分段轉錄間隔（秒）
    "llm_polish":    False,      # 是否啟用 LLM 潤色（去贅字+糾錯），需 OpenAI/Gemini key
    "gemini_api_key": "",        # Gemini API key（備用）
}


# ── 設定讀寫 ──────────────────────────────────────────────────────────────────
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


# ── 除錯日誌 ─────────────────────────────────────────────────────────────────
DEBUG_LOG     = CONFIG_DIR / "debug.log"
DEBUG_LOG_MAX = 5 * 1024 * 1024  # 5 MB → 輪替

def _dbg(msg: str):
    """寫除錯日誌到 userdata/debug.log（超過 5MB 自動輪替）"""
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


# ── 系統工具 ──────────────────────────────────────────────────────────────────
def disable_sticky_keys():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Control Panel\Accessibility\StickyKeys",
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "Flags", 0, winreg.REG_SZ, "58")
        winreg.CloseKey(key)
        key2 = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                              r"Control Panel\Accessibility\Keyboard Response",
                              0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key2, "Flags", 0, winreg.REG_SZ, "122")
        winreg.CloseKey(key2)
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
                              f'"{sys.executable}" "{Path(__file__).parent / "dictation.py"}"')
        else:
            try:
                winreg.DeleteValue(key, "SmarType")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


# ── 詞彙資料庫 ────────────────────────────────────────────────────────────────
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
        from smart_vocab import get_prompt_words
        if lang in ("zh-TW", "en"):
            base = "台灣國語，繁體中文，程式開發與技術討論，專有名詞保留英文。"
        elif lang == "zh-CN":
            base = "簡體中文，技術討論，專有名詞保留英文。"
        else:
            base = ""
        parts = [base] if base else []
        prompt_words = get_prompt_words(10)
        if prompt_words:
            parts.append(f"詞：{prompt_words}。")
        prompt = "".join(parts)
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
