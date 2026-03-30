"""
快打 SmarType v6 — 主程式入口
組裝各模組、啟動主迴圈
"""

import os, sys, json, time, re, threading, datetime, ctypes, traceback
from pathlib import Path
import tkinter as tk

import keyboard
import pystray
from pystray import MenuItem as Item

from config_manager import (
    CONFIG_DIR, load_config, save_config, _dbg,
    disable_sticky_keys, set_autostart, VocabularyDB,
)
from audio_recorder import (
    Recorder, inject_text, get_chat_context, load_history_context,
)
from transcriber import Transcriber
from overlay_ui import CenterBall
from tray_icon import make_tray_icon, show_mic_selector

from window_detector import get_active_window_info
from smart_vocab import run_background_update
from converter import convert
from diary_engine import context_aware_post_process


# ── 主應用 ────────────────────────────────────────────────────────────────────
class SmarTypeApp:
    def __init__(self):
        self.config       = load_config()
        self.vocab        = VocabularyDB()
        self.recorder     = Recorder(mic_index=self.config.get("mic_index"))
        self.is_recording = False
        self.last_window  = {}
        self.ball         = CenterBall()
        self.tray         = None
        self._seg_texts   = []
        self._processing  = False
        self._press_guard   = threading.Lock()
        self._release_guard = threading.Lock()

        self.transcriber = Transcriber(
            groq_key=self.config.get("groq_api_key", ""),
            openai_key=self.config.get("api_key", ""),
            gemini_key=self.config.get("gemini_api_key", ""),
        )

        disable_sticky_keys()

    # ── 托盤 ──────────────────────────────────────────────────────────────────
    def _api_status_label(self):
        t = self.transcriber
        if t.last_error == "rate_limit":
            return "\u26a0\ufe0f Groq 額度已滿"
        if t.last_error == "auth":
            return "\u274c API Key 錯誤"
        if t.last_success:
            short = t.last_model.replace("whisper-large-v3-", "")
            return f"\u2705 {short} \u00b7 {t.last_success}"
        return "\u23f3 尚未使用"

    def _build_menu(self):
        return pystray.Menu(
            Item(lambda _: f"快打 SmarType  \u00b7  {self._api_status_label()}",
                 None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("\U0001f5a5  顯示管理介面",  self._on_show_dashboard),
            pystray.Menu.SEPARATOR,
            Item("\u274c  退出",          self._on_quit),
        )

    _dashboard_proc = None

    def _on_show_dashboard(self, icon=None, item=None):
        import subprocess
        if self._dashboard_proc and self._dashboard_proc.poll() is None:
            try:
                signal_file = Path(__file__).parent / "userdata" / "dashboard_signal.json"
                signal_file.write_text('{"cmd": "show"}', encoding="utf-8")
                _dbg("dashboard signal: show (already running)")
            except Exception:
                pass
            return
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
        clean = re.sub(r'[，。,.\s！？!?、]', '', text)
        if len(clean) >= 4:
            unique_chars = set(clean)
            if len(unique_chars) <= 2:
                _dbg(f"hallucination: repeated chars in: {repr(text[:60])}")
                return True
        return False

    # ── 串流 ASR 回呼（每幀音頻觸發，逐字更新跑馬燈）─────────────────────────
    def _on_streaming_text(self, text: str):
        if not self.is_recording:
            return
        self.ball.safe_append(text)

    # ── 錄音開始 ──────────────────────────────────────────────────────────────
    def on_press(self):
        if self.is_recording:
            return
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

    # ── 錄音結束 ──────────────────────────────────────────────────────────────
    def on_release(self):
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
        if self._processing:
            _dbg("on_release: BLOCKED by _processing=True, dropping this release")
            return
        _dbg("on_release: stopping recorder...")
        self.is_recording = False
        self._processing  = True
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

                final_text = ""
                if wav_bytes:
                    try:
                        import audioop
                        wav_audio = wav_bytes[44:]
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
                        need_post = (
                            (target_lang == "en" and any('\u4e00' <= c <= '\u9fff' for c in final_text))
                            or self.config.get("llm_polish", False)
                        )
                        if need_post:
                            try:
                                app_name = self.last_window.get("process", "")
                                win_title = self.last_window.get("title", "")
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
                        _dbg("wav_bytes=None → 錄音太短")
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

                method = self.config.get("insert_method", "clipboard")
                _dbg(f"inject_text: method={method}")
                inject_text(final_text, method)
                _dbg("inject done")

                try:
                    from diary_engine import process_entry
                    process_entry(final_text, window_info=self.last_window)
                except Exception as de:
                    _dbg(f"diary process_entry error: {de}")

                self.vocab.log_session(
                    final_text, target_lang,
                    self.last_window.get("process", "unknown"))

                self._processing = False
                _dbg("_processing reset (before sleep)")
                self._write_status("done", final_text)

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
                self._processing = False
                self._write_status("idle")

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

    # ── 熱鍵輪詢 ──────────────────────────────────────────────────────────────
    def _poll_hotkey(self):
        hotkey       = self.config.get("hotkey", "right shift")
        keys         = [k.strip() for k in hotkey.split("+")]
        was_pressed  = False
        release_lock = threading.Lock()

        while True:
            try:
                currently = all(keyboard.is_pressed(k) for k in keys)

                if currently and not was_pressed:
                    was_pressed = True
                    self.on_press()

                elif not currently and was_pressed:
                    was_pressed = False
                    if release_lock.acquire(blocking=False):
                        try:
                            self.on_release()
                        finally:
                            def unlock():
                                time.sleep(0.5)
                                release_lock.release()
                            threading.Thread(target=unlock, daemon=True).start()

            except Exception:
                pass
            time.sleep(0.02)

    def _listen_enter(self):
        """監聽 Enter 鍵，在發送前擷取剪貼簿內容更新詞典"""
        def on_enter():
            try:
                import pyperclip
                text = pyperclip.paste()
                if text and len(text) > 3:
                    threading.Thread(
                        target=self._learn_from_text,
                        args=(text,), daemon=True).start()
            except Exception:
                pass

        keyboard.on_press_key("enter", lambda _: on_enter())
        keyboard.on_press_key("return", lambda _: on_enter())

    def _learn_from_text(self, text: str):
        """從一段文字中學習詞彙"""
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

    # ── 啟動 ──────────────────────────────────────────────────────────────────
    def run(self):
        # 單實例鎖（防止多進程同時執行出現雙球）
        try:
            self._mutex = ctypes.windll.kernel32.CreateMutexW(
                None, True, "SmarType_v6_SingleInstance")
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                root = tk.Tk()
                root.withdraw()
                tk.messagebox.showinfo(
                    "快打 SmarType", "程序已在運行中，請查看系統托盤。")
                root.destroy()
                sys.exit(0)
        except Exception:
            pass

        if not self.config.get("groq_api_key") and not self.config.get("api_key"):
            root = tk.Tk()
            root.withdraw()
            tk.messagebox.showerror(
                "快打 SmarType",
                "未設定 API Key！\n請執行 python setup.py")
            root.destroy()
            sys.exit(1)

        _dbg("=== SmarType v6 START ===")
        _dbg(f"groq_key={'SET' if self.config.get('groq_api_key') else 'MISSING'}")
        _dbg(f"openai_key_valid={'YES' if self.config.get('api_key','').startswith('sk-') else 'NO/EMPTY (OK if using Groq)'}")
        _dbg(f"hotkey={self.config.get('hotkey','right shift')}")
        _dbg(f"mic_index={self.config.get('mic_index', 'default')}")

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

        threading.Thread(target=self._watch_control_signal, daemon=True).start()
        threading.Thread(target=self._poll_hotkey, daemon=True).start()
        threading.Thread(target=self._listen_enter, daemon=True).start()

        try:
            from diary_engine import start_daily_scheduler
            start_daily_scheduler()
            _dbg("diary scheduler started")
        except Exception as de:
            _dbg(f"diary scheduler failed: {de}")

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

        if self.config.get("use_local_model", False):
            try:
                from local_transcriber import preload_async
                preload_async(self.config.get("local_model_size", "medium"))
                _dbg("local model preloading in background")
            except Exception as le:
                _dbg(f"local model preload failed: {le}")

        self.tray = pystray.Icon(
            "SmarType",
            make_tray_icon("ready"),
            "快打 SmarType",
            menu=self._build_menu(),
        )
        threading.Thread(target=self.tray.run, daemon=True).start()

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
