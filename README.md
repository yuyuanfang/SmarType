# SmarType v6 — AI 全域語音輸入工具

在 **任何** Windows 應用程式中，按住熱鍵說話、放開即輸入文字。類似 [Typeless](https://typeless.ch/)，但開源、可自訂、成本更低。

## 功能特色

- **全域語音輸入** — 瀏覽器、Word、微信、VS Code……任何有游標的地方都能用
- **即時跑馬燈** — 說話過程中即時顯示辨識文字（本地 Whisper Tiny）
- **高精度辨識** — 放開熱鍵後由 Groq Whisper Large v3 Turbo 雲端辨識
- **自動語言切換** — 根據當前視窗自動選擇繁中 / 簡中 / 英文 / 日文 / 韓文
- **中英翻譯** — 在 VS Code 等程式編輯器中說中文，自動翻譯成英文輸出
- **智慧詞典** — 從語音歷史自動學習高頻詞彙，提升辨識率
- **AI 潤色** — 可選用 GPT-4o-mini / Gemini 去除贅字、修正同音字
- **語音日記** — 每次語音輸入自動分類，每晚生成當日摘要
- **簡繁轉換** — 詞彙級轉換（「軟件」↔「軟體」），非僅字符替換
- **管理介面** — 深色主題 Dashboard，一站管理設定、詞庫、歷史

## 系統需求

| 項目 | 需求 |
|------|------|
| 作業系統 | Windows 10 / 11 |
| Python | 3.10+ |
| 麥克風 | 任意音訊輸入裝置 |
| 網路 | 需要（呼叫 Groq / OpenAI API） |

### API 金鑰

| 金鑰 | 用途 | 必要性 |
|------|------|--------|
| [Groq API Key](https://console.groq.com/keys) | 主力語音辨識（Whisper Large v3 Turbo） | **必要** |
| [OpenAI API Key](https://platform.openai.com/api-keys) | 備用辨識 + LLM 潤色 / 翻譯 | 選用 |
| [Gemini API Key](https://aistudio.google.com/apikey) | 備用 LLM 潤色 / 翻譯 | 選用 |

## 安裝步驟

### 1. Clone 倉庫

```bash
git clone https://github.com/YOUR_USERNAME/SmarType.git
cd SmarType
```

### 2. 安裝依賴

```bash
pip install -r requirements.txt
```

> **PyAudio 安裝失敗？** 試試：
> ```bash
> pip install pipwin && pipwin install pyaudio
> ```

### 3. 設定 API Key

```bash
python setup.py
```

或手動編輯 `userdata/config.json`：

```json
{
  "groq_api_key": "你的 Groq API Key",
  "api_key": "",
  "hotkey": "right shift",
  "auto_lang": true,
  "default_lang": "zh-TW"
}
```

### 4. 啟動

```bash
# 方法一：雙擊
start.bat

# 方法二：命令列
python dictation.py
```

> 程式需要管理員權限（全域熱鍵監聽需要）。`start.bat` 會自動提權。

## 使用方法

1. 啟動後，系統匣出現綠色圖示
2. 切換到任意應用程式，將游標放在輸入位置
3. **按住 Right Shift** — 開始錄音（螢幕底部出現綠色膠囊跑馬燈）
4. **說話**（即時看到辨識文字）
5. **放開 Right Shift** — 完成辨識，文字自動貼上

### 語音辨識流程

```
按住熱鍵 → 錄音開始
  ├── 每 3 秒 → 本地 Whisper Tiny 即時辨識（跑馬燈預覽）
  └── 放開熱鍵 → 完整音訊送 Groq Whisper Large v3 Turbo
       ├── 成功 → 文字輸出
       └── 失敗 → 備用 OpenAI Whisper-1
```

## 專案結構

```
SmarType/
├── dictation.py           # 核心語音聽寫引擎
├── dashboard.py           # 管理介面（CustomTkinter）
├── setup.py               # 首次設定精靈
├── converter.py           # 簡繁轉換器
├── window_detector.py     # 視窗語言自動偵測
├── smart_vocab.py         # 智慧詞彙學習
├── vocab_manager.py       # 詞彙管理 CLI
├── data_flywheel.py       # 數據飛輪系統
├── diary_engine.py        # 語音日記引擎
├── app_rules.py           # 應用程式規則
├── local_transcriber.py   # 本地轉錄（sherpa-onnx）
├── streaming_transcriber.py # 串流轉錄
├── start.bat              # 啟動腳本
├── requirements.txt       # Python 依賴
├── userdata/              # 使用者資料（不上傳）
│   ├── config.json        # 設定檔（含 API Key）
│   ├── vocabulary.json    # 詞彙庫
│   ├── smart_dict.json    # 智慧詞典
│   └── diary/             # 語音日記
└── models/                # 本地模型（不上傳）
```

## 費用參考

使用 Groq API（免費額度慷慨）+ OpenAI Whisper 備用：

| 使用量 | OpenAI 費用 |
|--------|-------------|
| 每天 10 分鐘 | ~$1.8/月 |
| 每天 30 分鐘 | ~$5.4/月 |
| 每天 1 小時 | ~$10.8/月 |

> Groq 目前提供免費 API 額度，日常使用幾乎零成本。

## 詳細文件

- [使用手冊](USER_MANUAL.md) — 完整功能說明與疑難排解
- [貢獻指南](CONTRIBUTING.md) — 如何參與開發

## 授權

[MIT License](LICENSE)
