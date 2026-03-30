"""
快打 SmarType - 历史记录查看器
查看、搜索所有听写记录
"""

import json
import sys
from pathlib import Path
from datetime import datetime

LOG_FILE = Path(__file__).parent / "userdata" / "history.jsonl"


def load_history():
    if not LOG_FILE.exists():
        return []
    records = []
    for line in LOG_FILE.read_text(encoding="utf-8").strip().split("\n"):
        try:
            r = json.loads(line)
            records.append(r)
        except Exception:
            pass
    return records


def format_time(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%m/%d %H:%M")
    except Exception:
        return ts[:16]


def show_history(records, limit=50, search=None):
    filtered = records
    if search:
        filtered = [r for r in records if search in r.get("text", "")]

    recent = filtered[-limit:]
    print(f"\n── 最近 {len(recent)} 条记录 {'（搜索: ' + search + '）' if search else ''} ──")
    print(f"{'时间':<12} {'语言':<6} {'应用':<20} 内容")
    print("─" * 70)
    for r in reversed(recent):
        ts   = format_time(r.get("ts", ""))
        lang = {"zh-TW": "繁體", "zh-CN": "简体", "en": "EN"}.get(r.get("lang", ""), "?")
        win  = r.get("window", "?")[:18]
        text = r.get("text", "")[:40]
        if len(r.get("text", "")) > 40:
            text += "…"
        print(f"{ts:<12} {lang:<6} {win:<20} {text}")
    print()


def show_stats(records):
    if not records:
        print("  暂无记录")
        return
    total_chars = sum(r.get("chars", 0) for r in records)
    langs = {}
    apps  = {}
    for r in records:
        lang = r.get("lang", "?")
        app  = r.get("window", "?")
        langs[lang] = langs.get(lang, 0) + 1
        apps[app]   = apps.get(app, 0) + 1

    print(f"\n📊 使用统计")
    print(f"   总记录数:  {len(records)} 条")
    print(f"   总字符数:  {total_chars} 字")
    print(f"\n   语言分布:")
    for lang, count in sorted(langs.items(), key=lambda x: -x[1]):
        label = {"zh-TW": "繁體中文", "zh-CN": "简体中文", "en": "English"}.get(lang, lang)
        print(f"     {label}: {count} 条")
    print(f"\n   常用应用 Top5:")
    for app, count in sorted(apps.items(), key=lambda x: -x[1])[:5]:
        print(f"     {app}: {count} 条")
    print()


def main():
    print("""
╔══════════════════════════════════════════╗
║     📝  快打 SmarType 历史记录查看器       ║
╚══════════════════════════════════════════╝
    """)

    records = load_history()
    if not records:
        print("  暂无记录，先去用快打 SmarType 说几句话吧！")
        input("\nPress Enter to exit...")
        return

    while True:
        print(f"共 {len(records)} 条记录")
        print("  [1] 查看最近 20 条")
        print("  [2] 查看最近 50 条")
        print("  [3] 搜索关键词")
        print("  [4] 查看统计")
        print("  [5] 导出为 txt 文件")
        print("  [q] 退出")
        print()

        choice = input("请选择: ").strip().lower()

        if choice == "1":
            show_history(records, limit=20)
        elif choice == "2":
            show_history(records, limit=50)
        elif choice == "3":
            kw = input("输入关键词: ").strip()
            if kw:
                show_history(records, limit=100, search=kw)
        elif choice == "4":
            show_stats(records)
        elif choice == "5":
            out = Path.home() / "Desktop" / "SmarType历史记录.txt"
            with open(out, "w", encoding="utf-8") as f:
                for r in records:
                    ts   = format_time(r.get("ts", ""))
                    lang = r.get("lang", "?")
                    text = r.get("text", "")
                    f.write(f"[{ts}][{lang}] {text}\n")
            print(f"  ✅ 已导出到桌面: SmarType历史记录.txt\n")
        elif choice == "q":
            print("👋 再见！")
            break
        else:
            print("请输入有效选项\n")


if __name__ == "__main__":
    main()
