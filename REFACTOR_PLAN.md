# SmarType v6 重構需求文件

> 本文件列出目前程式碼的改進項目，按優先級排列。
> 每個項目獨立，可分批執行。完成後請跑 `python selftest.py` 確認不破壞現有功能。

---

## 1. 拆分 dictation.py（優先級：高）

**現狀：** `dictation.py` 共 1383 行，包含錄音、轉錄、UI（跑馬燈/系統匣）、設定管理、熱鍵監聽等所有邏輯。

**目標：** 拆分為以下模組，每個檔案職責單一：

| 新檔案 | 職責 | 從 dictation.py 搬出的內容 |
|--------|------|---------------------------|
| `audio_recorder.py` | 錄音控制 | PyAudio 初始化、錄音 start/stop、WAV 編碼 |
| `transcriber.py` | 語音轉錄 | `Transcriber` class（Gemini/Groq/OpenAI/本地 fallback） |
| `overlay_ui.py` | 跑馬燈 UI | 綠色膠囊視窗、Tkinter overlay 相關程式碼 |
| `tray_icon.py` | 系統匣 | pystray 圖示、右鍵選單、狀態顯示 |
| `config_manager.py` | 設定管理 | config.json 讀寫、DEFAULT_CONFIG、路徑常數 |
| `dictation.py` | 主程式（入口） | 只負責組裝以上模組、啟動主迴圈 |

**要求：**
- 拆分後功能與現在完全一致，不新增不刪減任何功能
- `dictation.py` 作為入口，import 其他模組
- 所有模組共用 `config_manager.py` 的路徑常數與設定讀寫

---

## 2. 拆分 dashboard.py（優先級：高）

**現狀：** `dashboard.py` 共 1748 行，所有 Tab 頁面寫在一個檔案裡。

**目標：** 按 Tab 拆分：

| 新檔案 | 職責 |
|--------|------|
| `dashboard.py` | 主視窗框架、Tab 容器、啟動入口 |
| `tabs/tab_home.py` | 首頁 / 狀態總覽 |
| `tabs/tab_history.py` | 聽寫歷史 |
| `tabs/tab_vocab.py` | 詞庫管理 |
| `tabs/tab_diary.py` | 語音日記 |
| `tabs/tab_settings.py` | 設定頁面 |

**要求：**
- 建立 `tabs/` 目錄，每個 Tab 一個檔案
- 每個 Tab 是一個 class，繼承 `ctk.CTkFrame`
- `dashboard.py` 只負責建立主視窗並載入各 Tab

---

## 3. 拆分 data_flywheel.py（優先級：中）

**現狀：** `data_flywheel.py` 共 1248 行，混合了 N-gram 統計、上下文分析、信心度計算、糾錯邏輯。

**目標：**

| 新檔案 | 職責 |
|--------|------|
| `flywheel/ngram.py` | N-gram 統計與儲存 |
| `flywheel/context.py` | 上下文 profile 分析 |
| `flywheel/confidence.py` | 信心度計算 |
| `flywheel/correction.py` | 糾錯對匯出與應用 |
| `data_flywheel.py` | 整合入口，保持原有 API 不變 |

**要求：**
- 外部程式碼（如 `dictation.py`）呼叫方式不變
- `data_flywheel.py` 改為 re-export 各子模組的函數

---

## 4. 統一註釋語言（優先級：低）

**現狀：** 註釋混合簡體中文、繁體中文、英文。

**目標：** 統一為**繁體中文**（與 UI 和文件一致）。

**範圍：**
- 所有 `.py` 檔案中的中文註釋統一為繁體
- 變數名、函數名維持英文不動
- docstring 統一為繁體中文

---

## 5. 加入標準化測試（優先級：低）

**現狀：** 有 `selftest.py` 和 `test_startup.py`，但不是標準 pytest 格式。

**目標：** 新增 `tests/` 目錄，使用 pytest：

```
tests/
├── test_converter.py      # 簡繁轉換測試
├── test_smart_vocab.py    # 詞彙學習測試
├── test_window_detector.py # 視窗偵測測試
├── test_config_manager.py  # 設定讀寫測試
└── test_data_flywheel.py   # 飛輪邏輯測試
```

**要求：**
- 只測純邏輯模組（不測 UI、不測錄音）
- 每個測試檔案至少 3 個 test case
- 能用 `pytest tests/` 一鍵跑完
- 在 `requirements.txt` 加入 `pytest` 為開發依賴

---

## 注意事項

- 每完成一個項目就獨立 commit，不要一次全改
- 不要改動任何功能邏輯，純重構
- 不要刪除 `selftest.py`（現有使用者可能依賴它）
- 拆分後確保 `start.bat` 和 `start_dashboard.bat` 仍能正常啟動
