"""
語音日記分頁
"""

import customtkinter as ctk
import json, datetime, threading

from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "userdata"
DIARY_DIR  = CONFIG_DIR / "diary"

ACCENT  = "#1D9E75"
ACCENT2 = "#17876A"
BG      = "#1a1a1a"
CARD    = "#242424"
TEXT    = "#e8e8e8"
DIM     = "#888888"
INPUT   = "#2e2e2e"

FONT_TITLE = ("Microsoft YaHei", 18, "bold")
FONT_HEAD  = ("Microsoft YaHei", 13, "bold")
FONT_BODY  = ("Microsoft YaHei", 12)
FONT_SMALL = ("Microsoft YaHei", 10)


class TabDiary(ctk.CTkFrame):
    def __init__(self, parent, dashboard):
        super().__init__(parent, fg_color=BG, corner_radius=0)
        self.dashboard = dashboard
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="語音日記", font=FONT_TITLE,
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(20, 2))
        ctk.CTkLabel(self, text="每次語音輸入自動分類 · 每晚 22:00 生成當日摘要",
                     font=FONT_SMALL, text_color=DIM).pack(anchor="w", padx=20, pady=(0, 10))

        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(ctrl, text="日期：", font=FONT_BODY,
                     text_color=DIM).pack(side="left")
        self._diary_date = ctk.CTkEntry(ctrl, width=120, font=("Consolas", 11),
                                         fg_color=INPUT,
                                         placeholder_text="YYYY-MM-DD")
        self._diary_date.insert(0, datetime.date.today().isoformat())
        self._diary_date.pack(side="left", padx=(4, 10))
        ctk.CTkButton(ctrl, text="載入", width=70,
                      fg_color=ACCENT, hover_color=ACCENT2,
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=self.refresh).pack(side="left", padx=(0, 12))
        ctk.CTkButton(ctrl, text="\u26a1 生成今日摘要", width=160,
                      fg_color=INPUT, hover_color="#3a3a3a",
                      font=FONT_BODY, corner_radius=8, height=34,
                      command=self._generate_summary).pack(side="left")

        tab_frame = ctk.CTkFrame(self, fg_color="transparent")
        tab_frame.pack(fill="x", padx=16, pady=(0, 6))
        self._diary_cat = ctk.StringVar(value="all")
        self._diary_tabs = {}
        for cat, icon, label in [
            ("all",     "\U0001f4cb", "全部"),
            ("work",    "\U0001f4bc", "工作"),
            ("life",    "\U0001f33f", "生活"),
            ("finance", "\U0001f4b0", "財務"),
            ("misc",    "\U0001f4dd", "雜記"),
            ("summary", "\u2728", "摘要"),
        ]:
            btn = ctk.CTkButton(
                tab_frame, text=f"{icon} {label}",
                fg_color=ACCENT if cat == "all" else INPUT,
                hover_color=ACCENT2 if cat == "all" else "#3a3a3a",
                text_color="white",
                font=FONT_SMALL, corner_radius=8,
                width=82, height=32,
                command=lambda c=cat: self._switch_tab(c))
            btn.pack(side="left", padx=(0, 6))
            self._diary_tabs[cat] = btn

        self._diary_box = ctk.CTkTextbox(self, fg_color=CARD,
                                          font=FONT_BODY,
                                          text_color=TEXT,
                                          corner_radius=12,
                                          state="disabled", wrap="word")
        self._diary_box.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def _switch_tab(self, cat):
        self._diary_cat.set(cat)
        for k, btn in self._diary_tabs.items():
            btn.configure(
                fg_color=ACCENT if k == cat else INPUT,
                hover_color=ACCENT2 if k == cat else "#3a3a3a")
        self.refresh()

    def refresh(self):
        date     = self._diary_date.get().strip()
        cat_filt = self._diary_cat.get()
        self._diary_box.configure(state="normal")
        self._diary_box.delete("1.0", "end")

        if cat_filt == "summary":
            sf = DIARY_DIR / f"{date}_summary.md"
            if sf.exists():
                self._diary_box.insert("end", sf.read_text(encoding="utf-8"))
            else:
                self._diary_box.insert("end",
                    f"尚無 {date} 的摘要。\n點擊「\u26a1 生成今日摘要」產生。")
            self._diary_box.configure(state="disabled")
            return

        diary_file = DIARY_DIR / f"{date}.jsonl"
        if not diary_file.exists():
            self._diary_box.insert("end",
                f"尚無 {date} 的語音日記。\n語音輸入後自動分類存入。")
            self._diary_box.configure(state="disabled")
            return

        cat_label = {"work":"\U0001f4bc 工作","life":"\U0001f33f 生活",
                     "finance":"\U0001f4b0 財務","misc":"\U0001f4dd 雜記"}
        scene_emoji = {"chat":"\U0001f4ac","coding":"\U0001f4bb","email":"\U0001f4e7",
                       "browser":"\U0001f310","general":"\U0001f4dd"}
        by_cat = {"work":[],"life":[],"finance":[],"misc":[]}
        for line in diary_file.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                c = r.get("category","misc")
                if c in by_cat:
                    by_cat[c].append(r)
            except Exception:
                pass

        total = 0
        for cat, entries in by_cat.items():
            if cat_filt != "all" and cat != cat_filt:
                continue
            if not entries:
                continue
            self._diary_box.insert("end",
                f"{cat_label.get(cat,cat)}  ({len(entries)} 條)\n")
            for r in entries:
                ts      = r.get("ts","")[:16].replace("T"," ")
                text    = r.get("text","")
                raw     = r.get("raw","")
                contact = r.get("contact","")
                scene   = r.get("app_scene","")
                window  = r.get("window","")
                emoji   = scene_emoji.get(scene, "")

                prefix = f"  {ts[11:]}  "
                if contact:
                    app_hint = window.replace(".exe","") if window else ""
                    prefix += f"{emoji} {contact}"
                    if app_hint and app_hint.lower() not in contact.lower():
                        prefix += f"（{app_hint}）"
                    prefix += " — "
                elif window:
                    prefix += f"{emoji} {window.replace('.exe','')} — "

                self._diary_box.insert("end", f"{prefix}{text}\n")
                if raw and raw != text:
                    self._diary_box.insert("end",
                        f"    原始：{raw[:60]}{'…' if len(raw)>60 else ''}\n")
                total += 1
            self._diary_box.insert("end", "\n")

        if total == 0:
            self._diary_box.insert("end", "此分類今日尚無記錄。")
        self._diary_box.configure(state="disabled")

    def _generate_summary(self):
        date = self._diary_date.get().strip()
        self._diary_box.configure(state="normal")
        self._diary_box.delete("1.0", "end")
        self._diary_box.insert("end", f"正在生成 {date} 摘要，請稍候…")
        self._diary_box.configure(state="disabled")
        def _run():
            try:
                from diary_engine import generate_daily_summary
                generate_daily_summary(date)
                self.after(0, lambda: self._switch_tab("summary"))
            except Exception as e:
                self.after(0, lambda: (
                    self._diary_box.configure(state="normal"),
                    self._diary_box.insert("end", f"\n錯誤：{e}"),
                    self._diary_box.configure(state="disabled")))
        threading.Thread(target=_run, daemon=True).start()
