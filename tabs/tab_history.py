"""
歷史紀���分頁
"""

import customtkinter as ctk
from tkinter import ttk, messagebox
import json, re

from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "userdata"
LOG_FILE   = CONFIG_DIR / "history.jsonl"
DICT_FILE  = CONFIG_DIR / "smart_dict.json"

ACCENT  = "#1D9E75"
ACCENT2 = "#17876A"
BG      = "#1a1a1a"
CARD    = "#242424"
TEXT    = "#e8e8e8"
DIM     = "#888888"
INPUT   = "#2e2e2e"
RED     = "#e05555"

FONT_TITLE = ("Microsoft YaHei", 18, "bold")
FONT_HEAD  = ("Microsoft YaHei", 13, "bold")
FONT_BODY  = ("Microsoft YaHei", 12)
FONT_SMALL = ("Microsoft YaHei", 10)


class TabHistory(ctk.CTkFrame):
    _HIST_PAGE_SIZE = 25

    def __init__(self, parent, dashboard):
        super().__init__(parent, fg_color=BG, corner_radius=0)
        self.dashboard = dashboard
        self._hist_page = 0
        self._hist_data = []
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(20, 2))
        ctk.CTkLabel(hdr, text="歷史紀錄", font=FONT_TITLE,
                     text_color=TEXT).pack(side="left")
        ctk.CTkButton(hdr, text="\U0001f504 重建詞庫",
                      fg_color=INPUT, hover_color="#3a3a3a",
                      text_color=TEXT,
                      font=FONT_SMALL, corner_radius=8, height=30, width=100,
                      command=self._rebuild_vocab).pack(side="right")
        self._hist_count_label = ctk.CTkLabel(hdr, text="",
                                               font=FONT_SMALL, text_color=DIM)
        self._hist_count_label.pack(side="right", padx=10)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=(4, 10), side="bottom")

        frame = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=16, pady=(2, 0))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("H.Treeview",
                        background=CARD, foreground=TEXT,
                        fieldbackground=CARD,
                        font=("Microsoft YaHei", 12),
                        rowheight=36)
        style.configure("H.Treeview.Heading",
                        background="#2e2e2e", foreground=ACCENT,
                        font=("Microsoft YaHei", 12, "bold"))
        style.map("H.Treeview", background=[("selected", ACCENT)])

        cols = ("時間", "語言", "文字", "字數")
        self._hist_tree = ttk.Treeview(frame, columns=cols,
                                        show="headings", style="H.Treeview",
                                        selectmode="browse")
        for col, w in zip(cols, [168, 85, 0, 70]):
            self._hist_tree.heading(col, text=col)
            self._hist_tree.column(col, width=w, anchor="w",
                                   stretch=(col == "文字"))
        self._hist_tree.bind("<Double-1>", lambda e: self._edit_entry())

        vsb = ttk.Scrollbar(frame, orient="vertical",
                             command=self._hist_tree.yview)
        self._hist_tree.configure(yscrollcommand=vsb.set)
        self._hist_tree.pack(side="left", fill="both", expand=True, padx=(12,0), pady=12)
        vsb.pack(side="right", fill="y", pady=12, padx=(0,8))

        ctk.CTkButton(foot, text="\u270f  修正", width=90,
                      fg_color=INPUT, hover_color=ACCENT2,
                      text_color=TEXT, font=FONT_BODY,
                      corner_radius=8, height=34,
                      command=self._edit_entry).pack(side="left", padx=(0, 8))
        ctk.CTkButton(foot, text="\U0001f5d1  刪除", width=90,
                      fg_color=INPUT, hover_color=RED,
                      text_color=TEXT, font=FONT_BODY,
                      corner_radius=8, height=34,
                      command=self._delete_entry).pack(side="left", padx=(0, 24))

        ctk.CTkButton(foot, text="下一頁 \u203a", width=90,
                      fg_color=INPUT, hover_color="#3a3a3a",
                      text_color=TEXT, font=FONT_BODY,
                      corner_radius=8, height=34,
                      command=self._hist_next).pack(side="right")
        self._hist_page_label = ctk.CTkLabel(foot, text="第 1 / 1 頁",
                                              font=FONT_BODY, text_color=DIM)
        self._hist_page_label.pack(side="right", padx=10)
        ctk.CTkButton(foot, text="\u2039 上一頁", width=90,
                      fg_color=INPUT, hover_color="#3a3a3a",
                      text_color=TEXT, font=FONT_BODY,
                      corner_radius=8, height=34,
                      command=self._hist_prev).pack(side="right")

    # ── 資料方法 ─────────────────────────────────────────────────────────────
    def refresh(self):
        self._hist_data = []
        try:
            if LOG_FILE.exists():
                lines = [l for l in LOG_FILE.read_text(
                    encoding="utf-8").splitlines() if l.strip()]
                for line in reversed(lines):
                    try:
                        self._hist_data.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass
        self._hist_page = 0
        total = len(self._hist_data)
        self._hist_count_label.configure(text=f"共 {total} 筆")
        self._render_page()

    def _render_page(self):
        for item in self._hist_tree.get_children():
            self._hist_tree.delete(item)
        ps    = self._HIST_PAGE_SIZE
        total = len(self._hist_data)
        pages = max(1, (total + ps - 1) // ps)
        start = self._hist_page * ps
        end   = min(start + ps, total)
        for r in self._hist_data[start:end]:
            ts   = r.get("ts","")[:19].replace("T"," ")
            lang = r.get("lang","")
            text = r.get("text","")
            chars = r.get("chars", len(text))
            self._hist_tree.insert("", "end",
                iid=r.get("ts",""),
                values=(ts, lang, text, chars))
        self._hist_page_label.configure(
            text=f"第 {self._hist_page+1} / {pages} 頁")

    def _hist_prev(self):
        if self._hist_page > 0:
            self._hist_page -= 1
            self._render_page()

    def _hist_next(self):
        ps    = self._HIST_PAGE_SIZE
        total = len(self._hist_data)
        pages = max(1, (total + ps - 1) // ps)
        if self._hist_page < pages - 1:
            self._hist_page += 1
            self._render_page()

    def _get_selected_record(self):
        sel = self._hist_tree.selection()
        if not sel:
            messagebox.showwarning("快打 SmarType", "請先選取一筆紀錄")
            return None
        ts = sel[0]
        for r in self._hist_data:
            if r.get("ts","") == ts:
                return r
        return None

    def _edit_entry(self):
        r = self._get_selected_record()
        if r is None:
            return
        dlg = ctk.CTkToplevel(self)
        dlg.title("修正紀錄")
        dlg.geometry("640x280")
        dlg.configure(fg_color=BG)
        dlg.grab_set()
        dlg.resizable(True, False)

        ts = r.get("ts","")[:19].replace("T"," ")
        ctk.CTkLabel(dlg, text=f"修正  {ts}", font=FONT_HEAD,
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 8))
        txt = ctk.CTkTextbox(dlg, font=FONT_BODY, fg_color=INPUT,
                              text_color=TEXT, height=120, wrap="word")
        txt.insert("1.0", r.get("text",""))
        txt.pack(fill="x", padx=20, pady=(0, 12))
        txt.focus()

        def _save():
            new_text = txt.get("1.0","end").strip()
            if not new_text:
                messagebox.showwarning("快打 SmarType", "文字不能為空")
                return
            r["text"]  = new_text
            r["chars"] = len(new_text)
            self._save_history_data()
            self.refresh()
            dlg.destroy()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(anchor="e", padx=20, pady=(0, 16))
        ctk.CTkButton(btn_row, text="儲存", width=90,
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=_save).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="取消", width=90,
                      fg_color=INPUT, hover_color="#3a3a3a",
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=dlg.destroy).pack(side="left")

    def _delete_entry(self):
        r = self._get_selected_record()
        if r is None:
            return
        ts   = r.get("ts","")[:19].replace("T"," ")
        text = r.get("text","")[:30]
        if not messagebox.askyesno("快打 SmarType",
                f"確定刪除這筆紀錄？\n{ts}  {text}…"):
            return
        self._hist_data.remove(r)
        self._save_history_data()
        total = len(self._hist_data)
        self._hist_count_label.configure(text=f"共 {total} 筆")
        ps    = self._HIST_PAGE_SIZE
        pages = max(1, (total + ps - 1) // ps)
        if self._hist_page >= pages:
            self._hist_page = pages - 1
        self._render_page()

    def _save_history_data(self):
        try:
            lines = [json.dumps(r, ensure_ascii=False) for r in reversed(self._hist_data)]
            LOG_FILE.write_text("\n".join(lines) + ("\n" if lines else ""),
                                encoding="utf-8")
        except Exception as e:
            messagebox.showerror("快打 SmarType", f"儲存失敗：{e}")

    def _rebuild_vocab(self):
        if not messagebox.askyesno("快打 SmarType",
                "重建詞庫將清除舊詞庫，並從現有歷史重新統計高頻詞。\n確定繼續？"):
            return
        word_count: dict = {}
        for r in self._hist_data:
            text = r.get("text", "")
            for w in re.findall(r'[\u4e00-\u9fff]{2,6}|[A-Za-z]{3,}', text):
                word_count[w] = word_count.get(w, 0) + 1
        word_count = {w: c for w, c in word_count.items() if c >= 2}
        try:
            DICT_FILE.write_text(
                json.dumps({"words": word_count}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            messagebox.showinfo("快打 SmarType",
                f"詞庫重建完成，共 {len(word_count)} 個有效詞彙（出現 ≥2 次）")
        except Exception as e:
            messagebox.showerror("快打 SmarType", f"重建失敗：{e}")
