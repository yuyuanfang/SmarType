"""
窗口检测器 - Window Detector
检测当前活动窗口，自动判断应使用简体还是繁体中文
"""

import re
import json
from pathlib import Path

try:
    import win32gui
    import win32process
    import psutil
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

CONFIG_DIR = Path(__file__).parent / "userdata"
APP_RULES_FILE = CONFIG_DIR / "app_rules.json"

# ── 内建应用规则 ───────────────────────────────────────────────────────────────
# 格式: { "匹配关键词": "zh-TW" 或 "zh-CN" 或 "en" }
# 匹配范围: 进程名 或 窗口标题（不区分大小写）

DEFAULT_APP_RULES = {
    # ── 简体中文环境 ──
    "wechat":           "zh-CN",
    "weixin":           "zh-CN",
    "微信":              "zh-CN",
    "qq":               "zh-CN",
    "腾讯":              "zh-CN",
    "dingtalk":         "zh-CN",
    "钉钉":              "zh-CN",
    "feishu":           "zh-CN",
    "飞书":              "zh-CN",
    "lark":             "zh-CN",
    "企业微信":           "zh-CN",
    "wxwork":           "zh-CN",

    # ── 繁体中文环境 ──
    "facebook":         "zh-TW",
    "instagram":        "zh-TW",
    "line":             "zh-TW",
    "telegram":         "zh-TW",
    "discord":          "zh-TW",
    "whatsapp":         "zh-TW",
    "twitter":          "zh-TW",
    "x.com":            "zh-TW",

    # ── 邮件（混合，默认繁体）──
    "outlook":          "zh-TW",
    "thunderbird":      "zh-TW",
    "gmail":            "zh-TW",

    # ── 文书软件（默认繁体）──
    "word":             "zh-TW",
    "winword":          "zh-TW",
    "pages":            "zh-TW",
    "notion":           "zh-TW",
    "obsidian":         "zh-TW",
    "onenote":          "zh-TW",
    "evernote":         "zh-TW",

    # ── 开发工具（直接輸出繁體中文，Claude/Cursor 皆可理解）──
    "claude":           "zh-TW",
    "code":             "zh-TW",
    "vscode":           "zh-TW",
    "visual studio":    "zh-TW",
    "pycharm":          "zh-TW",
    "intellij":         "zh-TW",
    "webstorm":         "zh-TW",
    "goland":           "zh-TW",
    "rider":            "zh-TW",
    "cursor":           "zh-TW",
    "windsurf":         "zh-TW",
    "zed":              "zh-TW",
    "sublime":          "zh-TW",
    "terminal":         "zh-TW",
    "cmd":              "zh-TW",
    "powershell":       "zh-TW",
    "wt":               "zh-TW",       # Windows Terminal
    "notepad++":        "zh-TW",
    "vim":              "zh-TW",
    "neovim":           "zh-TW",
    "github":           "zh-TW",

    # ── 浏览器（根据网址判断，默认繁体）──
    "chrome":           "zh-TW",
    "firefox":          "zh-TW",
    "edge":             "zh-TW",
    "msedge":           "zh-TW",
    "opera":            "zh-TW",
    "brave":            "zh-TW",
}

# 浏览器标题关键词 → 覆盖浏览器默认语言
BROWSER_TITLE_RULES = {
    # 简体
    "微信网页版":        "zh-CN",
    "bilibili":         "zh-CN",
    "哔哩哔哩":          "zh-CN",
    "weibo":            "zh-CN",
    "微博":              "zh-CN",
    "zhihu":            "zh-CN",
    "知乎":              "zh-CN",
    "baidu":            "zh-CN",
    "百度":              "zh-CN",
    "taobao":           "zh-CN",
    "淘宝":              "zh-CN",
    "jd.com":           "zh-CN",
    "京东":              "zh-CN",

    # 繁体
    "facebook":         "zh-TW",
    "instagram":        "zh-TW",
    "twitter":          "zh-TW",
    "youtube":          "zh-TW",
    "gmail":            "zh-TW",
    "notion":           "zh-TW",
    "ptt":              "zh-TW",
}


def load_app_rules() -> dict:
    """加载应用规则（内建 + 用户自定义）"""
    rules = DEFAULT_APP_RULES.copy()
    if APP_RULES_FILE.exists():
        try:
            with open(APP_RULES_FILE, "r", encoding="utf-8") as f:
                custom = json.load(f)
            rules.update(custom)  # 用户规则覆盖内建
        except Exception:
            pass
    return rules


def save_custom_rule(keyword: str, lang: str):
    """保存用户自定义规则"""
    CONFIG_DIR.mkdir(exist_ok=True)
    custom = {}
    if APP_RULES_FILE.exists():
        try:
            with open(APP_RULES_FILE, "r", encoding="utf-8") as f:
                custom = json.load(f)
        except Exception:
            pass
    custom[keyword.lower()] = lang
    with open(APP_RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(custom, f, ensure_ascii=False, indent=2)


def get_active_window_info() -> dict:
    """
    获取当前活动窗口信息
    返回: {"process": "chrome.exe", "title": "Facebook - Google Chrome", "lang": "zh-TW"}
    """
    info = {"process": "", "title": "", "process_name": "", "lang": "zh-TW"}

    if not WIN32_AVAILABLE:
        return info

    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        info["title"] = title

        # 获取进程名
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            proc = psutil.Process(pid)
            process_name = proc.name().lower()
            info["process"] = proc.name()
            info["process_name"] = process_name
        except Exception:
            process_name = ""

        # 判断语言
        info["lang"] = detect_language(process_name, title)

    except Exception:
        pass

    return info


def detect_language(process_name: str, window_title: str) -> str:
    """
    根据进程名和窗口标题判断目标语言
    优先级: 浏览器标题规则 > 进程名规则 > 默认
    """
    rules = load_app_rules()
    title_lower = window_title.lower()
    process_lower = process_name.lower()

    # 检查是否是浏览器
    browsers = ["chrome", "firefox", "edge", "msedge", "opera", "brave", "vivaldi"]
    is_browser = any(b in process_lower for b in browsers)

    if is_browser:
        # 浏览器：优先用窗口标题匹配
        for keyword, lang in BROWSER_TITLE_RULES.items():
            if keyword.lower() in title_lower:
                return lang
        # 浏览器默认繁体（你的社交媒体多为繁体）
        return "zh-TW"

    # 非浏览器：用进程名匹配
    for keyword, lang in rules.items():
        if keyword.lower() in process_lower:
            return lang

    # 进程名没匹配到，试窗口标题
    for keyword, lang in rules.items():
        if keyword.lower() in title_lower:
            return lang

    # 默认繁体
    return "zh-TW"


def get_language_label(lang: str) -> str:
    labels = {
        "zh-TW": "繁體中文",
        "zh-CN": "简体中文",
        "en":    "English",
        "zh":    "中文",
    }
    return labels.get(lang, lang)


# ── 调试工具 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import time
    print("🔍 窗口检测调试模式（每2秒刷新一次，Ctrl+C 退出）\n")
    while True:
        info = get_active_window_info()
        lang_label = get_language_label(info["lang"])
        print(f"\r  进程: {info['process']:<25} 标题: {info['title'][:40]:<40} 语言: {lang_label}", end="", flush=True)
        time.sleep(2)
