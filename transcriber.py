"""
語音轉錄模組 — Gemini / Groq / OpenAI / 本地 fallback
"""

import io, time, datetime

from config_manager import _dbg

# ── 可選依賴 ──────────────────────────────────────────────────────────────────
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


# ── 轉錄器 ───────────────────────────────────────────────────────────────────
class Transcriber:
    def __init__(self, groq_key="", openai_key="", gemini_key=""):
        self.groq_client   = Groq(api_key=groq_key) if groq_key and GROQ_AVAILABLE else None
        valid_oai = openai_key and openai_key.startswith("sk-") and OPENAI_AVAILABLE
        self.openai_client = OpenAI(api_key=openai_key) if valid_oai else None
        self.gemini_client = None
        if gemini_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=gemini_key)
            except ImportError:
                pass
        # API 狀態追蹤（供托盤選單顯示）
        self.last_model    = "--"
        self.last_error    = None
        self.last_success  = None
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
        safe_prompt = (prompt or "台灣繁體中文。")[:120]
        _dbg(f"Groq call: wav={len(wav_bytes)}B, prompt={repr(safe_prompt[:40])}")

        self.last_error = None
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
                if "429" in str(e) or "rate_limit" in str(e).lower() or "RateLimitError" in err_name:
                    self.last_error = "rate_limit"
                    _dbg("RATE LIMITED — stopping Groq attempts")
                    break
                elif "401" in str(e) or "auth" in str(e).lower():
                    self.last_error = "auth"
                else:
                    self.last_error = "network"

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
                lang_hint = "簡體中文"
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
