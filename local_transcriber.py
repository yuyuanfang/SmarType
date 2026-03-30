"""
快打 SmarType — 本地轉錄模組 local_transcriber.py
使用 faster-whisper，完全離線，零費用。

首次使用自動下載模型（約 1.5GB），存於 userdata/models/
後續啟動直接從本地載入，無需網路。
"""

import io, wave, threading, time
from pathlib import Path

CONFIG_DIR  = Path(__file__).parent / "userdata"
MODELS_DIR  = CONFIG_DIR / "models"

# 預設使用 medium（精度/速度平衡）
# 可選：tiny / base / small / medium / large-v3 / large-v3-turbo
DEFAULT_MODEL = "medium"

_model       = None
_model_lock  = threading.Lock()
_model_name  = None


def _log(msg):
    try:
        ts = time.strftime("%H:%M:%S")
        with open(CONFIG_DIR / "debug.log", "a", encoding="utf-8") as f:
            f.write(f"[{ts}][local] {msg}\n")
    except Exception:
        pass


def load_model(model_size: str = DEFAULT_MODEL, force_reload: bool = False):
    """
    載入 faster-whisper 模型（單例，執行緒安全）。
    首次呼叫會自動下載到 userdata/models/。
    """
    global _model, _model_name
    with _model_lock:
        if _model is not None and not force_reload and _model_name == model_size:
            return _model
        try:
            from faster_whisper import WhisperModel
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            _log(f"loading model: {model_size} ...")
            t0 = time.time()
            _model = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",          # CPU 最佳化
                download_root=str(MODELS_DIR),
            )
            _model_name = model_size
            _log(f"model loaded in {time.time()-t0:.1f}s")
            return _model
        except Exception as e:
            _log(f"load_model error: {e}")
            return None


def transcribe_local(wav_bytes: bytes,
                     language: str = "zh",
                     prompt: str = "",
                     model_size: str = DEFAULT_MODEL) -> str:
    """
    用本地 faster-whisper 轉錄 WAV bytes。
    回傳轉錄文字；失敗回傳空字串。
    """
    model = load_model(model_size)
    if model is None:
        _log("model not loaded, skip local transcribe")
        return ""

    try:
        # faster-whisper 接受檔案路徑或 file-like object
        audio_io = io.BytesIO(wav_bytes)

        segments, info = model.transcribe(
            audio_io,
            language=language,
            initial_prompt=prompt or None,
            beam_size=5,
            vad_filter=True,               # 內建 VAD，自動去靜音
            vad_parameters=dict(
                min_silence_duration_ms=300,
            ),
        )

        text = "".join(seg.text for seg in segments).strip()
        _log(f"local transcribe: lang={info.language} prob={info.language_probability:.2f} → {repr(text[:60])}")
        return text

    except Exception as e:
        _log(f"transcribe_local error: {e}")
        return ""


def preload_async(model_size: str = DEFAULT_MODEL):
    """背景預載模型（程式啟動時呼叫，不阻塞主執行緒）"""
    threading.Thread(
        target=load_model,
        args=(model_size,),
        daemon=True
    ).start()


def is_loaded(model_size: str = DEFAULT_MODEL) -> bool:
    return _model is not None and _model_name == model_size


# ── 測試 ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"載入模型 {DEFAULT_MODEL}...")
    m = load_model(DEFAULT_MODEL)
    if m:
        print("✅ 模型載入成功，可以離線使用")
        print(f"   模型存於：{MODELS_DIR}")
    else:
        print("❌ 模型載入失敗，請確認 faster-whisper 已安裝")
