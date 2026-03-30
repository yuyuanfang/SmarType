"""
快打 SmarType — 資料飛輪 data_flywheel.py

獨立模組，不修改原有 smart_vocab.py。
測試穩定後再整合。

核心理念：隨著使用量累積，本地資料庫越來越豐富，
逐步減少對雲端模型的依賴。

功能：
1. N-gram 追蹤（unigram / bigram / trigram）
2. 信心評分取代純頻率（含時間衰減 + 語境多樣性）
3. 按應用程式 / 時段建立詞彙側寫
4. 上下文感知的 Whisper Prompt 建構
5. 衰減機制清理過期詞彙
6. 對話模式偵測（贅字、常用開頭）
7. 學習速度分析 & 成長報告
8. 微調訓練資料匯出
9. 從既有 smart_dict.json 遷移
"""

import json, re, math, threading
from pathlib import Path
from collections import Counter
from datetime import datetime, date, timedelta

CONFIG_DIR     = Path(__file__).parent / "userdata"
NGRAM_FILE     = CONFIG_DIR / "flywheel_ngrams.json"
CONTEXT_FILE   = CONFIG_DIR / "flywheel_contexts.json"
ANALYTICS_FILE = CONFIG_DIR / "flywheel_analytics.json"
HISTORY_FILE   = CONFIG_DIR / "history.jsonl"
DIARY_DIR      = CONFIG_DIR / "diary"
DICT_FILE      = CONFIG_DIR / "smart_dict.json"
VOCAB_FILE     = CONFIG_DIR / "vocabulary.json"

# ── 停用詞（從 smart_vocab.py 複用）────────────────────────────────────────

STOPWORDS = set([
    "的","了","是","在","我","你","他","她","它","們","這","那","有","和","與",
    "也","都","就","而","但","或","如","及","被","把","從","到","對","為","以",
    "其","可","會","能","要","不","沒","很","更","最","已","還","又","再","只",
    "去","來","上","下","中","大","小","多","少","好","新","現","時","用","說",
    "看","想","做","給","讓","得","著","過","啊","吧","呢","嗯","哦","哈",
    "一個","一些","一樣","一起","一直","這個","那個","什麼","怎麼","為什麼",
    "然後","所以","因為","但是","如果","雖然","已經","可以","應該",
    "現在","今天","明天","昨天","時候","地方","問題","方法","情況","工作",
    # 英文常用詞
    "the","a","an","is","are","was","were","be","been","have","has","had",
    "do","does","did","will","would","could","should","may","might","can",
    "i","you","he","she","it","we","they","this","that","and","or","but",
    "in","on","at","to","for","of","with","by","from","as","not","no",
    "so","if","my","me","your","am","just","like","about","what","how",
])

# N-gram 容量上限
MAX_UNIGRAMS = 3000
MAX_BIGRAMS  = 1500
MAX_TRIGRAMS = 500


# ── 日誌 ──────────────────────────────────────────────────────────────────────

def _log(msg: str):
    try:
        log_file = CONFIG_DIR / "debug.log"
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}][flywheel] {msg}\n")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  Part 1: 分詞 & N-gram 提取
# ══════════════════════════════════════════════════════════════════════════════

def segment_text(text: str) -> list:
    """
    從文本中提取有序 token 列表。
    中文詞組（2-6字）+ 英文詞（3+字母）+ 混合詞。
    過濾停用詞。
    """
    tokens = []

    # 按出現順序逐段提取
    # 先切分中英文區段
    parts = re.findall(
        r'[\u4e00-\u9fff]{2,6}'           # 中文詞組
        r'|[A-Za-z][A-Za-z0-9\-\.]*[A-Za-z0-9]'  # 英文詞
        r'|[A-Za-z]{2,}'                  # 短英文
        r'|[A-Za-z]+\d+|\d+[A-Za-z]+',   # 混合詞
        text
    )

    for p in parts:
        low = p.lower()
        if low in STOPWORDS:
            continue
        if p.isdigit():
            continue
        if len(p) < 2:
            continue
        tokens.append(p)

    return tokens


def extract_ngrams(text: str, max_n: int = 3) -> dict:
    """
    提取 unigrams、bigrams、trigrams。
    回傳 {"unigrams": [...], "bigrams": [...], "trigrams": [...]}
    """
    tokens = segment_text(text)
    result = {"unigrams": list(tokens)}

    if max_n >= 2:
        result["bigrams"] = [
            tokens[i] + tokens[i+1]
            for i in range(len(tokens) - 1)
            # 只有兩個都是中文或至少一個是中文才做 bigram
            if _is_chinese_token(tokens[i]) or _is_chinese_token(tokens[i+1])
        ]

    if max_n >= 3:
        result["trigrams"] = [
            tokens[i] + tokens[i+1] + tokens[i+2]
            for i in range(len(tokens) - 2)
            if _has_chinese(tokens[i] + tokens[i+1] + tokens[i+2])
        ]

    return result


def _is_chinese_token(t: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', t))

def _has_chinese(t: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', t))


# ══════════════════════════════════════════════════════════════════════════════
#  Part 2: N-gram 存儲
# ══════════════════════════════════════════════════════════════════════════════

def _empty_ngram_store() -> dict:
    return {
        "version": 1,
        "last_updated": "",
        "unigrams": {},
        "bigrams": {},
        "trigrams": {},
    }

def load_ngram_store() -> dict:
    if NGRAM_FILE.exists():
        try:
            with open(NGRAM_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return _empty_ngram_store()

def save_ngram_store(store: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    store["last_updated"] = datetime.now().isoformat()
    with open(NGRAM_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def update_ngram_store(text: str, context: str = "", category: str = ""):
    """
    從一段文字中提取 n-gram，合併到存儲中。
    context = 視窗名稱（如 chrome.exe）
    category = 日記分類（如 work）
    """
    ngrams = extract_ngrams(text)
    store  = load_ngram_store()
    today  = date.today().isoformat()

    for level in ["unigrams", "bigrams", "trigrams"]:
        for gram in ngrams.get(level, []):
            bucket = store[level]
            if gram in bucket:
                bucket[gram]["count"] += 1
                bucket[gram]["last_seen"] = today
                if context:
                    ctx = bucket[gram].setdefault("contexts", {})
                    ctx[context] = ctx.get(context, 0) + 1
                if category:
                    cats = bucket[gram].setdefault("categories", {})
                    cats[category] = cats.get(category, 0) + 1
            else:
                bucket[gram] = {
                    "count": 1,
                    "first_seen": today,
                    "last_seen": today,
                    "contexts": {context: 1} if context else {},
                    "categories": {category: 1} if category else {},
                }

    # 容量控制：按 count 排序，保留前 N 個
    _cap_bucket(store, "unigrams", MAX_UNIGRAMS)
    _cap_bucket(store, "bigrams",  MAX_BIGRAMS)
    _cap_bucket(store, "trigrams", MAX_TRIGRAMS)

    save_ngram_store(store)


def _cap_bucket(store: dict, level: str, max_size: int):
    bucket = store[level]
    if len(bucket) > max_size:
        sorted_items = sorted(bucket.items(),
                              key=lambda x: x[1]["count"], reverse=True)
        store[level] = dict(sorted_items[:max_size])


# ══════════════════════════════════════════════════════════════════════════════
#  Part 3: 信心評分 & 衰減
# ══════════════════════════════════════════════════════════════════════════════

def calculate_confidence(word_info: dict, max_count: int = 100) -> float:
    """
    計算單一詞彙的信心分數（0.0 ~ 1.0）。

    公式：
      freq_score  = log2(count+1) / log2(max_count+1)
      recency     = 0.5 ^ (days_since_last_seen / 30)
      diversity   = min(len(contexts) / 3, 1.0)
      confidence  = freq_score * recency * (0.6 + 0.4 * diversity)
    """
    count = word_info.get("count", 1)
    last_seen = word_info.get("last_seen", date.today().isoformat())
    contexts = word_info.get("contexts", {})

    # 頻率分數（對數縮放）
    freq_score = math.log2(count + 1) / math.log2(max(max_count, count) + 1)

    # 時效因子（半衰期 30 天）
    try:
        last_dt = datetime.strptime(last_seen, "%Y-%m-%d").date()
        days_ago = (date.today() - last_dt).days
    except Exception:
        days_ago = 0
    recency = 0.5 ** (days_ago / 30.0)

    # 語境多樣性
    diversity = min(len(contexts) / 3.0, 1.0)

    confidence = freq_score * recency * (0.6 + 0.4 * diversity)
    return round(min(confidence, 1.0), 4)


def apply_decay(half_life_days: int = 30) -> dict:
    """
    對整個 ngram 存儲套用衰減。
    - 計算每個詞的有效分數
    - 移除 confidence < 0.05 且 last_seen > 90 天的條目
    回傳更新後的 store。
    """
    store = load_ngram_store()
    removed = 0
    today_str = date.today().isoformat()

    for level in ["unigrams", "bigrams", "trigrams"]:
        bucket = store[level]
        # 找出該層最大 count
        max_count = max((v["count"] for v in bucket.values()), default=1)

        to_remove = []
        for gram, info in bucket.items():
            conf = calculate_confidence(info, max_count)
            last = info.get("last_seen", today_str)
            try:
                days_old = (date.today() - datetime.strptime(last, "%Y-%m-%d").date()).days
            except Exception:
                days_old = 0

            # 清理條件：信心極低 且 超過 90 天未出現
            if conf < 0.05 and days_old > 90:
                to_remove.append(gram)

        for gram in to_remove:
            del bucket[gram]
            removed += 1

    if removed > 0:
        _log(f"decay: removed {removed} stale entries")
        save_ngram_store(store)

    return store


# ══════════════════════════════════════════════════════════════════════════════
#  Part 4: 上下文感知 Prompt 建構
# ══════════════════════════════════════════════════════════════════════════════

def load_context_profiles() -> dict:
    if CONTEXT_FILE.exists():
        try:
            with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": 1, "app_profiles": {}, "time_profiles": {}}

def save_context_profiles(profiles: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)


def update_context_profile(window: str, text: str, category: str = ""):
    """更新應用程式側寫 & 時段側寫"""
    profiles = load_context_profiles()
    tokens = segment_text(text)
    period = get_time_period()

    # App profile
    if window:
        app = profiles["app_profiles"].setdefault(window, {
            "total": 0, "top_words": [], "categories": {}
        })
        app["total"] += 1
        if category:
            app["categories"][category] = app["categories"].get(category, 0) + 1

        # 更新 top_words（簡易：合併後取前 50）
        word_counts = Counter(app.get("top_words", []))
        word_counts.update(tokens)
        app["top_words"] = [w for w, _ in word_counts.most_common(50)]

    # Time profile
    tp = profiles["time_profiles"].setdefault(period, {
        "categories": {}, "top_words": []
    })
    if category:
        tp["categories"][category] = tp["categories"].get(category, 0) + 1
    word_counts = Counter(tp.get("top_words", []))
    word_counts.update(tokens)
    tp["top_words"] = [w for w, _ in word_counts.most_common(50)]

    save_context_profiles(profiles)


def get_time_period(hour: int = None) -> str:
    if hour is None:
        hour = datetime.now().hour
    if 6 <= hour < 12:
        return "morning"
    elif 12 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 24:
        return "evening"
    else:
        return "night"


def get_high_confidence_vocab(min_confidence: float = 0.3,
                               max_words: int = 80) -> list:
    """
    取得高信心詞彙列表（替代 smart_vocab._sync_to_vocab）。
    回傳 [(word, confidence), ...] 按信心降序。
    """
    store = load_ngram_store()
    bucket = store.get("unigrams", {})
    if not bucket:
        return []

    max_count = max(v["count"] for v in bucket.values())

    scored = []
    for word, info in bucket.items():
        conf = calculate_confidence(info, max_count)
        if conf >= min_confidence:
            scored.append((word, conf))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:max_words]


def build_context_prompt(window: str = "", time_of_day: str = "",
                          max_chars: int = 120) -> str:
    """
    建構上下文感知的 Whisper Prompt。
    1. 全域高信心詞彙
    2. 若有 app profile，加權該 app 的常用詞
    3. 若有 time profile，加權該時段常用詞
    4. 合併、去重、截斷

    替代 smart_vocab.get_prompt_words()
    """
    # 全域詞彙
    global_words = [w for w, _ in get_high_confidence_vocab(0.3, 60)]

    # App 特化
    profiles = load_context_profiles()
    app_words = []
    if window and window in profiles.get("app_profiles", {}):
        app_words = profiles["app_profiles"][window].get("top_words", [])[:20]

    # 時段特化
    period = time_of_day or get_time_period()
    time_words = []
    if period in profiles.get("time_profiles", {}):
        time_words = profiles["time_profiles"][period].get("top_words", [])[:10]

    # 合併：app > time > global（優先順序）
    merged = list(dict.fromkeys(app_words + time_words + global_words))

    # 也納入 vocabulary.json 的手動詞彙
    try:
        if VOCAB_FILE.exists():
            with open(VOCAB_FILE, "r", encoding="utf-8") as f:
                vocab = json.load(f)
            manual = vocab.get("custom_words", [])
            merged = list(dict.fromkeys(manual + merged))
    except Exception:
        pass

    # 截斷到 max_chars
    prompt_words = []
    total_len = 0
    for w in merged:
        added = len(w) + 2  # ", " separator
        if total_len + added > max_chars:
            break
        prompt_words.append(w)
        total_len += added

    return ", ".join(prompt_words) if prompt_words else ""


# ══════════════════════════════════════════════════════════════════════════════
#  Part 5: 對話模式偵測
# ══════════════════════════════════════════════════════════════════════════════

def detect_filler_words(min_count: int = 5) -> list:
    """
    比較 diary 中的 raw vs text，找出被 LLM 刪掉的贅字。
    回傳 [(word, count), ...] 按次數降序。
    """
    filler_counter = Counter()

    # 掃描所有日記檔
    if not DIARY_DIR.exists():
        return []

    for f in DIARY_DIR.glob("*.jsonl"):
        if "summary" in f.name:
            continue
        try:
            for line in f.read_text(encoding="utf-8").strip().split("\n"):
                if not line:
                    continue
                entry = json.loads(line)
                raw  = entry.get("raw", "")
                text = entry.get("text", "")
                if raw and text and raw != text:
                    # 找出 raw 中有但 text 中沒有的詞
                    raw_tokens  = set(segment_text(raw))
                    text_tokens = set(segment_text(text))
                    fillers = raw_tokens - text_tokens
                    filler_counter.update(fillers)
        except Exception:
            pass

    return [(w, c) for w, c in filler_counter.most_common()
            if c >= min_count]


def detect_patterns(min_support: int = 3) -> list:
    """
    從歷史中偵測對話模式（常見開頭、常用句型）。
    回傳 [{"pattern": str, "count": int, "type": str}, ...]
    """
    opener_counter = Counter()

    if not HISTORY_FILE.exists():
        return []

    try:
        lines = HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n")
        for line in lines:
            if not line:
                continue
            entry = json.loads(line)
            text = entry.get("text", "").strip()
            if len(text) < 4:
                continue

            # 取前 4-8 個字作為開頭模式
            chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
            if len(chinese_chars) >= 4:
                opener = "".join(chinese_chars[:4])
                opener_counter[opener] += 1
    except Exception:
        pass

    patterns = []
    for pattern, count in opener_counter.most_common():
        if count >= min_support:
            patterns.append({
                "pattern": pattern,
                "count": count,
                "type": "opener",
            })

    return patterns[:50]


# ══════════════════════════════════════════════════════════════════════════════
#  Part 6: 分析 & 報告
# ══════════════════════════════════════════════════════════════════════════════

def load_analytics() -> dict:
    if ANALYTICS_FILE.exists():
        try:
            with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": 1, "daily_stats": {}, "total_processed": 0}

def save_analytics(analytics: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(ANALYTICS_FILE, "w", encoding="utf-8") as f:
        json.dump(analytics, f, ensure_ascii=False, indent=2)


def _update_daily_analytics():
    """更新今日統計"""
    analytics = load_analytics()
    today = date.today().isoformat()
    store = load_ngram_store()

    stats = analytics["daily_stats"].setdefault(today, {
        "vocab_size": 0, "new_words": 0, "entries": 0
    })
    stats["vocab_size"] = len(store.get("unigrams", {}))
    stats["entries"] = analytics.get("total_processed", 0)

    # 只保留最近 90 天
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    analytics["daily_stats"] = {
        k: v for k, v in analytics["daily_stats"].items() if k >= cutoff
    }

    save_analytics(analytics)


def calculate_learning_velocity() -> dict:
    """
    計算學習速度。
    回傳 {words_per_day_7d, words_per_day_30d, total_vocab, saturation_pct}
    """
    analytics = load_analytics()
    daily = analytics.get("daily_stats", {})

    if len(daily) < 2:
        store = load_ngram_store()
        return {
            "words_per_day_7d": 0,
            "words_per_day_30d": 0,
            "total_vocab": len(store.get("unigrams", {})),
            "saturation_pct": 0,
        }

    sorted_days = sorted(daily.items())
    sizes = [(d, s.get("vocab_size", 0)) for d, s in sorted_days]

    # 7 天平均
    recent_7 = sizes[-7:] if len(sizes) >= 7 else sizes
    if len(recent_7) >= 2:
        growth_7 = recent_7[-1][1] - recent_7[0][1]
        wpd_7 = growth_7 / max(len(recent_7) - 1, 1)
    else:
        wpd_7 = 0

    # 30 天平均
    recent_30 = sizes[-30:] if len(sizes) >= 30 else sizes
    if len(recent_30) >= 2:
        growth_30 = recent_30[-1][1] - recent_30[0][1]
        wpd_30 = growth_30 / max(len(recent_30) - 1, 1)
    else:
        wpd_30 = 0

    total = sizes[-1][1] if sizes else 0
    sat = min(total / MAX_UNIGRAMS * 100, 100)

    return {
        "words_per_day_7d": round(wpd_7, 1),
        "words_per_day_30d": round(wpd_30, 1),
        "total_vocab": total,
        "saturation_pct": round(sat, 1),
    }


def generate_analytics_report(days: int = 7) -> str:
    """生成文字版分析報告"""
    store = load_ngram_store()
    velocity = calculate_learning_velocity()
    high_conf = get_high_confidence_vocab(0.5, 20)

    lines = [
        "=== Data Flywheel Analytics Report ===",
        "",
        f"Total unigrams:  {len(store.get('unigrams', {}))}",
        f"Total bigrams:   {len(store.get('bigrams', {}))}",
        f"Total trigrams:  {len(store.get('trigrams', {}))}",
        "",
        f"Learning velocity (7d):  {velocity['words_per_day_7d']} words/day",
        f"Learning velocity (30d): {velocity['words_per_day_30d']} words/day",
        f"Capacity used:           {velocity['saturation_pct']}%",
        "",
        "Top 20 high-confidence words:",
    ]

    for i, (word, conf) in enumerate(high_conf, 1):
        bar = "\u2588" * int(conf * 20)
        lines.append(f"  {i:2}. {word:<20s} {bar} ({conf:.3f})")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  Part 7: 微調資料準備
# ══════════════════════════════════════════════════════════════════════════════

def prepare_finetune_data(output_path: str = None,
                           min_entries: int = 100) -> str:
    """
    從日記中萃取 (raw → polished) 配對，作為本地模型微調訓練資料。
    回傳檔案路徑（若資料量不足回傳 None）。
    """
    if not DIARY_DIR.exists():
        return None

    pairs = []
    for f in sorted(DIARY_DIR.glob("*.jsonl")):
        if "summary" in f.name:
            continue
        try:
            for line in f.read_text(encoding="utf-8").strip().split("\n"):
                if not line:
                    continue
                entry = json.loads(line)
                raw  = entry.get("raw", "")
                text = entry.get("text", "")
                if raw and text and raw != text and len(raw) > 5:
                    pairs.append({"input": raw, "output": text})
        except Exception:
            pass

    if len(pairs) < min_entries:
        _log(f"finetune: only {len(pairs)} pairs (need {min_entries})")
        return None

    out = output_path or str(CONFIG_DIR / "finetune_data.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    _log(f"finetune: exported {len(pairs)} pairs to {out}")
    return out


def export_correction_pairs() -> list:
    """萃取所有 (raw, polished) 配對（不寫檔）"""
    pairs = []
    if not DIARY_DIR.exists():
        return pairs

    for f in sorted(DIARY_DIR.glob("*.jsonl")):
        if "summary" in f.name:
            continue
        try:
            for line in f.read_text(encoding="utf-8").strip().split("\n"):
                if not line:
                    continue
                entry = json.loads(line)
                raw  = entry.get("raw", "")
                text = entry.get("text", "")
                if raw and text and raw != text:
                    pairs.append({"raw": raw, "polished": text})
        except Exception:
            pass
    return pairs


# ══════════════════════════════════════════════════════════════════════════════
#  Part 8: 飛輪整合入口
# ══════════════════════════════════════════════════════════════════════════════

_process_counter = 0
_counter_lock = threading.Lock()

def process_flywheel_update(text: str, window: str = "",
                             category: str = "") -> dict:
    """
    單一入口：每次語音辨識後呼叫。
    替代 smart_vocab.run_background_update()。

    1. 更新 ngram store
    2. 更新 context profile
    3. 每 50 次套用衰減
    4. 更新每日統計
    """
    global _process_counter

    try:
        update_ngram_store(text, window, category)
        update_context_profile(window, text, category)

        with _counter_lock:
            _process_counter += 1
            cnt = _process_counter

        # 每 50 次做一次衰減清理
        if cnt % 50 == 0:
            apply_decay()

        # 更新分析
        analytics = load_analytics()
        analytics["total_processed"] = cnt
        save_analytics(analytics)
        _update_daily_analytics()

        store = load_ngram_store()
        new_count = len(store.get("unigrams", {}))

        return {"new_ngrams": new_count, "vocab_size": new_count}

    except Exception as e:
        _log(f"flywheel update error: {e}")
        return {"new_ngrams": 0, "vocab_size": 0}


def run_background_flywheel(text: str, window: str = "",
                              category: str = ""):
    """背景執行版本（daemon thread）"""
    threading.Thread(
        target=process_flywheel_update,
        args=(text, window, category),
        daemon=True,
    ).start()


def get_flywheel_status() -> dict:
    """回傳飛輪系統狀態摘要"""
    store = load_ngram_store()
    velocity = calculate_learning_velocity()
    high_conf = get_high_confidence_vocab(0.5)

    return {
        "vocab_size": len(store.get("unigrams", {})),
        "bigram_size": len(store.get("bigrams", {})),
        "trigram_size": len(store.get("trigrams", {})),
        "high_confidence_count": len(high_conf),
        "learning_velocity_7d": velocity["words_per_day_7d"],
        "saturation_pct": velocity["saturation_pct"],
        "last_updated": store.get("last_updated", ""),
        "total_processed": _process_counter,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Part 9: 歷史資料完整重建（含對話語境）
# ══════════════════════════════════════════════════════════════════════════════

def build_from_history() -> dict:
    """
    從 history.jsonl + diary/*.jsonl 完整重建 ngram store 與 context profiles。

    解決問題：
    - migrate_from_smart_dict() 只有詞頻，沒有「誰說的」（視窗語境）
    - 導致 context profiles 為空，prompt 無法按 app 客製化
    - 分類時也缺乏語境，容易出錯

    資料來源優先順序：
    1. diary/*.jsonl  —— 最豐富：有 text/raw/window/category/ts
    2. history.jsonl  —— 補充：有 text/window/ts（無 category）

    回傳 {"diary_entries": N, "history_entries": M, "total_tokens": K}
    """
    store    = _empty_ngram_store()
    profiles = {"version": 1, "app_profiles": {}, "time_profiles": {}}

    diary_count   = 0
    history_count = 0
    total_tokens  = 0

    # ── 1. 讀取日記（最豐富來源）────────────────────────────────────────────
    if DIARY_DIR.exists():
        for f in sorted(DIARY_DIR.glob("*.jsonl")):
            if "summary" in f.name:
                continue
            try:
                for line in f.read_text(encoding="utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    entry = json.loads(line)

                    text     = entry.get("text") or entry.get("raw", "")
                    window   = entry.get("window", "")
                    category = entry.get("category", "")
                    ts       = entry.get("ts", "")

                    if not text:
                        continue

                    date_str = ts[:10] if ts else date.today().isoformat()
                    hour     = int(ts[11:13]) if len(ts) >= 13 else 12
                    period   = get_time_period(hour)
                    tokens   = segment_text(text)

                    # 更新 ngram store（帶視窗語境 + 分類）
                    _add_to_store(store, tokens, window, category, date_str)
                    total_tokens += len(tokens)

                    # 更新 context profiles
                    _add_to_profiles(profiles, window, tokens, category, period)

                    diary_count += 1
            except Exception as e:
                _log(f"build_from_history diary error: {e}")

    # ── 2. 讀取 history.jsonl（補充沒有日記的條目）──────────────────────────
    #    history 裡的條目通常也會在日記裡，但 history 記錄更完整（含 en 語言）
    #    使用 ts 做去重：跳過已在日記中處理的條目
    diary_ts_set: set = set()
    if DIARY_DIR.exists():
        for f in DIARY_DIR.glob("*.jsonl"):
            if "summary" in f.name:
                continue
            try:
                for line in f.read_text(encoding="utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    e = json.loads(line)
                    if e.get("ts"):
                        diary_ts_set.add(e["ts"][:19])  # 精確到秒
            except Exception:
                pass

    if HISTORY_FILE.exists():
        try:
            for line in HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                entry = json.loads(line)
                ts_key = (entry.get("ts", ""))[:19]

                # 已在日記中處理過，跳過
                if ts_key in diary_ts_set:
                    continue

                text   = entry.get("text", "")
                window = entry.get("window", "")
                ts     = entry.get("ts", "")

                if not text:
                    continue

                date_str = ts[:10] if ts else date.today().isoformat()
                hour     = int(ts[11:13]) if len(ts) >= 13 else 12
                period   = get_time_period(hour)
                tokens   = segment_text(text)

                _add_to_store(store, tokens, window, "", date_str)
                total_tokens += len(tokens)

                _add_to_profiles(profiles, window, tokens, "", period)

                history_count += 1
        except Exception as e:
            _log(f"build_from_history history error: {e}")

    # ── 3. 容量控制 & 儲存 ───────────────────────────────────────────────────
    _cap_bucket(store, "unigrams", MAX_UNIGRAMS)
    _cap_bucket(store, "bigrams",  MAX_BIGRAMS)
    _cap_bucket(store, "trigrams", MAX_TRIGRAMS)

    save_ngram_store(store)
    save_context_profiles(profiles)

    # 更新 analytics
    analytics = load_analytics()
    analytics["total_processed"] = diary_count + history_count
    analytics["last_full_build"] = datetime.now().isoformat()
    save_analytics(analytics)

    summary = {
        "diary_entries":   diary_count,
        "history_entries": history_count,
        "total_tokens":    total_tokens,
        "unigrams":        len(store["unigrams"]),
        "bigrams":         len(store["bigrams"]),
        "app_profiles":    len(profiles["app_profiles"]),
        "time_profiles":   len(profiles["time_profiles"]),
    }
    _log(f"build_from_history done: {summary}")
    return summary


def _add_to_store(store: dict, tokens: list, window: str,
                  category: str, date_str: str):
    """把 token 列表寫入 store（unigrams + bigrams + trigrams）"""
    # unigrams
    for tok in tokens:
        _upsert_gram(store["unigrams"], tok, window, category, date_str)

    # bigrams（中文優先）
    for i in range(len(tokens) - 1):
        if _is_chinese_token(tokens[i]) or _is_chinese_token(tokens[i+1]):
            gram = tokens[i] + tokens[i+1]
            _upsert_gram(store["bigrams"], gram, window, category, date_str)

    # trigrams
    for i in range(len(tokens) - 2):
        combined = tokens[i] + tokens[i+1] + tokens[i+2]
        if _has_chinese(combined):
            _upsert_gram(store["trigrams"], combined, window, category, date_str)


def _upsert_gram(bucket: dict, gram: str, window: str,
                 category: str, date_str: str):
    """新增或更新一個 gram 條目"""
    if gram in bucket:
        e = bucket[gram]
        e["count"] += 1
        e["last_seen"] = max(e.get("last_seen", date_str), date_str)
        if window:
            e["contexts"][window] = e["contexts"].get(window, 0) + 1
        if category:
            e["categories"][category] = e["categories"].get(category, 0) + 1
    else:
        bucket[gram] = {
            "count":      1,
            "first_seen": date_str,
            "last_seen":  date_str,
            "contexts":   {window: 1} if window else {},
            "categories": {category: 1} if category else {},
        }


def _add_to_profiles(profiles: dict, window: str, tokens: list,
                     category: str, period: str):
    """更新 app_profiles 和 time_profiles"""
    if window:
        app = profiles["app_profiles"].setdefault(window, {
            "total": 0, "top_words": [], "categories": {}
        })
        app["total"] += 1
        if category:
            app["categories"][category] = app["categories"].get(category, 0) + 1
        wc = Counter(app.get("top_words", []))
        wc.update(tokens)
        app["top_words"] = [w for w, _ in wc.most_common(50)]

    tp = profiles["time_profiles"].setdefault(period, {
        "categories": {}, "top_words": []
    })
    if category:
        tp["categories"][category] = tp["categories"].get(category, 0) + 1
    wc = Counter(tp.get("top_words", []))
    wc.update(tokens)
    tp["top_words"] = [w for w, _ in wc.most_common(50)]


# ── 從 smart_dict.json 遷移（舊方式，無語境，保留供相容）─────────────────────

def migrate_from_smart_dict() -> int:
    """
    一次性遷移：讀取 smart_dict.json，轉換為 ngram store 格式。
    保留 count，從 history.jsonl 推算時間範圍。
    回傳遷移的詞條數。
    """
    if not DICT_FILE.exists():
        print("  smart_dict.json not found, skipping migration.")
        return 0

    with open(DICT_FILE, "r", encoding="utf-8") as f:
        old = json.load(f)

    old_words = old.get("words", {})
    if not old_words:
        return 0

    # 嘗試從 history.jsonl 取得時間範圍
    first_date = date.today().isoformat()
    last_date  = date.today().isoformat()
    if HISTORY_FILE.exists():
        try:
            lines = HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n")
            if lines:
                first_entry = json.loads(lines[0])
                last_entry  = json.loads(lines[-1])
                first_date = first_entry.get("ts", first_date)[:10]
                last_date  = last_entry.get("ts", last_date)[:10]
        except Exception:
            pass

    store = load_ngram_store()
    migrated = 0

    for word, count in old_words.items():
        if word.lower() in STOPWORDS:
            continue
        if len(word) < 2:
            continue

        existing = store["unigrams"].get(word)
        if existing:
            # 合併：取較大的 count
            existing["count"] = max(existing["count"], count)
        else:
            store["unigrams"][word] = {
                "count": count,
                "first_seen": first_date,
                "last_seen": last_date,
                "contexts": {},
                "categories": {},
            }
            migrated += 1

    # 容量控制
    _cap_bucket(store, "unigrams", MAX_UNIGRAMS)
    save_ngram_store(store)

    _log(f"migrated {migrated} words from smart_dict.json")
    return migrated


# ══════════════════════════════════════════════════════════════════════════════
#  獨立測試
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("""
+------------------------------------------------------+
|   Data Flywheel - Standalone Test                    |
|   N-gram + Confidence + Context-Aware Prompts        |
+------------------------------------------------------+
""")

    # ── Test 1: N-gram 提取 ──────────────────────────────────────────────
    print("=== Test 1: N-gram Extraction ===\n")

    test_text = "今天開會討論了Q3預算，Claude Code很好用，cursor也不錯"
    ngrams = extract_ngrams(test_text)
    print(f"  Input: {test_text}")
    print(f"  Unigrams ({len(ngrams['unigrams'])}): {ngrams['unigrams']}")
    print(f"  Bigrams  ({len(ngrams['bigrams'])}):  {ngrams['bigrams']}")
    print(f"  Trigrams ({len(ngrams['trigrams'])}): {ngrams['trigrams']}")
    print()

    # ── Test 2: 信心評分 ─────────────────────────────────────────────────
    print("=== Test 2: Confidence Scoring ===\n")

    today_str = date.today().isoformat()
    old_str = (date.today() - timedelta(days=60)).isoformat()
    ancient_str = (date.today() - timedelta(days=120)).isoformat()

    test_cases = [
        ("high freq + recent", {"count": 50, "last_seen": today_str, "contexts": {"a": 10, "b": 5, "c": 3}}),
        ("high freq + stale",  {"count": 50, "last_seen": old_str,  "contexts": {"a": 50}}),
        ("low freq + recent",  {"count": 3,  "last_seen": today_str, "contexts": {"a": 2, "b": 1}}),
        ("low freq + ancient", {"count": 3,  "last_seen": ancient_str, "contexts": {"a": 3}}),
    ]

    for label, info in test_cases:
        conf = calculate_confidence(info, max_count=100)
        print(f"  {label:25s} -> confidence = {conf:.4f}")
    print()

    # ── Test 3: 衰減機制 ─────────────────────────────────────────────────
    print("=== Test 3: Decay Mechanism ===\n")

    # 備份現有 store
    backup = None
    if NGRAM_FILE.exists():
        backup = NGRAM_FILE.read_text(encoding="utf-8")

    # 建立測試 store
    test_store = _empty_ngram_store()
    test_store["unigrams"] = {
        "新鮮詞": {"count": 10, "first_seen": today_str, "last_seen": today_str, "contexts": {"a": 5}, "categories": {}},
        "過期詞": {"count": 2,  "first_seen": ancient_str, "last_seen": ancient_str, "contexts": {}, "categories": {}},
        "半衰詞": {"count": 20, "first_seen": old_str, "last_seen": old_str, "contexts": {"b": 10}, "categories": {}},
    }
    save_ngram_store(test_store)

    before = len(load_ngram_store()["unigrams"])
    apply_decay()
    after = len(load_ngram_store()["unigrams"])
    print(f"  Before decay: {before} entries")
    print(f"  After decay:  {after} entries")
    print(f"  Removed:      {before - after}")

    # 還原
    if backup:
        NGRAM_FILE.write_text(backup, encoding="utf-8")
    elif NGRAM_FILE.exists():
        NGRAM_FILE.unlink()
    print()

    # ── Test 4: 真實資料分析 ─────────────────────────────────────────────
    print("=== Test 4: Real Data Analysis ===\n")

    if HISTORY_FILE.exists():
        lines = HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n")
        print(f"  History entries: {len(lines)}")

        # 從歷史建立 ngram store
        all_tokens = Counter()
        for line in lines:
            try:
                entry = json.loads(line)
                text = entry.get("text", "")
                tokens = segment_text(text)
                all_tokens.update(tokens)
            except Exception:
                pass

        print(f"  Unique tokens: {len(all_tokens)}")
        print(f"  Top 15 tokens:")
        for w, c in all_tokens.most_common(15):
            bar = "\u2588" * min(c // 2, 20)
            print(f"    {w:<20s} {bar} ({c})")
    else:
        print("  No history.jsonl found (skip)")
    print()

    # ── Test 5a: build_from_history（完整歷史重建，含視窗語境）────────────
    print("=== Test 5a: build_from_history (diary + history + window context) ===\n")

    ngram_backup   = NGRAM_FILE.read_text(encoding="utf-8") if NGRAM_FILE.exists() else None
    context_backup = CONTEXT_FILE.read_text(encoding="utf-8") if CONTEXT_FILE.exists() else None

    result = build_from_history()
    print(f"  diary entries:   {result['diary_entries']}")
    print(f"  history entries: {result['history_entries']} (non-duplicate)")
    print(f"  total tokens:    {result['total_tokens']}")
    print(f"  unigrams built:  {result['unigrams']}")
    print(f"  bigrams built:   {result['bigrams']}")
    print(f"  app profiles:    {result['app_profiles']}")
    print(f"  time profiles:   {result['time_profiles']}")

    profiles = load_context_profiles()
    if profiles["app_profiles"]:
        print(f"\n  App profiles (top words per app):")
        for app, info in sorted(profiles["app_profiles"].items(),
                                key=lambda x: x[1]["total"], reverse=True)[:6]:
            cats = info.get("categories", {})
            top_cat = max(cats, key=cats.get) if cats else "—"
            top_words = info["top_words"][:5]
            print(f"    {app:<28} total={info['total']:>4}  "
                  f"主分類={top_cat:8}  詞：{', '.join(top_words)}")

    high = get_high_confidence_vocab(0.4, 15)
    if high:
        print(f"\n  Top 15 high-confidence (real timestamps):")
        for w, c in high:
            bar = "\u2588" * int(c * 20)
            print(f"    {w:<20s} {bar} ({c:.3f})")

    # ── Test 5b: 還原後測試 context-aware prompt ──────────────────────────
    print(f"\n  Context-aware prompts after full build:")
    all_apps = list(profiles["app_profiles"].keys())
    for app in all_apps[:3]:
        p = build_context_prompt(window=app)
        print(f"    [{app}]: {p[:80]}")

    # 還原
    if ngram_backup:
        NGRAM_FILE.write_text(ngram_backup, encoding="utf-8")
    elif NGRAM_FILE.exists():
        NGRAM_FILE.unlink()
    if context_backup:
        CONTEXT_FILE.write_text(context_backup, encoding="utf-8")
    elif CONTEXT_FILE.exists():
        CONTEXT_FILE.unlink()
    print()

    # ── Test 5c: 遷移（舊方式，無語境，保留參考）─────────────────────────
    print("=== Test 5c: migrate_from_smart_dict (legacy, no window context) ===\n")

    if DICT_FILE.exists():
        ngram_backup = NGRAM_FILE.read_text(encoding="utf-8") if NGRAM_FILE.exists() else None
        count = migrate_from_smart_dict()
        print(f"  Migrated: {count} words  (context profiles remain empty)")
        if ngram_backup:
            NGRAM_FILE.write_text(ngram_backup, encoding="utf-8")
        elif NGRAM_FILE.exists():
            NGRAM_FILE.unlink()
    else:
        print("  No smart_dict.json (skip)")
    print()

    # ── Test 6: Context Prompt 建構 ──────────────────────────────────────
    print("=== Test 6: Context-Aware Prompt (simulated data) ===\n")

    prompt_default = build_context_prompt()
    prompt_vscode  = build_context_prompt(window="Code.exe", time_of_day="morning")
    prompt_wechat  = build_context_prompt(window="WeChat.exe", time_of_day="evening")

    print(f"  Default prompt ({len(prompt_default)} chars):")
    print(f"    {prompt_default[:100]}...")
    print(f"  VS Code prompt ({len(prompt_vscode)} chars):")
    print(f"    {prompt_vscode[:100]}...")
    print(f"  WeChat prompt ({len(prompt_wechat)} chars):")
    print(f"    {prompt_wechat[:100]}...")
    print()

    # ── Test 7: 贅字偵測 ─────────────────────────────────────────────────
    print("=== Test 7: Filler Word Detection ===\n")

    fillers = detect_filler_words(min_count=2)
    if fillers:
        print(f"  Found {len(fillers)} filler patterns:")
        for w, c in fillers[:10]:
            print(f"    {w:<20s} ({c} times)")
    else:
        print("  No filler words detected (need diary raw/text pairs)")
    print()

    # ── Test 8: 微調資料 ─────────────────────────────────────────────────
    print("=== Test 8: Fine-tune Data ===\n")

    pairs = export_correction_pairs()
    print(f"  Correction pairs found: {len(pairs)}")
    if pairs:
        print(f"  Sample:")
        for p in pairs[:3]:
            print(f"    raw:      {p['raw'][:50]}")
            print(f"    polished: {p['polished'][:50]}")
            print()

    # ── 總結 ──────────────────────────────────────────────────────────────
    print("=== Flywheel Status ===\n")
    status = get_flywheel_status()
    for k, v in status.items():
        print(f"  {k}: {v}")

    print("\n=== All tests completed ===")
