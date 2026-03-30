"""
快打 SmarType — 日記引擎 diary_engine.py（繁體中文版）

功能：
1. polish(text)      — 去贅字、糾同音字、補標點（GPT-4o-mini）
2. classify(text)    — 分類：工作 / 生活 / 財務 / 雜記
3. append_entry()    — 寫入本地日記檔
4. generate_daily()  — 生成當日日記摘要（每晚10點呼叫）
"""

import json, datetime, threading
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "userdata"
DIARY_DIR  = CONFIG_DIR / "diary"

CATEGORY_MAP = {
    "work":    "工作",
    "life":    "生活",
    "finance": "財務",
    "misc":    "雜記",
}

# ── 初始化 ────────────────────────────────────────────────────────────────────
def _ensure_dirs():
    DIARY_DIR.mkdir(parents=True, exist_ok=True)

def _load_config():
    cfg_file = CONFIG_DIR / "config.json"
    if cfg_file.exists():
        with open(cfg_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ── LLM 客戶端（GLM → Gemini → OpenAI）────────────────────────────────────────
def _get_glm():
    """智譜 GLM-4-Flash（免費，中文能力強）"""
    try:
        from openai import OpenAI
        cfg = _load_config()
        key = cfg.get("glm_api_key", "")
        if not key:
            return None
        return OpenAI(api_key=key, base_url="https://open.bigmodel.cn/api/paas/v4/")
    except ImportError:
        return None

def _get_gemini():
    try:
        from google import genai
        cfg = _load_config()
        key = cfg.get("gemini_api_key", "")
        if not key:
            return None
        return genai.Client(api_key=key)
    except ImportError:
        return None

def _get_openai():
    try:
        from openai import OpenAI
        cfg = _load_config()
        key = cfg.get("api_key", "")
        if not key:
            return None
        return OpenAI(api_key=key)
    except ImportError:
        return None


def _llm_call(prompt: str) -> str:
    """優先 GLM-4-Flash，備用 Gemini，最後 OpenAI"""
    # ── 1. GLM-4-Flash（免費，中文最強）──
    glm = _get_glm()
    if glm:
        try:
            resp = glm.chat.completions.create(
                model="glm-4-flash",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            _log(f"GLM error: {e}")

    # ── 2. Gemini 2.5 Flash（免費額度大）──
    gemini = _get_gemini()
    if gemini:
        try:
            resp = gemini.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            return resp.text.strip()
        except Exception as e:
            _log(f"Gemini error: {e}")

    # ── 3. OpenAI GPT-4o-mini（付費備用）──
    openai_client = _get_openai()
    if openai_client:
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            _log(f"OpenAI error: {e}")

    return ""


# ── 翻譯功能（保留向後相容）─────────────────────────────────────────────────
def translate_to_english(text: str) -> str:
    """向後相容包裝，無上下文時直接呼叫 context_aware_post_process"""
    return context_aware_post_process(text, target_lang="en")


# ── 上下文感知後處理（Typeless 風格）─────────────────────────────────────────
def context_aware_post_process(
    text: str,
    target_lang: str = "zh-TW",
    app_name: str = "",
    window_title: str = "",
    recent_context: str = "",
) -> str:
    """
    單次 LLM 呼叫，同時完成語音辨識糾錯 + 語意修正 + 翻譯（如需要）。
    參考 Typeless 的做法，根據當前 app 和對話上下文調整輸出。
    失敗時回傳原文。
    """
    if not text or len(text.strip()) < 2:
        return text

    # 如果 ASR 結果不含任何中文字且不需要翻譯，跳過後處理
    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in text)
    if not has_cjk and target_lang != "en":
        return text

    # ── 判斷場景 ──
    app_lower = app_name.lower()
    if any(k in app_lower for k in ("claude", "cursor", "code", "vscode",
                                     "terminal", "cmd", "powershell", "wt")):
        scene = "coding"
        tone = "precise technical language, suitable for communicating with AI coding assistants"
    elif any(k in app_lower for k in ("wechat", "weixin", "qq", "dingtalk",
                                       "line", "telegram", "discord")):
        scene = "chat"
        tone = "casual and conversational, natural messaging style"
    elif any(k in app_lower for k in ("outlook", "gmail", "thunderbird")):
        scene = "email"
        tone = "professional and clear, suitable for email communication"
    else:
        scene = "general"
        tone = "clear and natural"

    # ── 組裝 prompt ──
    need_translate = (target_lang == "en")

    parts = [
        "You are a post-processor for voice dictation from a Taiwanese Mandarin (台灣國語) speaker.",
        "",
        "The input is raw speech recognition output and commonly contains:",
        "- Homophone errors (同音字): 城市→程式, 案子→專案, 文件→問題, 變色→辨識",
        "- Filler words (贅字): 嗯、那個、就是、然後、對對對、這個這個",
        "- Taiwanese-specific vocabulary: 程式(program), 資料夾(folder), 專案(project), 執行(run/execute)",
        "- Run-on or fragmented sentences from natural speech",
        "- Misrecognized technical terms or proper nouns",
    ]

    if recent_context:
        # 截取上下文，避免 prompt 過長
        ctx = recent_context[-500:]
        parts.append("")
        parts.append(f"Recent conversation context (use this to disambiguate meaning):")
        parts.append(f'"""{ctx}"""')

    if app_name:
        parts.append("")
        parts.append(f"Current app: {app_name}" + (f" — {window_title}" if window_title else ""))
        parts.append(f"Expected tone: {tone}")

    parts.append("")
    parts.append("CRITICAL RULES:")
    parts.append("- NEVER add content that was not in the original speech input")
    parts.append("- NEVER use the context to generate new sentences — context is ONLY for disambiguation")
    parts.append("- Output length should be similar to input length (±30%)")
    parts.append("- If the input seems like noise or nonsense, output it as-is")
    parts.append("")
    parts.append("Instructions:")
    parts.append("1. Fix homophone errors and misrecognized words (use context to disambiguate)")
    parts.append("2. Remove filler words and speech disfluencies")
    parts.append("3. Keep technical terms, variable names, file paths, and code references as-is")

    if need_translate:
        parts.append("4. Translate the corrected text to natural, fluent English")
        parts.append("5. Output ONLY the final English text, nothing else")
    else:
        if target_lang == "zh-CN":
            parts.append("4. 【重要】必须使用简体中文输出，禁止使用繁體字（如：這→这、點→点、個→个、還→还）")
        else:
            parts.append("4. 【重要】必須使用繁體中文輸出（如：这→這、点→點、个→個）")
        parts.append("5. Output ONLY the corrected text, nothing else")

    parts.append("")
    parts.append(f"Raw speech input: {text}")

    prompt = "\n".join(parts)
    result = _llm_call(prompt)

    if result and len(result.strip()) > 0:
        cleaned = result.strip()
        # 移除 LLM 可能加的引號包裝
        if len(cleaned) > 2 and cleaned[0] == '"' and cleaned[-1] == '"':
            cleaned = cleaned[1:-1]
        # ★ 幻覺檢測：如果輸出比輸入長 3 倍以上，視為 LLM 幻覺，回傳原文
        if len(cleaned) > len(text) * 3 and len(text) < 50:
            _log(f"post_process HALLUCINATION detected: input={len(text)} output={len(cleaned)}, returning raw")
            return text
        _log(f"post_process[{scene}→{target_lang}]: '{text[:40]}' → '{cleaned[:40]}'")
        return cleaned
    return text


# ── 核心功能 ──────────────────────────────────────────────────────────────────
def polish_and_classify(text: str) -> tuple:
    """
    單次 GPT 呼叫，同時完成：
    1. 去贅字、糾同音字、補標點
    2. 分類（work / life / finance / misc）
    回傳 (polished_text, category)
    """
    if not text or len(text.strip()) < 3:
        return text, "misc"

    prompt = f"""你是繁體中文語音輸入助理，請同時完成兩件事：

1. 去除贅字（嗯、那個、就是、對對對、然後然後、這個這個 等口語重複詞）
2. 根據語境修正同音字錯誤
3. 補充適當標點符號，保持原意
4. 判斷內容分類：work（工作）/ life（生活）/ finance（財務）/ misc（其他）

輸入：{text}

輸出 JSON（只輸出 JSON，不要其他內容）：
{{"text": "修正後繁體中文文字", "category": "work/life/finance/misc"}}"""

    raw = _llm_call(prompt)
    try:
        import re
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            obj = json.loads(m.group())
            clean = obj.get("text", text).strip()
            cat   = obj.get("category", "misc").lower().strip()
            if cat not in CATEGORY_MAP:
                cat = "misc"
            return clean, cat
    except Exception:
        pass
    return text, "misc"


# 保留向後相容的單獨呼叫
def polish(text: str) -> str:
    clean, _ = polish_and_classify(text)
    return clean

def classify(text: str) -> str:
    _, cat = polish_and_classify(text)
    return cat


def _extract_contact(process_name: str, window_title: str) -> str:
    """從窗口標題解析交談對象 / 網站名 / 檔案名"""
    if not window_title:
        return ""
    title = window_title.strip()
    pname = process_name.lower()

    # ── 通訊軟體：取分隔符前的部分 ──
    chat_suffixes = [
        " - 微信", " - WeChat", " - QQ", " - 飛書", " - Feishu", " - Lark",
        " - LINE", " - 钉钉", " - DingTalk", " - 企业微信", " - WeCom",
    ]
    for suffix in chat_suffixes:
        if title.endswith(suffix):
            return title[:-len(suffix)].strip()

    # Telegram 用 em dash
    if " — Telegram" in title:
        return title.split(" — Telegram")[0].strip()
    if " - Discord" in title:
        return title.split(" - Discord")[0].strip()
    if " - WhatsApp" in title:
        return title.split(" - WhatsApp")[0].strip()

    # ── 瀏覽器：取第一段（網站名）──
    browsers = ["chrome", "firefox", "edge", "msedge", "opera", "brave"]
    if any(b in pname for b in browsers):
        for sep in [" - ", " — ", " | "]:
            if sep in title:
                return title.split(sep)[0].strip()
        return title[:30]

    # ── 編輯器/IDE：取第一段（檔案/專案名）──
    editors = ["code", "cursor", "pycharm", "intellij", "webstorm",
               "sublime", "notepad", "vim", "neovim", "rider", "goland"]
    if any(e in pname for e in editors):
        for sep in [" - ", " — ", " | "]:
            if sep in title:
                return title.split(sep)[0].strip()
        return title[:30]

    # ── Claude Code ──
    if "claude" in pname:
        return "Claude Code"

    # ── 其他：截斷標題 ──
    return title[:30] if len(title) > 30 else title


def _detect_scene(process_name: str) -> str:
    """根據進程名判斷應用場景"""
    pname = process_name.lower()

    chat_apps = ["wechat", "weixin", "qq", "dingtalk", "feishu", "lark",
                 "line", "telegram", "discord", "whatsapp", "wxwork"]
    if any(a in pname for a in chat_apps):
        return "chat"

    code_apps = ["code", "cursor", "pycharm", "intellij", "webstorm",
                 "sublime", "vim", "neovim", "rider", "goland", "claude",
                 "terminal", "cmd", "powershell", "wt", "zed", "windsurf"]
    if any(a in pname for a in code_apps):
        return "coding"

    mail_apps = ["outlook", "thunderbird", "gmail"]
    if any(a in pname for a in mail_apps):
        return "email"

    browsers = ["chrome", "firefox", "edge", "msedge", "opera", "brave"]
    if any(b in pname for b in browsers):
        return "browser"

    return "general"


# 場景 emoji 對照
_SCENE_EMOJI = {
    "chat": "💬", "coding": "💻", "email": "📧",
    "browser": "🌐", "general": "📝",
}


def append_entry(text: str, category: str, ts: str = None,
                 raw_text: str = None, window: str = "",
                 window_title: str = "", contact: str = "",
                 app_scene: str = "", lang: str = ""):
    """
    寫入當日日記檔：userdata/diary/YYYY-MM-DD.jsonl
    每行一條記錄。
    """
    _ensure_dirs()
    ts     = ts or datetime.datetime.now().isoformat()
    date   = ts[:10]
    entry  = {
        "ts":       ts,
        "category": category,
        "label":    CATEGORY_MAP.get(category, "雜記"),
        "text":     text,
        "raw":      raw_text or text,
        "window":   window,
        "window_title": window_title,
        "contact":  contact,
        "app_scene": app_scene,
        "lang":     lang,
    }
    diary_file = DIARY_DIR / f"{date}.jsonl"
    with open(diary_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _log(f"diary append [{entry['label']}] {contact or window}: {text[:40]}")


def process_entry(raw_text: str, window: str = "",
                  window_info: dict = None) -> tuple[str, str]:
    """
    完整處理一條語音輸入：
      1. polish → 乾淨文字
      2. classify → 分類
      3. append → 寫入日記（含交談對象、場景）

    回傳 (polished_text, category)
    在背景執行，不阻塞主流程。
    """
    ts = datetime.datetime.now().isoformat()
    wi = window_info or {}
    proc_name   = wi.get("process", window)
    win_title   = wi.get("title", "")
    win_lang    = wi.get("lang", "")
    contact     = _extract_contact(proc_name, win_title)
    scene       = _detect_scene(proc_name)

    def _run():
        try:
            clean, category = polish_and_classify(raw_text)
            append_entry(clean, category, ts=ts,
                         raw_text=raw_text, window=proc_name,
                         window_title=win_title, contact=contact,
                         app_scene=scene, lang=win_lang)
            _log(f"process_entry done: [{category}] {contact}: {clean[:40]}")
        except Exception as e:
            _log(f"process_entry error: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return raw_text, "misc"


def polish_and_inject(raw_text: str, inject_fn, window: str = "",
                      window_info: dict = None):
    """
    polish 完成後才呼叫 inject_fn(polished_text)。
    用於需要「先潤色再注入」的模式。
    """
    ts = datetime.datetime.now().isoformat()
    wi = window_info or {}
    proc_name   = wi.get("process", window)
    win_title   = wi.get("title", "")
    win_lang    = wi.get("lang", "")
    contact     = _extract_contact(proc_name, win_title)
    scene       = _detect_scene(proc_name)

    def _run():
        try:
            clean, category = polish_and_classify(raw_text)
            append_entry(clean, category, ts=ts,
                         raw_text=raw_text, window=proc_name,
                         window_title=win_title, contact=contact,
                         app_scene=scene, lang=win_lang)
            _log(f"polish_and_inject done: [{category}] {contact}: {clean[:40]}")
        except Exception as e:
            _log(f"polish_and_inject error: {e}")

    threading.Thread(target=_run, daemon=True).start()


# ── 每日摘要生成 ──────────────────────────────────────────────────────────────
def generate_daily_summary(date: str = None) -> dict:
    """
    生成指定日期的日記摘要（四類分開）。
    date 格式：'YYYY-MM-DD'，預設今天。
    回傳 dict：{ 'work': '...', 'life': '...', 'finance': '...', 'misc': '...' }
    """
    _ensure_dirs()
    date = date or datetime.date.today().isoformat()
    diary_file = DIARY_DIR / f"{date}.jsonl"

    if not diary_file.exists():
        _log(f"generate_daily: no diary file for {date}")
        return {}

    entries_by_cat = {k: [] for k in CATEGORY_MAP}
    with open(diary_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                cat = r.get("category", "misc")
                if cat in entries_by_cat:
                    entries_by_cat[cat].append(r)
            except Exception:
                pass

    summaries = {}
    for cat, records in entries_by_cat.items():
        if not records:
            continue
        label = CATEGORY_MAP[cat]

        # 按交談對象分組，讓摘要更有上下文
        by_contact = {}
        for r in records:
            contact = r.get("contact", "") or r.get("window", "未知")
            scene   = r.get("app_scene", "")
            key     = f"{contact}（{_SCENE_EMOJI.get(scene, '')} {scene}）" if scene else contact
            by_contact.setdefault(key, []).append(r)

        parts = []
        for contact_key, entries in by_contact.items():
            parts.append(f"▸ {contact_key}：")
            for e in entries:
                t = e.get("ts", "")[:16].replace("T", " ")
                parts.append(f"  - [{t[11:]}] {e.get('text', '')}")
        combined = "\n".join(parts)

        prompt = f"""以下是今天（{date}）的{label}語音記錄，已按交談對象分組：

{combined}

請用繁體中文整理成簡潔的{label}日記，包含：
- 今日摘要（2-3句）
- 按交談對象/場景整理重點
{"- 待辦事項（如有）" if cat == "work" else ""}
{"- 決策記錄（如有）" if cat == "work" else ""}
{"- 支出/收入明細（如有）" if cat == "finance" else ""}

格式用 Markdown，簡潔為主。"""

        result = _llm_call(prompt)
        if result:
            summaries[cat] = result

    if summaries:
        summary_file = DIARY_DIR / f"{date}_summary.md"
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(f"# {date} 日記摘要\n\n")
            for cat in ["work", "life", "finance", "misc"]:
                if cat in summaries:
                    label = CATEGORY_MAP[cat]
                    f.write(f"## {label}日記\n\n{summaries[cat]}\n\n")
        _log(f"daily summary saved: {summary_file}")

    return summaries


# ── 排程：每晚10點自動生成 ────────────────────────────────────────────────────
def start_daily_scheduler():
    """在背景執行，每天晚上10點自動生成昨日摘要"""
    import time

    def _scheduler():
        generated_today = None
        while True:
            now  = datetime.datetime.now()
            date = now.date().isoformat()
            # 每天 22:00 執行一次
            if now.hour == 22 and generated_today != date:
                _log(f"scheduler: generating daily summary for {date}")
                generate_daily_summary(date)
                generated_today = date
            time.sleep(60)   # 每分鐘檢查一次

    threading.Thread(target=_scheduler, daemon=True).start()


# ── 工具 ──────────────────────────────────────────────────────────────────────
def _log(msg: str):
    try:
        log_file = CONFIG_DIR / "debug.log"
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}][diary] {msg}\n")
    except Exception:
        pass


# ── 手動測試 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    test_texts = [
        "嗯那個今天開了一個會然後就是討論了一下Q3的預算對對對然後決定把行銷費用提高百分之二十",
        "今天跟老朋友吃飯聊了很多以前的事情感覺很開心",
        "剛剛付了房租還有水電費大概三千多塊",
        "突然想到一個產品想法可以做一個語音備忘錄的功能",
    ]

    print("=== 測試 polish + classify ===\n")
    for text in test_texts:
        print(f"原文：{text}")
        clean = polish(text)
        cat   = classify(clean)
        print(f"潤色：{clean}")
        print(f"分類：{CATEGORY_MAP.get(cat, cat)}")
        append_entry(clean, cat, raw_text=text)
        print()

    print("=== 生成今日摘要 ===\n")
    summaries = generate_daily_summary()
    for cat, summary in summaries.items():
        print(f"【{CATEGORY_MAP[cat]}日記】\n{summary}\n")
