"""
智能词典学习器 - Smart Vocabulary Learner
自动从听写历史中提取高频词，建立个人专属词典
每次使用后在后台静默更新
"""

import json
import re
from pathlib import Path
from collections import Counter
from datetime import datetime

CONFIG_DIR = Path(__file__).parent / "userdata"
LOG_FILE   = CONFIG_DIR / "history.jsonl"
VOCAB_FILE = CONFIG_DIR / "vocabulary.json"
DICT_FILE  = CONFIG_DIR / "smart_dict.json"  # 自动学习的词典

# ── 不纳入词典的停用词 ────────────────────────────────────────────────────────
STOPWORDS = set([
    # 中文常用虚词
    "的","了","是","在","我","你","他","她","它","们","这","那","有","和","与",
    "也","都","就","而","但","或","如","及","被","把","从","到","对","为","以",
    "其","可","会","能","要","不","没","很","更","最","已","还","又","再","只",
    "去","来","上","下","中","大","小","多","少","好","新","现","时","用","说",
    "看","想","做","给","让","得","着","过","啊","吧","呢","嗯","哦","哈","嗯",
    "一个","一些","一样","一起","一直","这个","那个","什么","怎么","为什么",
    "然后","所以","因为","但是","如果","虽然","虽然","已经","可以","应该",
    "现在","今天","明天","昨天","时候","地方","问题","方法","情况","工作",
    # 英文常用词
    "the","a","an","is","are","was","were","be","been","have","has","had",
    "do","does","did","will","would","could","should","may","might","can",
    "i","you","he","she","it","we","they","this","that","and","or","but",
    "in","on","at","to","for","of","with","by","from","as","not","no",
])

# 专有名词特征：全大写、包含数字、混合大小写（驼峰）、特定后缀
def is_likely_proper_noun(word: str) -> bool:
    """判断是否可能是专有名词或技术词汇"""
    if len(word) < 2:
        return False
    # 纯数字跳过
    if word.isdigit():
        return False
    # 停用词跳过
    if word.lower() in STOPWORDS:
        return False
    # 纯中文短词（2字以下）跳过，除非是人名/地名
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', word)
    if len(chinese_chars) == len(word) and len(word) <= 1:
        return False
    return True


def extract_words(text: str) -> list:
    """从文本中提取词汇"""
    words = []

    # 提取英文词（包括缩写、产品名）
    eng_words = re.findall(r'[A-Za-z][A-Za-z0-9\-\.]*[A-Za-z0-9]|[A-Za-z]{2,}', text)
    words.extend(eng_words)

    # 提取中文词组（2-6字）
    chinese_phrases = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
    words.extend(chinese_phrases)

    # 提取混合词（如 iPhone15、GPT4、API）
    mixed = re.findall(r'[A-Za-z]+\d+|\d+[A-Za-z]+', text)
    words.extend(mixed)

    return [w for w in words if is_likely_proper_noun(w)]


def analyze_history(min_freq: int = 3) -> dict:
    """
    分析历史记录，返回高频词及频次
    min_freq: 出现次数达到此值才纳入词典
    """
    if not LOG_FILE.exists():
        return {}

    all_words = []
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
        for line in lines:
            if not line:
                continue
            try:
                r = json.loads(line)
                text = r.get("text", "")
                all_words.extend(extract_words(text))
            except Exception:
                pass
    except Exception:
        return {}

    counter = Counter(all_words)
    # 只保留频次 >= min_freq 的词
    return {w: c for w, c in counter.items() if c >= min_freq}


def load_smart_dict() -> dict:
    """加载智能词典"""
    if DICT_FILE.exists():
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"words": {}, "last_updated": "", "total_learned": 0}


def save_smart_dict(d: dict):
    """保存智能词典"""
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(DICT_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def update_smart_dict(min_freq: int = 3) -> list:
    """
    分析历史，更新智能词典
    返回新增的词列表
    """
    freq_words = analyze_history(min_freq)
    smart_dict = load_smart_dict()

    existing = set(smart_dict.get("words", {}).keys())
    new_words = []

    for word, count in freq_words.items():
        if word not in existing:
            new_words.append(word)
        smart_dict["words"][word] = count

    smart_dict["last_updated"] = datetime.now().isoformat()
    smart_dict["total_learned"] = len(smart_dict["words"])
    save_smart_dict(smart_dict)

    # 同时更新 vocabulary.json 的 custom_words（供 Whisper prompt 使用）
    _sync_to_vocab(smart_dict["words"])

    return new_words


def _sync_to_vocab(freq_words: dict):
    """
    将高频词同步到 vocabulary.json 的 auto_learned 字段
    按频次排序，取前 80 个
    """
    try:
        if VOCAB_FILE.exists():
            with open(VOCAB_FILE, "r", encoding="utf-8") as f:
                vocab = json.load(f)
        else:
            vocab = {"custom_words": [], "corrections": {},
                     "session_count": 0, "total_chars": 0}

        # 按频次排序，取前80个
        sorted_words = sorted(freq_words.items(), key=lambda x: x[1], reverse=True)
        auto_learned = [w for w, _ in sorted_words[:80]]

        vocab["auto_learned"] = auto_learned
        with open(VOCAB_FILE, "w", encoding="utf-8") as f:
            json.dump(vocab, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_prompt_words(max_words: int = 60) -> str:
    """
    获取用于 Whisper prompt 的词汇字符串
    合并：手动添加词汇 + 自动学习词汇
    """
    try:
        if not VOCAB_FILE.exists():
            return ""
        with open(VOCAB_FILE, "r", encoding="utf-8") as f:
            vocab = json.load(f)

        manual   = vocab.get("custom_words", [])
        auto     = vocab.get("auto_learned", [])

        # 手动词优先，合并去重
        all_words = list(dict.fromkeys(manual + auto))[:max_words]
        return ", ".join(all_words) if all_words else ""
    except Exception:
        return ""


def run_background_update():
    """后台静默更新（在线程中调用）"""
    try:
        update_smart_dict(min_freq=3)
    except Exception:
        pass


# ── 命令行查看模式 ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════╗
║      🧠  快打 SmarType · 智能词典                  ║
╚══════════════════════════════════════════════════╝
""")
    print("正在分析历史记录...\n")

    smart_dict = load_smart_dict()
    new_words  = update_smart_dict(min_freq=2)

    words = smart_dict.get("words", {})
    if not words:
        print("  还没有足够的历史记录来学习词汇。")
        print("  多用几次后再来看！")
    else:
        print(f"  词典共收录 {len(words)} 个词汇")
        print(f"  上次更新: {smart_dict.get('last_updated', '未知')[:16]}")
        if new_words:
            print(f"  本次新增: {len(new_words)} 个 → {', '.join(new_words[:10])}")
        print()

        # 按频次显示前20
        sorted_words = sorted(words.items(), key=lambda x: x[1], reverse=True)
        print("  高频词排行 Top 20:")
        for i, (w, c) in enumerate(sorted_words[:20], 1):
            bar = "█" * min(c, 20)
            print(f"  {i:2}. {w:<20} {bar} ({c}次)")

    print()
    input("按 Enter 退出...")
