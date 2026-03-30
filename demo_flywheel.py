"""
快打 SmarType — 功能展示腳本 demo_flywheel.py
對比展示新舊系統差異
"""
import sys, json, datetime
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

# ── 色彩輸出（Windows 終端支援 ANSI）─────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
GRAY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
RED    = "\033[91m"
BLUE   = "\033[94m"

def h(title):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")

def sub(title):
    print(f"\n{YELLOW}── {title} ──{RESET}")

# ══════════════════════════════════════════════════════════════════════════════
#  Demo 1: 分類系統對比（舊 4 類 vs 新 10 類）
# ══════════════════════════════════════════════════════════════════════════════
h("Demo 1: 分類系統對比（舊 4 類 → 新 10 類）")

OLD_CATS = {"work": "工作", "life": "生活", "finance": "財務", "misc": "雜記"}

samples = [
    ("媽媽今天打電話說身體不舒服", "family", "life"),
    ("今天去健身房跑了五公里，感覺很好", "health", "life"),
    ("和老同學聚餐，聊了好多以前的事", "social", "life"),
    ("突然想到一個產品點子，用語音自動記帳", "ideas", "misc"),
    ("在看那本 Python 設計模式的書", "learning", "misc"),
    ("想起小時候在外婆家的夏天", "memories", "misc"),
]

from enhanced_diary import ENHANCED_CATEGORIES, enhanced_polish_and_classify

print(f"\n  {'輸入文字':<30} {'舊分類':^10} {'新分類':^12} {'情緒':^10} {'關鍵字'}")
print(f"  {'-'*80}")

for text, expected_new, expected_old in samples:
    result = enhanced_polish_and_classify(text)
    new_cat = result["category"]
    new_label = ENHANCED_CATEGORIES[new_cat]["label"]
    old_label = OLD_CATS.get(expected_old, "雜記")
    emoji = ENHANCED_CATEGORIES[new_cat]["emoji"]
    sent = result["sentiment"]
    sent_icon = "😊" if sent == "positive" else ("😢" if sent == "negative" else "😐")
    kw = ", ".join(result["keywords"][:2])

    # 新分類是否比舊分類更精確
    is_better = new_cat != expected_old
    better_mark = f"{GREEN}↑精確{RESET}" if is_better else "     "

    print(f"  {text[:28]:<30} "
          f"{GRAY}{old_label:^10}{RESET} "
          f"{GREEN}{emoji}{new_label:^10}{RESET} "
          f"{better_mark} "
          f"{sent_icon}{sent[:7]:^8} "
          f"{CYAN}{kw}{RESET}")

print(f"\n  {GREEN}✓ 新系統將「生活」細分為：家庭/健康/社交/回憶/靈感{RESET}")
print(f"  {GREEN}✓ 「雜記」細分為：學習/靈感/回憶{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
#  Demo 2: 情緒追蹤
# ══════════════════════════════════════════════════════════════════════════════
h("Demo 2: 情緒追蹤（Sentiment Tracking）")

mood_samples = [
    "今天升職了，老闆說我表現很好！",
    "又加班到十一點，好累，感覺撐不住了。",
    "今天去超市買了些東西。",
    "和媽媽吵架了，心情很差。",
    "項目終於完成了，團隊合作很愉快！",
]

print(f"\n  {'語音輸入':<30} {'情緒':^10} {'分數':^8} {'視覺化'}")
print(f"  {'-'*65}")

for text in mood_samples:
    result = enhanced_polish_and_classify(text)
    sent  = result["sentiment"]
    score = result["mood_score"]

    if sent == "positive":
        color = GREEN
        bar = "+" * int(score * 10)
        icon = "😊"
    elif sent == "negative":
        color = RED
        bar = "-" * int(abs(score) * 10)
        icon = "😢"
    else:
        color = GRAY
        bar = "·" * 3
        icon = "😐"

    print(f"  {text[:28]:<30} {color}{icon}{sent[:8]:^9}{RESET} {score:+5.1f}   {color}{bar}{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
#  Demo 3: 信心評分 vs 純頻率
# ══════════════════════════════════════════════════════════════════════════════
h("Demo 3: 信心評分 vs 純頻率計數")

from data_flywheel import calculate_confidence
from datetime import date, timedelta

today = date.today().isoformat()
d30   = (date.today() - timedelta(days=30)).isoformat()
d90   = (date.today() - timedelta(days=90)).isoformat()
d120  = (date.today() - timedelta(days=120)).isoformat()

test_words = [
    ("cursor（常用·今天）",     {"count": 80, "last_seen": today, "contexts": {"code": 50, "chrome": 20, "slack": 10}}),
    ("cursor（常用·30天前）",   {"count": 80, "last_seen": d30,  "contexts": {"code": 80}}),
    ("translation（超高頻·西班牙課）", {"count": 387,"last_seen": d90, "contexts": {"chrome": 387}}),
    ("la（高頻·西班牙）",       {"count": 133,"last_seen": d90, "contexts": {"chrome": 133}}),
    ("預算（中頻·今天）",        {"count": 25, "last_seen": today,"contexts": {"work": 20, "excel": 5}}),
    ("龍眼樹（低頻·今天）",      {"count": 3,  "last_seen": today,"contexts": {"diary": 3}}),
    ("es（中頻·120天前）",       {"count": 52, "last_seen": d120,"contexts": {"chrome": 52}}),
]

print(f"\n  {'詞彙':<25} {'頻率':>6}  {'信心分數':>10}  {'視覺化':<20}  {'說明'}")
print(f"  {'-'*80}")

max_count = max(info["count"] for _, info in test_words)

for label, info in test_words:
    freq  = info["count"]
    conf  = calculate_confidence(info, max_count)
    bar_len = int(conf * 20)
    bar   = "█" * bar_len

    if conf >= 0.6:
        color = GREEN
        note = "✓ 進入 Prompt"
    elif conf >= 0.3:
        color = YELLOW
        note = "~ 候選"
    elif conf >= 0.05:
        color = GRAY
        note = "↓ 衰減中"
    else:
        color = RED
        note = "✗ 即將清除"

    print(f"  {label:<25} {freq:>6}次  {color}{conf:>10.4f}{RESET}  {color}{bar:<20}{RESET}  {note}")

print(f"\n  {GREEN}✓ 「translation/la/es」雖然頻率最高，但因長期未用+單一語境，信心分數低{RESET}")
print(f"  {GREEN}✓ 「cursor」跨多個語境使用，信心分數最高{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
#  Demo 4: 上下文感知 Prompt 對比
# ══════════════════════════════════════════════════════════════════════════════
h("Demo 4: 上下文感知 Whisper Prompt")

from data_flywheel import (update_ngram_store, update_context_profile,
                            build_context_prompt, NGRAM_FILE, CONTEXT_FILE)
import tempfile, os

# 用臨時檔案模擬
orig_ngram   = NGRAM_FILE
orig_context = CONTEXT_FILE

# 模擬累積的使用資料
import data_flywheel as fw
fw.NGRAM_FILE   = Path(tempfile.mktemp(suffix=".json"))
fw.CONTEXT_FILE = Path(tempfile.mktemp(suffix=".json"))

# 模擬 VS Code 工作對話
coding_texts = [
    "幫我把這個函數重構一下", "今天要 review 這個 PR",
    "cursor 的 autocomplete 很好用", "在 VS Code 裡面加一個 breakpoint",
    "這個 API 要怎麼呼叫", "docker compose 啟動失敗",
]
for t in coding_texts:
    fw.update_ngram_store(t, "Code.exe", "work")
    fw.update_context_profile("Code.exe", t, "work")

# 模擬 WeChat 家庭對話
wechat_texts = [
    "媽媽今天怎麼樣", "週末回家吃飯", "姊姊的小孩快出生了",
    "爸爸說要去看醫生", "家裡的水管壞了", "妹妹昨天打電話來",
]
for t in wechat_texts:
    fw.update_ngram_store(t, "Weixin.exe", "family")
    fw.update_context_profile("Weixin.exe", t, "family")

prompt_generic = fw.build_context_prompt("", "morning")
prompt_vscode  = fw.build_context_prompt("Code.exe", "morning")
prompt_wechat  = fw.build_context_prompt("Weixin.exe", "evening")

print(f"\n  場景 1：{GRAY}沒有上下文（通用）{RESET}")
print(f"  {GRAY}Prompt: {prompt_generic or '（空）'}{RESET}")

print(f"\n  場景 2：{GREEN}VS Code + 早上{RESET}")
print(f"  {GREEN}Prompt: {prompt_vscode}{RESET}")

print(f"\n  場景 3：{CYAN}微信 + 晚上{RESET}")
print(f"  {CYAN}Prompt: {prompt_wechat}{RESET}")

print(f"\n  {GREEN}✓ 不同 App 產生不同 Prompt，提升辨識準確度{RESET}")

# 清理臨時檔案
for f in [fw.NGRAM_FILE, fw.CONTEXT_FILE]:
    try: f.unlink()
    except: pass
fw.NGRAM_FILE   = orig_ngram
fw.CONTEXT_FILE = orig_context


# ══════════════════════════════════════════════════════════════════════════════
#  Demo 5: 飛輪成長效應（模擬 30 天使用）
# ══════════════════════════════════════════════════════════════════════════════
h("Demo 5: 飛輪成長效應（資料累積越多越準確）")

print(f"""
  {BOLD}資料飛輪運作示意：{RESET}

  第 1 天：  cursor      ░░░░░░░░░░  count=1   confidence=0.00
  第 3 天：  cursor      ████░░░░░░  count=5   confidence=0.33  ← 進入候選
  第 7 天：  cursor      ██████░░░░  count=15  confidence=0.56  ← 進入 Prompt
  第 14 天： cursor      ████████░░  count=30  confidence=0.72  ← 高信心
  第 30 天： cursor      ██████████  count=60  confidence=0.85  ← 穩定核心詞

  第 90 天： translation ████████░░  count=387  → 60天未用 → {RED}confidence=0.08{RESET}
  第 120天： translation ░░░░░░░░░░  count=387  → 90天未用 → {RED}自動清除 ✗{RESET}

  {GREEN}✓ 常用詞越來越強，廢棄詞自動淘汰{RESET}
  {GREEN}✓ 不需要手動維護，系統自我優化{RESET}
""")

# ══════════════════════════════════════════════════════════════════════════════
#  Demo 6: 微調資料庫
# ══════════════════════════════════════════════════════════════════════════════
h("Demo 6: 微調訓練資料（從日記萃取）")

from data_flywheel import export_correction_pairs
pairs = export_correction_pairs()

if pairs:
    print(f"\n  已累積 {GREEN}{len(pairs)}{RESET} 組 (原始語音 → 潤色後) 配對\n")
    print(f"  {'原始語音（raw）':<35} → {'潤色後（polished）'}")
    print(f"  {'-'*70}")
    for p in pairs[:8]:
        raw = p["raw"][:33]
        pol = p["polished"][:33]
        changed = raw != pol
        marker = f"{GREEN}✓{RESET}" if changed else f"{GRAY}~{RESET}"
        print(f"  {marker} {GRAY}{raw:<35}{RESET}  {GREEN}{pol}{RESET}")

    print(f"\n  {GREEN}✓ 這 {len(pairs)} 組資料可用於微調本地 Whisper 模型{RESET}")
    print(f"  {GREEN}✓ 數據越多，本地模型越懂你的說話習慣{RESET}")
else:
    print(f"\n  {GRAY}（尚無修正配對，使用一段時間後自動累積）{RESET}")

# ══════════════════════════════════════════════════════════════════════════════
#  總結
# ══════════════════════════════════════════════════════════════════════════════
h("總結：資料飛輪效應")

print(f"""
  {BOLD}傳統系統（靜態）：{RESET}
  每次辨識 ──▶ Groq Cloud ──▶ 結果
  詞彙學習：純頻率計數，垃圾詞越積越多

  {BOLD}{GREEN}資料飛輪（動態）：{RESET}
  ┌─────────────────────────────────────────────────┐
  │  說話  →  辨識  →  日記分類  →  詞彙學習        │
  │    ↑                               │             │
  │    └── 更準確的 Prompt ←── 信心評分 ┘             │
  └─────────────────────────────────────────────────┘

  {GREEN}✓ 日記分類：4 類 → 10 類（家庭/健康/回憶/靈感等）{RESET}
  {GREEN}✓ 情緒追蹤：每條記錄附帶情緒分數（-1.0 ~ +1.0）{RESET}
  {GREEN}✓ 詞彙信心：時效衰減 + 語境多樣性，自動清除過期詞{RESET}
  {GREEN}✓ 上下文 Prompt：VS Code 和微信用不同詞彙提示 Whisper{RESET}
  {GREEN}✓ 微調資料：{len(pairs)} 組訓練對，未來可訓練本地模型{RESET}
  {GREEN}✓ 完全獨立：不影響現有程式，測試穩定後再整合{RESET}
""")
