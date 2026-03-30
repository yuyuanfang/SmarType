"""
跑馬燈 UI 模組 — 綠色膠囊視窗（底部居中，仿微信輸入法風格）
"""

import tkinter as tk
from window_detector import get_language_label


class CenterBall:
    """
    固定寬度膠囊條（仿微信輸入法），螢幕底部居中。
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

        # ── 膠囊背景（圓角矩形）────────────────────────────────────────────
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

        # ── 左側麥克風圓點 ─────────────────────────────────────────────────
        dot_cx = r + 6
        dot_cy = H // 2
        self._dot = self.canvas.create_oval(
            dot_cx - 11, dot_cy - 11,
            dot_cx + 11, dot_cy + 11,
            fill="white", outline="")
        self._dot_icon = self.canvas.create_text(
            dot_cx, dot_cy,
            text="\U0001f399", font=("Segoe UI Emoji", 13), fill="#1D9E75")

        # ── 即時文字（膠囊右側，支援平滑滾動）────────────────────────────
        self._txt_x0   = dot_cx + 22
        self._txt_xmax = W - 16
        self._txt_font = ("Microsoft YaHei", 13)

        self._live_txt = self.canvas.create_text(
            self._txt_x0, H // 2,
            text="", anchor="w",
            font=self._txt_font,
            fill="white")

        self._pulse_job    = None
        self._pulse_toggle = True
        self._last_text    = ""
        self._scroll_job   = None
        self._scroll_target_x = self._txt_x0
        self._typing_queue = []
        self._typing_job   = None
        self._displayed_text = ""
        self._full_target  = ""

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
        self.canvas.itemconfig(self._dot_icon, text="\U0001f399")
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

        self.canvas.itemconfig(self._live_txt, text=text)
        self.canvas.update_idletasks()

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
        self.canvas.itemconfig(self._dot_icon, text="\u23f3")
        hint = (self._last_text[-16:] + "  \u23f3") if self._last_text else "識別中..."
        self.canvas.itemconfig(self._live_txt, text=hint)
        self.canvas.coords(self._live_txt, self._txt_x0, self.H // 2)

    def show_result(self, text: str, lang: str):
        self._stop_pulse()
        self._cancel_scroll()
        self._cancel_typing()
        self.canvas.itemconfig(self._dot_icon, text="\u2713")
        self.canvas.itemconfig(self._live_txt, text=text)
        self.canvas.coords(self._live_txt, self._txt_x0, self.H // 2)
        self.canvas.update_idletasks()
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
        self.canvas.itemconfig(self._dot_icon, text="\u274c")
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
