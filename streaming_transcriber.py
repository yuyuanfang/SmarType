"""
Sherpa-ONNX 串流語音辨識引擎。
每幀音頻送入 → 有新文字立刻回調 → 跑馬燈逐字更新。
"""

import os
import struct
import numpy as np
import sherpa_onnx

_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "models", "sherpa-onnx-streaming-paraformer-bilingual-zh-en")

_recognizer = None   # 全域單例


def _ensure_recognizer():
    global _recognizer
    if _recognizer is not None:
        return _recognizer
    _recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
        tokens=os.path.join(_MODEL_DIR, "tokens.txt"),
        encoder=os.path.join(_MODEL_DIR, "encoder.int8.onnx"),
        decoder=os.path.join(_MODEL_DIR, "decoder.int8.onnx"),
        num_threads=2,
        sample_rate=16000,
        feature_dim=80,
        enable_endpoint_detection=True,
        rule1_min_trailing_silence=2.4,   # 長靜音 → endpoint
        rule2_min_trailing_silence=0.8,   # 說完一句後短靜音 → endpoint
        rule3_min_utterance_length=20.0,
        decoding_method="greedy_search",
        provider="cpu",
    )
    return _recognizer


class StreamingSession:
    """
    一次錄音對應一個 Session。
    用法：
        session = StreamingSession()
        # 在 PyAudio callback 中：
        session.feed_pcm(in_data)    # bytes, int16, 16kHz mono
        text = session.current_text  # 隨時取得最新識別結果
    """

    def __init__(self, on_text=None):
        """
        on_text: 回調函數 fn(text: str)，有新文字時立刻觸發。
                 從音頻回調線程中調用，需線程安全。
        """
        self._recognizer = _ensure_recognizer()
        self._stream = self._recognizer.create_stream()
        self._on_text = on_text
        self._last_text = ""
        self.current_text = ""      # 目前累積的識別文字
        self._final_parts = []      # endpoint 確認的句子

    def feed_pcm(self, raw_bytes: bytes):
        """
        送入 PCM 音頻數據（int16, 16kHz, mono）。
        在 PyAudio stream_callback 中直接調用即可。
        """
        # int16 bytes → float32 numpy array (sherpa-onnx 需要 float32)
        n_samples = len(raw_bytes) // 2
        samples = np.array(
            struct.unpack(f"<{n_samples}h", raw_bytes),
            dtype=np.float32) / 32768.0

        self._stream.accept_waveform(16000, samples)

        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)

        # 取得目前的部分識別結果
        partial = self._recognizer.get_result(self._stream).strip()

        # 組合：已確認的句子 + 當前部分結果
        full_text = "".join(self._final_parts) + partial
        self.current_text = full_text

        # 有新字才回調
        if full_text != self._last_text and full_text:
            self._last_text = full_text
            if self._on_text:
                self._on_text(full_text)

        # 檢查 endpoint（說完一句話的停頓）
        if self._recognizer.is_endpoint(self._stream):
            if partial:
                self._final_parts.append(partial)
            self._recognizer.reset(self._stream)

    def reset(self):
        """重置 session（開始新一次錄音）"""
        self._stream = self._recognizer.create_stream()
        self._last_text = ""
        self.current_text = ""
        self._final_parts = []


def preload():
    """預載模型（啟動時背景調用）"""
    try:
        _ensure_recognizer()
        return True
    except Exception:
        return False
