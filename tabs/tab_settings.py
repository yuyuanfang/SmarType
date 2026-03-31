"""
設定分頁
"""

import customtkinter as ctk
from tkinter import ttk, messagebox
import json

from pathlib import Path

CONFIG_DIR  = Path(__file__).parent.parent / "userdata"
CONFIG_FILE = CONFIG_DIR / "config.json"
RULES_FILE  = CONFIG_DIR / "app_rules.json"

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
FONT_MONO  = ("Consolas", 11)


def _load_config():
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class TabSettings(ctk.CTkFrame):
    def __init__(self, parent, dashboard):
        super().__init__(parent, fg_color=BG, corner_radius=0)
        self.dashboard = dashboard
        self.config_data = dashboard.config_data
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="設定", font=FONT_TITLE,
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(20, 10))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                         corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # API Keys
        api_card = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=12)
        api_card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(api_card, text="API 金鑰", font=FONT_HEAD,
                     text_color=TEXT).pack(anchor="w", padx=18, pady=(16, 10))
        for lbl, key in [("Groq API Key",   "groq_api_key"),
                          ("GLM API Key",    "glm_api_key"),
                          ("Gemini API Key", "gemini_api_key"),
                          ("OpenAI API Key", "api_key")]:
            v = self.config_data.get(key, "")
            disp = v[:10] + "\u00b7\u00b7\u00b7\u00b7\u00b7" + v[-4:] if len(v) > 14 else (v or "（未設定）")
            row = ctk.CTkFrame(api_card, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=5)
            ctk.CTkLabel(row, text=lbl, font=FONT_BODY,
                         text_color=DIM, width=140, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=disp, font=FONT_MONO,
                         text_color=TEXT).pack(side="left")

        ctk.CTkFrame(api_card, height=1, fg_color="#333").pack(fill="x", padx=18, pady=10)

        hk_row = ctk.CTkFrame(api_card, fg_color="transparent")
        hk_row.pack(fill="x", padx=18, pady=5)
        ctk.CTkLabel(hk_row, text="熱鍵", font=FONT_BODY,
                     text_color=DIM, width=140, anchor="w").pack(side="left")
        self._hotkey_entry = ctk.CTkEntry(hk_row, width=210, font=FONT_BODY,
                                           fg_color=INPUT)
        self._hotkey_entry.insert(0, self.config_data.get("hotkey", "right shift"))
        self._hotkey_entry.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(hk_row, text="例: right shift / ctrl+alt+r",
                     font=FONT_SMALL, text_color=DIM).pack(side="left")

        as_row = ctk.CTkFrame(api_card, fg_color="transparent")
        as_row.pack(fill="x", padx=18, pady=5)
        ctk.CTkLabel(as_row, text="開機自動啟動", font=FONT_BODY,
                     text_color=DIM, width=140, anchor="w").pack(side="left")
        self._autostart = ctk.CTkSwitch(as_row, text="",
                                         progress_color=ACCENT,
                                         button_color="white")
        if self.config_data.get("auto_start", False):
            self._autostart.select()
        self._autostart.pack(side="left")

        lp_row = ctk.CTkFrame(api_card, fg_color="transparent")
        lp_row.pack(fill="x", padx=18, pady=5)
        ctk.CTkLabel(lp_row, text="AI 自動潤色", font=FONT_BODY,
                     text_color=DIM, width=140, anchor="w").pack(side="left")
        self._llm_polish = ctk.CTkSwitch(lp_row, text="",
                                          progress_color=ACCENT,
                                          button_color="white")
        if self.config_data.get("llm_polish", True):
            self._llm_polish.select()
        self._llm_polish.pack(side="left")

        ctk.CTkButton(api_card, text="儲存所有設定",
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_BODY, corner_radius=8, height=38,
                      command=self._save_all).pack(anchor="w", padx=18, pady=(10, 18))

        # 視窗語言規則
        lang_card = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=12)
        lang_card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(lang_card, text="\U0001f310  視窗語言規則", font=FONT_HEAD,
                     text_color=TEXT).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(lang_card,
                     text="按下熱鍵的瞬間偵��前景視窗，自動切換繁體 / 簡體",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=18, pady=(0, 10))

        tree_frame = ctk.CTkFrame(lang_card, fg_color=INPUT, corner_radius=8)
        tree_frame.pack(fill="x", padx=18, pady=(0, 8))
        style2 = ttk.Style()
        style2.configure("L.Treeview",
                         background=INPUT, foreground=TEXT,
                         fieldbackground=INPUT,
                         font=("Microsoft YaHei", 12), rowheight=28)
        style2.configure("L.Treeview.Heading",
                         background="#222222", foreground=ACCENT,
                         font=("Microsoft YaHei", 12, "bold"))
        style2.map("L.Treeview", background=[("selected", ACCENT)])
        cols2 = ("視���進程 / 關鍵字", "輸出語言")
        self._rules_tree = ttk.Treeview(tree_frame, columns=cols2,
                                         show="headings", style="L.Treeview",
                                         height=7)
        self._rules_tree.heading("視窗進程 / 關鍵字", text="視窗進程 / 關鍵字")
        self._rules_tree.heading("輸出語言",           text="輸出語言")
        self._rules_tree.column("視窗進程 / 關鍵字", width=320, anchor="w")
        self._rules_tree.column("輸出語��",           width=200, anchor="center")
        vsb2 = ttk.Scrollbar(tree_frame, orient="vertical",
                              command=self._rules_tree.yview)
        self._rules_tree.configure(yscrollcommand=vsb2.set)
        self._rules_tree.pack(side="left", fill="x", expand=True,
                               padx=(8, 0), pady=8)
        vsb2.pack(side="right", fill="y", pady=8, padx=(0, 4))
        self._load_rules_table()

        add_row = ctk.CTkFrame(lang_card, fg_color="transparent")
        add_row.pack(fill="x", padx=18, pady=(0, 6))
        ctk.CTkLabel(add_row, text="進程名稱", font=FONT_BODY,
                     text_color=DIM).pack(side="left")
        self._rule_proc = ctk.CTkEntry(add_row, width=160, font=FONT_BODY,
                                        fg_color=INPUT,
                                        placeholder_text="WeChat / Notion ...")
        self._rule_proc.pack(side="left", padx=(8, 12))
        self._rule_lang = ctk.StringVar(value="zh-TW")
        ctk.CTkOptionMenu(add_row, values=["zh-TW","zh-CN","en","ja"],
                          variable=self._rule_lang,
                          fg_color=INPUT, button_color=ACCENT,
                          font=FONT_BODY, width=130).pack(side="left", padx=(0, 10))
        ctk.CTkButton(add_row, text="\uff0b 新增", width=90,
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=self._add_rule).pack(side="left", padx=(0, 8))
        ctk.CTkButton(add_row, text="\uff0d 刪除", width=90,
                      fg_color=INPUT, hover_color=RED,
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=self._del_rule).pack(side="left")

        ctk.CTkLabel(lang_card,
                     text="\u270e 亮綠色 = 自訂規則（可刪）  |  灰色 = 內建預設  |  藍色 = Chrome 標題規則",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=18, pady=(0, 16))

    def _load_rules_table(self):
        for item in self._rules_tree.get_children():
            self._rules_tree.delete(item)
        try:
            from window_detector import DEFAULT_APP_RULES, BROWSER_TITLE_RULES
        except ImportError:
            DEFAULT_APP_RULES, BROWSER_TITLE_RULES = {}, {}
        custom = {}
        try:
            if RULES_FILE.exists():
                custom = json.loads(RULES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        ll = {"zh-TW":"TW 繁體中文","zh-CN":"CN 簡體��文",
              "en":"EN 英文","ja":"JA 日文"}
        for proc, lang in custom.items():
            self._rules_tree.insert("", "end", tags=("custom",),
                values=(proc, ll.get(lang, lang) + "  \u270e"))
        shown = set(k.lower() for k in custom)
        for proc, lang in sorted(DEFAULT_APP_RULES.items()):
            if proc.lower() not in shown:
                self._rules_tree.insert("", "end", tags=("builtin",),
                    values=(proc, ll.get(lang, lang)))
        for kw, lang in sorted(BROWSER_TITLE_RULES.items()):
            self._rules_tree.insert("", "end", tags=("browser",),
                values=(f"[Chrome標題] {kw}", ll.get(lang, lang)))
        self._rules_tree.tag_configure("custom",  foreground="#7de8c0")
        self._rules_tree.tag_configure("builtin", foreground=DIM)
        self._rules_tree.tag_configure("browser", foreground="#7ab8e8")

    def _add_rule(self):
        proc = self._rule_proc.get().strip()
        lang = self._rule_lang.get()
        if not proc:
            messagebox.showwarning("快打 SmarType", "請輸入視窗進程名稱")
            return
        try:
            rules = json.loads(RULES_FILE.read_text(encoding="utf-8")) \
                    if RULES_FILE.exists() else {}
            rules[proc] = lang
            RULES_FILE.write_text(json.dumps(rules, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
            self._load_rules_table()
            self._rule_proc.delete(0, "end")
            messagebox.showinfo("快打 SmarType", f"已新���：{proc} → {lang}，立即生效")
        except Exception as e:
            messagebox.showerror("快打 SmarType", f"儲存失敗：{e}")

    def _del_rule(self):
        sel = self._rules_tree.selection()
        if not sel:
            messagebox.showwarning("快打 SmarType", "請先選取要刪除的規則")
            return
        item = self._rules_tree.item(sel[0])
        if "builtin" in item["tags"] or "browser" in item["tags"]:
            messagebox.showinfo("快打 SmarType",
                "內建規則無法刪除。若要覆蓋，請新增同名規則。")
            return
        proc = item["values"][0].replace("  \u270e", "")
        try:
            rules = json.loads(RULES_FILE.read_text(encoding="utf-8")) \
                    if RULES_FILE.exists() else {}
            rules.pop(proc, None)
            RULES_FILE.write_text(json.dumps(rules, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
            self._load_rules_table()
        except Exception as e:
            messagebox.showerror("快打 SmarType", f"刪除失敗：{e}")

    def _save_all(self):
        cfg = _load_config()
        cfg["hotkey"]     = self._hotkey_entry.get().strip()
        cfg["auto_start"] = bool(self._autostart.get())
        cfg["llm_polish"] = bool(self._llm_polish.get())
        _save_config(cfg)
        self.config_data = cfg
        self.dashboard.config_data = cfg
        messagebox.showinfo("快打 SmarType", "設定已儲存，重啟 SmarType 後完全生效")
