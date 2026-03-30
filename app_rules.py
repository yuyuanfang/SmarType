"""
应用语言规则管理器 - App Language Rules Manager
自定义哪个程序用简体、哪个用繁体
"""

import json
from pathlib import Path
from window_detector import (
    get_active_window_info, get_language_label,
    load_app_rules, save_custom_rule,
    DEFAULT_APP_RULES, APP_RULES_FILE
)

CONFIG_DIR = Path(__file__).parent / "userdata"


def print_header():
    print("""
╔══════════════════════════════════════════════════╗
║      🌐  应用语言规则管理器                         ║
╠══════════════════════════════════════════════════╣
║  设置每个程序默认使用简体还是繁体中文                ║
╚══════════════════════════════════════════════════╝
    """)


def show_current_rules():
    """显示所有规则（内建 + 用户自定义）"""
    custom = {}
    if APP_RULES_FILE.exists():
        with open(APP_RULES_FILE, "r", encoding="utf-8") as f:
            custom = json.load(f)

    print("\n── 内建规则（部分）─────────────────────────")
    shown_default = {
        "微信/WeChat":      DEFAULT_APP_RULES.get("wechat", "?"),
        "QQ":              DEFAULT_APP_RULES.get("qq", "?"),
        "钉钉":             DEFAULT_APP_RULES.get("dingtalk", "?"),
        "飞书/Lark":        DEFAULT_APP_RULES.get("feishu", "?"),
        "Facebook":        DEFAULT_APP_RULES.get("facebook", "?"),
        "Line":            DEFAULT_APP_RULES.get("line", "?"),
        "Telegram":        DEFAULT_APP_RULES.get("telegram", "?"),
        "Gmail/Outlook":   DEFAULT_APP_RULES.get("gmail", "?"),
        "VS Code":         DEFAULT_APP_RULES.get("code", "?"),
    }
    for app, lang in shown_default.items():
        icon = "🇨🇳" if lang == "zh-CN" else ("🇹🇼" if lang == "zh-TW" else "🇬🇧")
        print(f"  {icon}  {app:<20} → {get_language_label(lang)}")

    if custom:
        print("\n── 你的自定义规则 ──────────────────────────")
        for i, (keyword, lang) in enumerate(custom.items(), 1):
            icon = "🇨🇳" if lang == "zh-CN" else ("🇹🇼" if lang == "zh-TW" else "🇬🇧")
            print(f"  {i:2}. {icon}  {keyword:<20} → {get_language_label(lang)}")
    else:
        print("\n  （没有自定义规则，使用全部内建规则）")
    print()


def detect_current_window():
    """检测当前活动窗口并显示会使用哪种语言"""
    print("\n🔍 实时窗口检测（切换窗口后按 Enter 刷新，输入 q 返回）\n")
    while True:
        info = get_active_window_info()
        lang = info.get("lang", "zh-TW")
        icon = "🇨🇳" if lang == "zh-CN" else ("🇹🇼" if lang == "zh-TW" else "🇬🇧")
        print(f"  {icon} 进程: {info.get('process', '?'):<25} "
              f"标题: {info.get('title', '')[:35]:<35} "
              f"→ {get_language_label(lang)}")
        cmd = input("  [Enter刷新 / q返回]: ").strip().lower()
        if cmd == "q":
            break


def add_rule():
    """添加自定义规则"""
    print("\n➕ 添加自定义规则")
    print("   关键词可以是：进程名的一部分，或窗口标题的一部分（不区分大小写）")
    print("   例如：'notion'、'word'、'我的日记' 等")
    print()
    keyword = input("   关键词: ").strip().lower()
    if not keyword:
        return

    print("   选择语言:")
    print("   [1] 繁體中文 (zh-TW)")
    print("   [2] 简体中文 (zh-CN)")
    print("   [3] English  (en，不转换)")
    choice = input("   > ").strip()
    lang_map = {"1": "zh-TW", "2": "zh-CN", "3": "en"}
    lang = lang_map.get(choice)
    if not lang:
        print("   ❌ 无效选择")
        return

    save_custom_rule(keyword, lang)
    print(f"   ✅ 已保存：「{keyword}」→ {get_language_label(lang)}")


def remove_rule():
    """删除自定义规则"""
    if not APP_RULES_FILE.exists():
        print("   没有自定义规则")
        return
    with open(APP_RULES_FILE, "r", encoding="utf-8") as f:
        custom = json.load(f)
    if not custom:
        print("   没有自定义规则")
        return

    print("\n🗑  删除自定义规则")
    items = list(custom.items())
    for i, (k, v) in enumerate(items, 1):
        print(f"   [{i}] {k} → {get_language_label(v)}")
    idx = input("\n   输入序号（留空取消）: ").strip()
    try:
        i = int(idx) - 1
        del custom[items[i][0]]
        with open(APP_RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(custom, f, ensure_ascii=False, indent=2)
        print(f"   ✅ 已删除：{items[i][0]}")
    except (ValueError, IndexError):
        print("   取消")


def main():
    print_header()
    CONFIG_DIR.mkdir(exist_ok=True)

    while True:
        print("主菜单:")
        print("  [1] 查看所有规则")
        print("  [2] 实时检测当前窗口语言")
        print("  [3] 添加自定义规则")
        print("  [4] 删除自定义规则")
        print("  [q] 退出")
        print()
        choice = input("请选择: ").strip().lower()

        if choice == "1":
            show_current_rules()
        elif choice == "2":
            detect_current_window()
        elif choice == "3":
            add_rule()
        elif choice == "4":
            remove_rule()
        elif choice == "q":
            print("👋 再见！")
            break
        else:
            print("请输入有效选项\n")


if __name__ == "__main__":
    main()
