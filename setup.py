"""
首次设置向导 - First-time Setup Wizard
"""

import json
import sys
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "userdata"
CONFIG_FILE = CONFIG_DIR / "config.json"
VOCAB_FILE = CONFIG_DIR / "vocabulary.json"

DEFAULT_CONFIG = {
    "api_key": "",
    "hotkey": "ctrl+alt",
    "language": "zh",
    "model": "whisper-1",
    "post_process": True,
    "show_tray": True,
    "beep_on_start": True,
    "auto_punctuation": True,
    "insert_method": "clipboard",
}


def print_header():
    print("""
╔══════════════════════════════════════════════════╗
║       🎙  随声 SpeakType - 初始设置              ║
╚══════════════════════════════════════════════════╝
    """)


def setup_api_key(config: dict):
    print("📌 步骤 1/3：设置 OpenAI API Key")
    print("   (在 https://platform.openai.com/api-keys 获取)")
    print(f"   当前值: {'已设置 ✅' if config.get('api_key') else '未设置 ❌'}")
    print()

    key = input("   请输入 API Key (留空跳过): ").strip()
    if key:
        config["api_key"] = key
        print("   ✅ API Key 已保存\n")
    else:
        print("   ⏭  跳过\n")


def setup_hotkey(config: dict):
    print("📌 步骤 2/3：设置快捷键")
    print("   按住此键录音，松开后自动转文字")
    print()
    print("   常用选项:")
    print("   [1] ctrl+alt     (推荐，不冲突)")
    print("   [2] ctrl+shift")
    print("   [3] right shift  (右 Shift 键)")
    print("   [4] f9")
    print("   [5] 自定义")
    print(f"   当前值: {config.get('hotkey', 'ctrl+alt')}")
    print()

    choice = input("   请选择 [1-5，留空保持当前]: ").strip()
    hotkey_map = {
        "1": "ctrl+alt",
        "2": "ctrl+shift",
        "3": "right shift",
        "4": "f9",
    }

    if choice in hotkey_map:
        config["hotkey"] = hotkey_map[choice]
        print(f"   ✅ 快捷键设为: {config['hotkey']}\n")
    elif choice == "5":
        custom = input("   输入自定义快捷键 (如 ctrl+f12): ").strip()
        if custom:
            config["hotkey"] = custom
            print(f"   ✅ 快捷键设为: {config['hotkey']}\n")
    else:
        print(f"   ⏭  保持: {config.get('hotkey')}\n")


def setup_vocabulary(config: dict):
    print("📌 步骤 3/3：添加自定义词汇（可选）")
    print("   用于提升 Whisper 对专有名词的识别率")
    print("   例如：产品名、人名、技术术语等")
    print()

    # 加载现有词汇
    vocab_data = {"custom_words": [], "corrections": {}, "session_count": 0, "total_chars": 0}
    if VOCAB_FILE.exists():
        with open(VOCAB_FILE, "r", encoding="utf-8") as f:
            vocab_data = json.load(f)

    current_words = vocab_data.get("custom_words", [])
    if current_words:
        print(f"   当前词汇 ({len(current_words)} 个): {', '.join(current_words[:10])}")
        if len(current_words) > 10:
            print(f"   ... 还有 {len(current_words) - 10} 个")
    else:
        print("   目前没有自定义词汇")
    print()

    words_input = input("   请输入词汇（逗号分隔，留空跳过）: ").strip()
    if words_input:
        new_words = [w.strip() for w in words_input.replace("，", ",").split(",") if w.strip()]
        for w in new_words:
            if w not in vocab_data["custom_words"]:
                vocab_data["custom_words"].append(w)
        with open(VOCAB_FILE, "w", encoding="utf-8") as f:
            json.dump(vocab_data, f, ensure_ascii=False, indent=2)
        print(f"   ✅ 已添加 {len(new_words)} 个词汇\n")
    else:
        print("   ⏭  跳过\n")

    # 纠错映射
    print("   是否要添加纠错映射？（Whisper 常见识别错误 → 正确文字）")
    print("   例如：'台湾' → '臺灣'，'API Key' → 'API Key'")
    corr_input = input("   输入格式「错误:正确」，逗号分隔（留空跳过）: ").strip()
    if corr_input:
        pairs = corr_input.replace("，", ",").split(",")
        for pair in pairs:
            if ":" in pair or "：" in pair:
                parts = pair.replace("：", ":").split(":", 1)
                if len(parts) == 2:
                    wrong, correct = parts[0].strip(), parts[1].strip()
                    vocab_data["corrections"][wrong] = correct
        with open(VOCAB_FILE, "w", encoding="utf-8") as f:
            json.dump(vocab_data, f, ensure_ascii=False, indent=2)
        print("   ✅ 纠错映射已保存\n")


def setup_insert_method(config: dict):
    print("⚙️  额外设置：文字输入方式")
    print("   [1] 剪贴板粘贴 (推荐，速度快，支持中文)")
    print("   [2] 模拟键盘打字 (慢，不推荐中文)")
    print(f"   当前值: {config.get('insert_method', 'clipboard')}")
    print()
    choice = input("   请选择 [1-2，留空保持当前]: ").strip()
    if choice == "1":
        config["insert_method"] = "clipboard"
    elif choice == "2":
        config["insert_method"] = "type"
    print()


def main():
    print_header()
    CONFIG_DIR.mkdir(exist_ok=True)

    # 加载现有配置
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        config.update(existing)

    setup_api_key(config)
    setup_hotkey(config)
    setup_vocabulary(config)
    setup_insert_method(config)

    # 保存配置
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print("╔══════════════════════════════════════════════════╗")
    print("║  ✅ 设置完成！                                     ║")
    print("║                                                  ║")
    print("║  启动听写工具:                                    ║")
    print("║    python dictation.py                           ║")
    print("║                                                  ║")
    print("║  管理词汇/纠错:                                   ║")
    print("║    python vocab_manager.py                       ║")
    print("╚══════════════════════════════════════════════════╝")

    if not config.get("api_key"):
        print("\n⚠️  提醒：您尚未设置 API Key，工具无法运行")
        print(f"   请编辑文件: {CONFIG_FILE}")
        print('   找到 "api_key" 字段并填入您的 Key')


if __name__ == "__main__":
    main()
