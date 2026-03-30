"""
快打 SmarType — 增強日記引擎 enhanced_diary.py

獨立模組，不修改原有 diary_engine.py。
測試穩定後再整合。

功能：
1. 10 大分類（工作/家庭/健康/生活/財務/社交/學習/回憶/靈感/雜記）
2. 情緒追蹤（sentiment + mood_score）
3. 關鍵字萃取
4. 分類專屬摘要模板
5. 每日心情總覽
6. 向後相容既有 JSONL 格式
"""

import json, re, datetime, threading
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "userdata"
DIARY_DIR  = CONFIG_DIR / "diary"

# ── 10 大分類定義 ─────────────────────────────────────────────────────────────

ENHANCED_CATEGORIES = {
    "work":     {"label": "工作", "emoji": "\U0001f4bc",
                 "summary_hints": ["待辦事項（如有）", "決策記錄（如有）", "會議摘要"]},
    "family":   {"label": "家庭", "emoji": "\U0001f3e0",
                 "summary_hints": ["家人互動重點", "需要關注的事項"]},
    "health":   {"label": "健康", "emoji": "\U0001f3cb",
                 "summary_hints": ["身體狀況變化", "運動/飲食記錄", "就醫備忘"]},
    "living":   {"label": "生活", "emoji": "\u2615",
                 "summary_hints": ["日常瑣事", "購物備忘", "家務紀錄"]},
    "finance":  {"label": "財務", "emoji": "\U0001f4b0",
                 "summary_hints": ["支出/收入明細", "預算提醒", "投資備忘"]},
    "social":   {"label": "社交", "emoji": "\U0001f91d",
                 "summary_hints": ["朋友互動", "聚會紀錄", "社群動態"]},
    "learning": {"label": "學習", "emoji": "\U0001f4da",
                 "summary_hints": ["學到什麼", "閱讀筆記", "技能提升"]},
    "memories": {"label": "回憶", "emoji": "\U0001f4f8",
                 "summary_hints": ["場景描述", "情感色彩", "時間脈絡"]},
    "ideas":    {"label": "靈感", "emoji": "\U0001f4a1",
                 "summary_hints": ["核心概念", "可行性初判", "待驗證假設"]},
    "misc":     {"label": "雜記", "emoji": "\U0001f4dd",
                 "summary_hints": ["其他"]},
}

# 舊分類向後映射
_LEGACY_MAP = {"life": "living"}

def get_categories() -> dict:
    return ENHANCED_CATEGORIES

def get_category_keys() -> list:
    return list(ENHANCED_CATEGORIES.keys())

def _normalize_category(cat: str) -> str:
    cat = cat.lower().strip()
    cat = _LEGACY_MAP.get(cat, cat)
    return cat if cat in ENHANCED_CATEGORIES else "misc"


# ── 初始化 ────────────────────────────────────────────────────────────────────

def _ensure_dirs():
    DIARY_DIR.mkdir(parents=True, exist_ok=True)

def _load_config() -> dict:
    cfg_file = CONFIG_DIR / "config.json"
    if cfg_file.exists():
        with open(cfg_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _log(msg: str):
    try:
        log_file = CONFIG_DIR / "debug.log"
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}][enhanced_diary] {msg}\n")
    except Exception:
        pass


# ── LLM 客戶端（與 diary_engine.py 同一模式）────────────────────────────────

def _get_openai():
    try:
        from openai import OpenAI
        key = _load_config().get("api_key", "")
        return OpenAI(api_key=key) if key else None
    except ImportError:
        return None

def _get_gemini():
    try:
        from google import genai
        key = _load_config().get("gemini_api_key", "")
        return genai.Client(api_key=key) if key else None
    except ImportError:
        return None

def _llm_call(prompt: str) -> str:
    """優先 OpenAI，備用 Gemini，都沒有回空字串"""
    client = _get_openai()
    if client:
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            _log(f"OpenAI error: {e}")

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

    return ""


# ── 核心：增強版潤色 + 分類 ──────────────────────────────────────────────────

def enhanced_polish_and_classify(text: str, window: str = "") -> dict:
    """
    單次 LLM 呼叫完成：
    1. 去贅字、糾同音字、補標點
    2. 10 類分類
    3. 情緒判斷 + 分數
    4. 關鍵字萃取
    5. 子分類標籤

    回傳 dict：
    {text, category, sentiment, mood_score, keywords, sub_category}
    """
    default = {
        "text": text, "category": "misc",
        "sentiment": "neutral", "mood_score": 0.0,
        "keywords": [], "sub_category": "",
    }
    if not text or len(text.strip()) < 3:
        return default

    cat_desc = "\n".join(
        f"   - {k}（{v['label']}：{_cat_hint(k)}）"
        for k, v in ENHANCED_CATEGORIES.items()
    )

    window_hint = f"\n當前應用程式：{window}" if window else ""

    prompt = f"""你是繁體中文語音輸入助理，請同時完成以下任務：

1. 去除贅字（嗯、那個、就是、對對對、然後然後 等口語重複詞）
2. 根據語境修正同音字錯誤
3. 補充適當標點符號，保持原意
4. 判斷內容分類（10 類之一）：
{cat_desc}
5. 情緒判斷：positive / neutral / negative
6. 情緒分數：-1.0（非常負面）到 1.0（非常正面）
7. 關鍵字：1-3 個核心詞
8. 子分類標籤（選填，如「家人健康」「團隊會議」）
{window_hint}

輸入：{text}

只輸出 JSON（不要其他內容）：
{{"text":"修正後文字","category":"分類key","sentiment":"positive/neutral/negative","mood_score":0.0,"keywords":["詞1"],"sub_category":""}}"""

    raw = _llm_call(prompt)
    if not raw:
        return default

    try:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            obj = json.loads(m.group())
            result = {
                "text":         obj.get("text", text).strip(),
                "category":     _normalize_category(obj.get("category", "misc")),
                "sentiment":    _clamp_sentiment(obj.get("sentiment", "neutral")),
                "mood_score":   _clamp_score(obj.get("mood_score", 0.0)),
                "keywords":     obj.get("keywords", [])[:3],
                "sub_category": str(obj.get("sub_category", ""))[:20],
            }
            return result
    except Exception as e:
        _log(f"parse error: {e}")

    return default


def _cat_hint(key: str) -> str:
    """簡短分類提示，幫助 LLM 辨別"""
    hints = {
        "work":     "會議、專案、同事、工作任務",
        "family":   "家人、親戚、家庭事務、孩子",
        "health":   "身體、運動、就醫、飲食養生、睡眠",
        "living":   "購物、家務、日常瑣事、出行",
        "finance":  "收支、帳單、投資、理財",
        "social":   "朋友、聚會、社群互動",
        "learning": "閱讀、課程、技能提升、研究",
        "memories": "過去的事、童年、懷舊、早年生活",
        "ideas":    "新想法、創意、產品靈感、待驗證概念",
        "misc":     "以上都不符合",
    }
    return hints.get(key, "")


def _clamp_sentiment(s: str) -> str:
    s = s.lower().strip()
    return s if s in ("positive", "neutral", "negative") else "neutral"

def _clamp_score(v) -> float:
    try:
        v = float(v)
        return max(-1.0, min(1.0, v))
    except (TypeError, ValueError):
        return 0.0


# ── 寫入日記 ──────────────────────────────────────────────────────────────────

def append_enhanced_entry(text: str, category: str, ts: str = None,
                          raw_text: str = None, window: str = "",
                          sentiment: str = "neutral", mood_score: float = 0.0,
                          keywords: list = None, sub_category: str = "") -> dict:
    """
    寫入當日日記檔（增強版格式，version=2）。
    與既有 diary_engine 寫同一個 JSONL 檔案。
    """
    _ensure_dirs()
    ts   = ts or datetime.datetime.now().isoformat()
    date = ts[:10]
    cat  = _normalize_category(category)

    entry = {
        "ts":           ts,
        "category":     cat,
        "label":        ENHANCED_CATEGORIES[cat]["label"],
        "text":         text,
        "raw":          raw_text or text,
        "window":       window,
        "sentiment":    sentiment,
        "mood_score":   mood_score,
        "keywords":     keywords or [],
        "sub_category": sub_category,
        "version":      2,
    }

    diary_file = DIARY_DIR / f"{date}.jsonl"
    with open(diary_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    emoji = ENHANCED_CATEGORIES[cat]["emoji"]
    _log(f"diary+ [{emoji}{entry['label']}] {text[:40]}")
    return entry


# ── 讀取日記（向後相容）────────────────────────────────────────────────────────

def read_entries(date: str = None, category: str = None) -> list:
    """
    讀取指定日期的日記條目。
    自動為舊格式（無 version 欄位）補充預設值。
    """
    date = date or datetime.date.today().isoformat()
    diary_file = DIARY_DIR / f"{date}.jsonl"
    if not diary_file.exists():
        return []

    entries = []
    with open(diary_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                # 向後相容：舊條目補預設
                e.setdefault("sentiment", "neutral")
                e.setdefault("mood_score", 0.0)
                e.setdefault("keywords", [])
                e.setdefault("sub_category", "")
                e.setdefault("version", 1)
                # 舊分類映射
                e["category"] = _normalize_category(e.get("category", "misc"))
                e["label"] = ENHANCED_CATEGORIES[e["category"]]["label"]

                if category and e["category"] != category:
                    continue
                entries.append(e)
            except Exception:
                pass
    return entries


# ── 處理入口（對應 diary_engine.process_entry）──────────────────────────────

def process_enhanced_entry(raw_text: str, window: str = ""):
    """
    完整處理一條語音輸入（背景執行）：
    1. enhanced_polish_and_classify
    2. append_enhanced_entry
    可直接替換 diary_engine.process_entry()
    """
    ts = datetime.datetime.now().isoformat()

    def _run():
        try:
            result = enhanced_polish_and_classify(raw_text, window)
            append_enhanced_entry(
                text=result["text"],
                category=result["category"],
                ts=ts,
                raw_text=raw_text,
                window=window,
                sentiment=result["sentiment"],
                mood_score=result["mood_score"],
                keywords=result["keywords"],
                sub_category=result["sub_category"],
            )
            _log(f"process done: [{result['category']}] {result['text'][:40]}")
        except Exception as e:
            _log(f"process error: {e}")

    threading.Thread(target=_run, daemon=True).start()


# ── 每日摘要生成（增強版）────────────────────────────────────────────────────

def _build_category_prompt(cat_key: str, texts: list, date: str) -> str:
    """依分類產生專屬摘要 prompt"""
    info = ENHANCED_CATEGORIES[cat_key]
    label = info["label"]
    hints = info["summary_hints"]
    hint_lines = "\n".join(f"- {h}" for h in hints)
    combined = "\n".join(f"- {t}" for t in texts)

    return f"""以下是 {date} 的{label}語音記錄：

{combined}

請用繁體中文整理成簡潔的{label}日記，包含：
{hint_lines}
- 今日摘要（2-3句）

格式用 Markdown，簡潔為主。"""


def generate_enhanced_summary(date: str = None) -> dict:
    """
    生成指定日期的增強版每日摘要。
    - 按 10 類分別摘要
    - 附加心情總覽
    - 寫入 YYYY-MM-DD_summary.md
    """
    _ensure_dirs()
    date = date or datetime.date.today().isoformat()
    entries = read_entries(date)

    if not entries:
        _log(f"summary: no entries for {date}")
        return {}

    # 按分類分組
    by_cat = {}
    sentiments = []
    for e in entries:
        cat = e["category"]
        by_cat.setdefault(cat, []).append(e["text"])
        sentiments.append({
            "ts": e.get("ts", ""),
            "sentiment": e.get("sentiment", "neutral"),
            "score": e.get("mood_score", 0.0),
        })

    # 各分類摘要
    summaries = {}
    for cat, texts in by_cat.items():
        if not texts:
            continue
        prompt = _build_category_prompt(cat, texts, date)
        result = _llm_call(prompt)
        if result:
            summaries[cat] = result

    # 心情總覽
    mood_overview = _generate_mood_overview(sentiments, date)

    # 寫入 Markdown
    if summaries or mood_overview:
        summary_file = DIARY_DIR / f"{date}_summary.md"
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(f"# {date} 日記摘要\n\n")

            # 按固定順序輸出
            for cat_key in get_category_keys():
                if cat_key in summaries:
                    info = ENHANCED_CATEGORIES[cat_key]
                    f.write(f"## {info['emoji']} {info['label']}日記\n\n")
                    f.write(summaries[cat_key] + "\n\n")

            if mood_overview:
                f.write("## \U0001f3ad 今日心情\n\n")
                f.write(mood_overview + "\n")

        _log(f"enhanced summary saved: {summary_file}")

    summaries["_mood"] = mood_overview
    return summaries


def _generate_mood_overview(sentiments: list, date: str) -> str:
    """生成心情總覽區塊"""
    if not sentiments:
        return ""

    total = len(sentiments)
    pos = sum(1 for s in sentiments if s["sentiment"] == "positive")
    neg = sum(1 for s in sentiments if s["sentiment"] == "negative")
    neu = total - pos - neg
    avg_score = sum(s["score"] for s in sentiments) / total if total else 0

    # 用表情表示整體心情
    if avg_score > 0.3:
        overall = "\U0001f60a 整體正面"
    elif avg_score < -0.3:
        overall = "\U0001f614 整體低落"
    else:
        overall = "\U0001f610 整體平穩"

    lines = [
        f"- {overall}（平均分數：{avg_score:.2f}）",
        f"- 正面 {pos} 則 / 中性 {neu} 則 / 負面 {neg} 則（共 {total} 則）",
    ]
    return "\n".join(lines)


def generate_mood_report(date: str = None) -> dict:
    """讀取條目，彙整情緒分佈"""
    entries = read_entries(date)
    if not entries:
        return {"overall": "neutral", "distribution": {}, "avg_score": 0.0, "count": 0}

    scores = [e.get("mood_score", 0.0) for e in entries]
    avg = sum(scores) / len(scores) if scores else 0
    dist = {"positive": 0, "neutral": 0, "negative": 0}
    for e in entries:
        s = e.get("sentiment", "neutral")
        dist[s] = dist.get(s, 0) + 1

    if avg > 0.3:
        overall = "positive"
    elif avg < -0.3:
        overall = "negative"
    else:
        overall = "neutral"

    return {
        "overall": overall,
        "distribution": dist,
        "avg_score": round(avg, 3),
        "count": len(entries),
    }


# ── 排程：每晚 22:00 自動生成 ────────────────────────────────────────────────

def start_enhanced_scheduler():
    """在背景執行，每天 22:00 自動生成當日摘要"""
    import time

    def _scheduler():
        generated_today = None
        while True:
            now  = datetime.datetime.now()
            date = now.date().isoformat()
            if now.hour == 22 and generated_today != date:
                _log(f"scheduler: generating enhanced summary for {date}")
                try:
                    generate_enhanced_summary(date)
                except Exception as e:
                    _log(f"scheduler error: {e}")
                generated_today = date
            time.sleep(60)

    threading.Thread(target=_scheduler, daemon=True).start()


# ── 翻譯功能（複用 diary_engine 同一邏輯）────────────────────────────────────

def translate_to_english(text: str) -> str:
    """將中文翻譯成英文，用於編程場景。失敗時回傳原文。"""
    if not text or len(text.strip()) < 2:
        return text
    prompt = (
        "Translate the following Chinese text to English. "
        "Output ONLY the English translation, nothing else. "
        "Keep technical terms, variable names, and code references as-is.\n\n"
        f"{text}"
    )
    result = _llm_call(prompt)
    if result and len(result.strip()) > 0:
        _log(f"translate: '{text[:40]}' -> '{result[:40]}'")
        return result.strip()
    return text


# ── 向後相容介面 ──────────────────────────────────────────────────────────────

def polish_and_classify(text: str) -> tuple:
    """相容舊版 diary_engine.polish_and_classify()"""
    result = enhanced_polish_and_classify(text)
    return result["text"], result["category"]

def polish(text: str) -> str:
    result = enhanced_polish_and_classify(text)
    return result["text"]

def classify(text: str) -> str:
    result = enhanced_polish_and_classify(text)
    return result["category"]


# ══════════════════════════════════════════════════════════════════════════════
#  獨立測試
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("""
+------------------------------------------------------+
|   Enhanced Diary Engine - Standalone Test             |
|   10 Categories + Sentiment + Keywords               |
+------------------------------------------------------+
""")

    # ── 測試 1：分類準確度 ────────────────────────────────────────────────
    test_samples = [
        ("嗯那個今天開了一個會然後就是討論了一下Q3的預算", "work"),
        ("媽媽今天生日我跟姊姊一起買了蛋糕給她", "family"),
        ("今天跑了五公里然後做了半小時瑜伽感覺很舒服", "health"),
        ("去超市買了一些日用品還有洗衣精", "living"),
        ("剛剛付了房租三千多塊還有信用卡帳單", "finance"),
        ("今天跟大學同學聚餐聊了很多很開心", "social"),
        ("在看那本關於Python設計模式的書學到了策略模式", "learning"),
        ("突然想到小時候外婆家的院子裡有一棵龍眼樹", "memories"),
        ("想到一個APP點子可以用語音自動記帳", "ideas"),
        ("今天天氣不錯隨便說一下", "misc"),
    ]

    print("=== Test 1: Classification (10 categories) ===\n")

    correct = 0
    for text, expected in test_samples:
        result = enhanced_polish_and_classify(text)
        got = result["category"]
        match = "OK" if got == expected else f"MISS (expected {expected})"
        if got == expected:
            correct += 1
        emoji = ENHANCED_CATEGORIES[got]["emoji"]
        print(f"  {emoji} [{got:8s}] {match}")
        print(f"     raw: {text[:50]}")
        print(f"     out: {result['text'][:50]}")
        print(f"     sentiment={result['sentiment']}  score={result['mood_score']:.1f}  kw={result['keywords']}")
        print()

    print(f"  Accuracy: {correct}/{len(test_samples)}\n")

    # ── 測試 2：寫入/讀取 ─────────────────────────────────────────────────
    print("=== Test 2: Entry I/O ===\n")

    test_date = "9999-12-31"  # 不污染真實日記
    test_file = DIARY_DIR / f"{test_date}.jsonl"
    if test_file.exists():
        test_file.unlink()

    append_enhanced_entry(
        text="測試條目：今天很開心",
        category="living",
        ts=f"{test_date}T10:00:00",
        raw_text="測試條目今天很開心",
        window="test.exe",
        sentiment="positive",
        mood_score=0.7,
        keywords=["開心", "測試"],
        sub_category="日常",
    )

    loaded = read_entries(test_date)
    if loaded and loaded[0]["version"] == 2 and loaded[0]["sentiment"] == "positive":
        print("  Write/Read: PASS (version=2, sentiment preserved)")
    else:
        print("  Write/Read: FAIL")

    # 清理
    if test_file.exists():
        test_file.unlink()

    # ── 測試 3：向後相容 ──────────────────────────────────────────────────
    print("\n=== Test 3: Legacy Compatibility ===\n")

    today = datetime.date.today().isoformat()
    legacy = read_entries(today)
    if legacy:
        sample = legacy[0]
        print(f"  Loaded {len(legacy)} entries from {today}")
        print(f"  First entry version={sample.get('version')}, "
              f"category={sample['category']}, "
              f"sentiment={sample.get('sentiment')}")
        print("  Legacy read: PASS")
    else:
        print(f"  No entries for {today} (skip legacy test)")

    # ── 測試 4：心情報告 ──────────────────────────────────────────────────
    print("\n=== Test 4: Mood Report ===\n")

    mood = generate_mood_report(today)
    print(f"  Overall: {mood['overall']}")
    print(f"  Avg score: {mood['avg_score']}")
    print(f"  Distribution: {mood['distribution']}")
    print(f"  Entries: {mood['count']}")

    print("\n=== All tests completed ===")
