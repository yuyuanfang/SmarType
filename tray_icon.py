"""
系統匣模組 — pystray 圖示、右鍵選單、麥克風選擇器
"""

import tkinter as tk
from PIL import Image, ImageDraw

from audio_recorder import list_microphones


def make_tray_icon(state="ready"):
    """產生系統匣圖示（不同狀態不同顏色）"""
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


def show_mic_selector(current_index, on_select):
    """彈出麥克風選擇視窗"""
    mics = list_microphones()
    if not mics:
        return

    win = tk.Tk()
    win.title("選擇麥克風 · 快打 SmarType")
    win.configure(bg="#1a1a1a")
    win.attributes("-topmost", True)
    win.resizable(False, False)
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"420x160+{(sw-420)//2}+{(sh-160)//2}")

    tk.Label(win, text="選擇錄音麥克風",
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

    tk.Button(win, text="確認", command=confirm,
              bg="#1D9E75", fg="#fff",
              font=("Microsoft YaHei", 10),
              relief="flat", padx=20, pady=4).pack(pady=6)
    win.mainloop()
