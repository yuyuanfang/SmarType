"""
字典管理分頁
"""

import customtkinter as ctk
from tkinter import ttk, messagebox
import json

from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "userdata"
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


class TabVocab(ctk.CTkFrame):
    def __init__(self, parent, dashboard):
        super().__init__(parent, fg_color=BG, corner_radius=0)
        self.dashboard = dashboard
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="智能字典", font=FONT_TITLE,
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(20, 2))
        ctk.CTkLabel(self, text="由每次語音輸入自動學習累積 · 支援手動新增/刪除/修改",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=20, pady=(0, 8))

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(toolbar, text="詞彙：", font=FONT_BODY,
                     text_color=DIM).pack(side="left")
        self._vocab_entry = ctk.CTkEntry(toolbar, width=160, font=FONT_BODY,
                                          fg_color=INPUT, placeholder_text="輸入新詞彙")
        self._vocab_entry.pack(side="left", padx=(0, 6))
        ctk.CTkButton(toolbar, text="+ 新增", width=70,
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_SMALL, corner_radius=8, height=30,
                      command=self._add_vocab_word).pack(side="left", padx=(0, 4))
        ctk.CTkButton(toolbar, text="修改", width=60,
                      fg_color=INPUT, hover_color="#3a3a3a", text_color=TEXT,
                      font=FONT_SMALL, corner_radius=8, height=30,
                      command=self._edit_vocab_word).pack(side="left", padx=(0, 4))
        ctk.CTkButton(toolbar, text="刪除", width=60,
                      fg_color=INPUT, hover_color=RED, text_color=TEXT,
                      font=FONT_SMALL, corner_radius=8, height=30,
                      command=self._del_vocab_word).pack(side="left")
        self._vocab_count_label = ctk.CTkLabel(toolbar, text="",
                                                font=FONT_SMALL, text_color=DIM)
        self._vocab_count_label.pack(side="right")

        vocab_frame = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        vocab_frame.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        style = ttk.Style()
        style.configure("V.Treeview",
                        background=CARD, foreground=TEXT,
                        fieldbackground=CARD,
                        font=("Microsoft YaHei", 12),
                        rowheight=32)
        style.configure("V.Treeview.Heading",
                        background="#2e2e2e", foreground=ACCENT,
                        font=("Microsoft YaHei", 12, "bold"))
        style.map("V.Treeview", background=[("selected", ACCENT)])

        vcols = ("詞彙", "頻次")
        self._vocab_tree = ttk.Treeview(vocab_frame, columns=vcols,
                                         show="headings", style="V.Treeview",
                                         selectmode="browse")
        self._vocab_tree.heading("詞彙", text="詞彙")
        self._vocab_tree.heading("頻次", text="頻次")
        self._vocab_tree.column("詞彙", width=300, anchor="w", stretch=True)
        self._vocab_tree.column("頻次", width=80, anchor="center", stretch=False)

        vsb = ttk.Scrollbar(vocab_frame, orient="vertical",
                             command=self._vocab_tree.yview)
        self._vocab_tree.configure(yscrollcommand=vsb.set)
        self._vocab_tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=10)
        vsb.pack(side="right", fill="y", padx=(0, 4), pady=10)

        # 糾正映射區
        ctk.CTkLabel(self, text="糾正映射（聽到 → 改成）",
                     font=FONT_HEAD, text_color=TEXT).pack(anchor="w", padx=20, pady=(4, 4))

        corr_toolbar = ctk.CTkFrame(self, fg_color="transparent")
        corr_toolbar.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(corr_toolbar, text="聽到：", font=FONT_SMALL,
                     text_color=DIM).pack(side="left")
        self._corr_from = ctk.CTkEntry(corr_toolbar, width=120, font=FONT_BODY,
                                        fg_color=INPUT, placeholder_text="錯誤詞")
        self._corr_from.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(corr_toolbar, text="\u2192", font=FONT_BODY,
                     text_color=DIM).pack(side="left", padx=4)
        self._corr_to = ctk.CTkEntry(corr_toolbar, width=120, font=FONT_BODY,
                                      fg_color=INPUT, placeholder_text="正確詞")
        self._corr_to.pack(side="left", padx=(0, 6))
        ctk.CTkButton(corr_toolbar, text="+ 新增", width=70,
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_SMALL, corner_radius=8, height=30,
                      command=self._add_correction).pack(side="left", padx=(0, 4))
        ctk.CTkButton(corr_toolbar, text="刪除", width=60,
                      fg_color=INPUT, hover_color=RED, text_color=TEXT,
                      font=FONT_SMALL, corner_radius=8, height=30,
                      command=self._del_correction).pack(side="left")

        corr_frame = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        corr_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        style.configure("C.Treeview",
                        background=CARD, foreground=TEXT,
                        fieldbackground=CARD,
                        font=("Microsoft YaHei", 12),
                        rowheight=32)
        style.configure("C.Treeview.Heading",
                        background="#2e2e2e", foreground=ACCENT,
                        font=("Microsoft YaHei", 12, "bold"))
        style.map("C.Treeview", background=[("selected", ACCENT)])

        ccols = ("聽到", "改成")
        self._corr_tree = ttk.Treeview(corr_frame, columns=ccols,
                                        show="headings", style="C.Treeview",
                                        selectmode="browse", height=5)
        self._corr_tree.heading("聽到", text="聽到")
        self._corr_tree.heading("改成", text="改成")
        self._corr_tree.column("聽到", width=200, anchor="w", stretch=True)
        self._corr_tree.column("改成", width=200, anchor="w", stretch=True)

        csb = ttk.Scrollbar(corr_frame, orient="vertical",
                             command=self._corr_tree.yview)
        self._corr_tree.configure(yscrollcommand=csb.set)
        self._corr_tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=8)
        csb.pack(side="right", fill="y", padx=(0, 4), pady=8)

    def _add_vocab_word(self):
        word = self._vocab_entry.get().strip()
        if not word:
            return
        try:
            data = json.loads(DICT_FILE.read_text(encoding="utf-8")) if DICT_FILE.exists() else {"words": {}}
            data.setdefault("words", {})[word] = data.get("words", {}).get(word, 0) + 1
            DICT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            vocab_file = CONFIG_DIR / "vocabulary.json"
            if vocab_file.exists():
                vdata = json.loads(vocab_file.read_text(encoding="utf-8"))
                cw = vdata.get("custom_words", [])
                if word not in cw:
                    cw.append(word)
                    vdata["custom_words"] = cw
                    vocab_file.write_text(json.dumps(vdata, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._vocab_entry.delete(0, "end")
        self.refresh()

    def _del_vocab_word(self):
        sel = self._vocab_tree.selection()
        if not sel:
            return
        word = self._vocab_tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("刪除詞彙", f"確定刪除「{word}」？"):
            return
        try:
            data = json.loads(DICT_FILE.read_text(encoding="utf-8"))
            data.get("words", {}).pop(word, None)
            DICT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self.refresh()

    def _edit_vocab_word(self):
        sel = self._vocab_tree.selection()
        if not sel:
            return
        old_word, count_str = self._vocab_tree.item(sel[0], "values")
        dlg = ctk.CTkToplevel(self)
        dlg.title("修改詞彙")
        dlg.geometry("350x150")
        dlg.transient(self)
        dlg.grab_set()
        ctk.CTkLabel(dlg, text="修改詞彙：", font=FONT_BODY).pack(padx=14, pady=(14, 4))
        entry = ctk.CTkEntry(dlg, width=280, font=FONT_BODY, fg_color=INPUT)
        entry.insert(0, old_word)
        entry.pack(padx=14, pady=4)
        def _save():
            new_word = entry.get().strip()
            if new_word and new_word != old_word:
                try:
                    data = json.loads(DICT_FILE.read_text(encoding="utf-8"))
                    words = data.get("words", {})
                    cnt = words.pop(old_word, 0)
                    words[new_word] = cnt
                    DICT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            dlg.destroy()
            self.refresh()
        ctk.CTkButton(dlg, text="儲存", fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_BODY, corner_radius=8, height=32,
                      command=_save).pack(pady=10)

    def _add_correction(self):
        frm = self._corr_from.get().strip()
        to = self._corr_to.get().strip()
        if not frm or not to:
            return
        try:
            vocab_file = CONFIG_DIR / "vocabulary.json"
            vdata = json.loads(vocab_file.read_text(encoding="utf-8")) if vocab_file.exists() else {}
            corr = vdata.get("corrections", {})
            corr[frm] = to
            vdata["corrections"] = corr
            vocab_file.write_text(json.dumps(vdata, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._corr_from.delete(0, "end")
        self._corr_to.delete(0, "end")
        self.refresh()

    def _del_correction(self):
        sel = self._corr_tree.selection()
        if not sel:
            return
        frm = self._corr_tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("刪除糾正", f"確定刪除「{frm}」的糾正規則？"):
            return
        try:
            vocab_file = CONFIG_DIR / "vocabulary.json"
            vdata = json.loads(vocab_file.read_text(encoding="utf-8"))
            vdata.get("corrections", {}).pop(frm, None)
            vocab_file.write_text(json.dumps(vdata, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self.refresh()

    def refresh(self):
        for item in self._vocab_tree.get_children():
            self._vocab_tree.delete(item)
        try:
            if DICT_FILE.exists():
                data  = json.loads(DICT_FILE.read_text(encoding="utf-8"))
                words = sorted(data.get("words", {}).items(), key=lambda x: -x[1])
                self._vocab_count_label.configure(text=f"共 {len(words)} 個詞")
                for w, cnt in words:
                    self._vocab_tree.insert("", "end", values=(w, cnt))
        except Exception:
            pass
        for item in self._corr_tree.get_children():
            self._corr_tree.delete(item)
        try:
            vocab_file = CONFIG_DIR / "vocabulary.json"
            if vocab_file.exists():
                vdata = json.loads(vocab_file.read_text(encoding="utf-8"))
                for frm, to in vdata.get("corrections", {}).items():
                    self._corr_tree.insert("", "end", values=(frm, to))
        except Exception:
            pass
