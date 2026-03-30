"""
词汇管理器 - Vocabulary & Corrections Manager
管理自定义词汇、纠错映射，查看使用统计
"""

import json
import sys
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "userdata"
VOCAB_FILE = CONFIG_DIR / "vocabulary.json"
LOG_FILE = CONFIG_DIR / "history.jsonl"


def load_vocab() -> dict:
    if VOCAB_FILE.exists():
        with open(VOCAB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"custom_words": [], "corrections": {}, "session_count": 0, "total_chars": 0}


def save_vocab(data: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(VOCAB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def show_stats(vocab: dict):
    print("\n📊 使用统计")
    print(f"   总听写次数: {vocab.get('session_count', 0)} 次")
    print(f"   总字符数:   {vocab.get('total_chars', 0)} 字")
    print(f"   自定义词汇: {len(vocab.get('custom_words', []))} 个")
    print(f"   纠错规则:   {len(vocab.get('corrections', {}))} 条")

    # 最近10条记录
    if LOG_FILE.exists():
        print("\n📝 最近记录:")
        lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
        recent = lines[-5:]
        for line in recent:
            try:
                r = json.loads(line)
                ts = r["ts"][:16].replace("T", " ")
                text = r["text"][:50] + ("..." if len(r["text"]) > 50 else "")
                print(f"   [{ts}] {text}")
            except Exception:
                pass
    print()


def manage_words(vocab: dict):
    print("\n📚 自定义词汇管理")
    words = vocab.get("custom_words", [])

    if words:
        print(f"   当前共 {len(words)} 个词汇:")
        for i, w in enumerate(words, 1):
            print(f"   {i:3}. {w}")
    else:
        print("   （暂无词汇）")

    print()
    print("   操作: [a] 添加  [d] 删除  [c] 清空  [回车] 返回")
    action = input("   > ").strip().lower()

    if action == "a":
        new_words = input("   输入词汇（逗号分隔）: ").strip()
        if new_words:
            ws = [w.strip() for w in new_words.replace("，", ",").split(",") if w.strip()]
            for w in ws:
                if w not in vocab["custom_words"]:
                    vocab["custom_words"].append(w)
            save_vocab(vocab)
            print(f"   ✅ 已添加 {len(ws)} 个词汇")

    elif action == "d":
        if not words:
            return
        idx = input("   输入要删除的序号: ").strip()
        try:
            i = int(idx) - 1
            removed = vocab["custom_words"].pop(i)
            save_vocab(vocab)
            print(f"   ✅ 已删除: {removed}")
        except (ValueError, IndexError):
            print("   ❌ 无效序号")

    elif action == "c":
        confirm = input("   确认清空所有词汇？[y/N]: ").strip().lower()
        if confirm == "y":
            vocab["custom_words"] = []
            save_vocab(vocab)
            print("   ✅ 已清空")


def manage_corrections(vocab: dict):
    print("\n✏️  纠错规则管理")
    corrections = vocab.get("corrections", {})

    if corrections:
        print(f"   当前共 {len(corrections)} 条规则:")
        for i, (wrong, correct) in enumerate(corrections.items(), 1):
            print(f"   {i:3}. 「{wrong}」→「{correct}」")
    else:
        print("   （暂无规则）")

    print()
    print("   操作: [a] 添加  [d] 删除  [回车] 返回")
    action = input("   > ").strip().lower()

    if action == "a":
        print("   格式：输入「错误识别:正确文字」")
        pair = input("   > ").strip()
        if ":" in pair or "：" in pair:
            parts = pair.replace("：", ":").split(":", 1)
            if len(parts) == 2:
                wrong, correct = parts[0].strip(), parts[1].strip()
                corrections[wrong] = correct
                vocab["corrections"] = corrections
                save_vocab(vocab)
                print(f"   ✅ 已添加: 「{wrong}」→「{correct}」")

    elif action == "d":
        if not corrections:
            return
        idx = input("   输入要删除的序号: ").strip()
        try:
            i = int(idx) - 1
            key = list(corrections.keys())[i]
            del corrections[key]
            vocab["corrections"] = corrections
            save_vocab(vocab)
            print(f"   ✅ 已删除规则: {key}")
        except (ValueError, IndexError):
            print("   ❌ 无效序号")


def show_prompt_preview(vocab: dict):
    """预览发给 Whisper 的 prompt"""
    words = vocab.get("custom_words", [])
    if not words:
        prompt = "台灣繁體中文，技術討論，專有名詞保留英文。"
    else:
        prompt = f"台灣繁體中文，技術討論，專有名詞保留英文。常用詞：{', '.join(words[:50])}。"
    print(f"\n🔍 当前 Whisper Prompt 预览:")
    print(f"   {prompt}")
    print()


def main():
    print("""
╔══════════════════════════════════════════╗
║       📚 词汇 & 习惯管理器                ║
╚══════════════════════════════════════════╝
    """)

    CONFIG_DIR.mkdir(exist_ok=True)

    while True:
        vocab = load_vocab()
        print("主菜单:")
        print("  [1] 查看使用统计")
        print("  [2] 管理自定义词汇")
        print("  [3] 管理纠错规则")
        print("  [4] 预览 Whisper Prompt")
        print("  [q] 退出")
        print()

        choice = input("请选择: ").strip().lower()

        if choice == "1":
            show_stats(vocab)
        elif choice == "2":
            manage_words(vocab)
        elif choice == "3":
            manage_corrections(vocab)
        elif choice == "4":
            show_prompt_preview(vocab)
        elif choice == "q":
            print("👋 再见！")
            break
        else:
            print("请输入有效选项\n")


if __name__ == "__main__":
    main()
