# SmarType 問題排查交接文件

**日期：** 2026-03-28
**專案路徑：** `C:\whisper-dictation\`

---

## 一、已解決的問題

### 1. 托盤圖標不顯示（啟動失敗）
**根本原因：** 三個問題疊加
- `start.bat` 使用了 Linux 語法（`/dev/null`），Python 根本未執行
- `userdata/vocabulary.json` 編碼損壞，JSON 解析失敗導致啟動崩潰
- `ensure_admin()` 的 UAC 提權在非 admin 下靜默失敗，子進程不啟動

**解決方式：**
- 重寫 `start.bat`，使用正確 Windows 語法
- 備份並重建 `vocabulary.json`（空白初始值）
- 完全移除 `ensure_admin()` 函數（Windows 11 上 `keyboard` 模組不需要 admin）

---

### 2. 點擊托盤 → Dashboard 開兩個視窗
**根本原因：** `Global\\SmarType_Dashboard_v1` mutex 非 admin 下創建失敗，單例檢測失效

**解決方式：**
- `dictation.py` 和 `dashboard.py` 都將 `Global\\SmarType_Dashboard_v1` 改為 `SmarType_Dashboard_v1`（去掉 `Global\\`）
- 重構開啟邏輯：`dictation.py` 只管 `Popen`，`dashboard.py` 自己負責單例判斷（若已有實例則寫 signal 給現有進程後退出）

---

## 二、尚未解決的問題

### 3. 識別結果重複輸出（最優先）
**現象：** 每次錄音輸出兩段完全相同的文字

**根本原因（已確認）：**
`SmarTypeApp` 單例 mutex 同樣使用 `Global\\` 前綴：
```python
# dictation.py line ~1143
ctypes.windll.kernel32.CreateMutexW(None, True, "Global\\SmarType_v6_SingleInstance")
```
非 admin 下 mutex 創建失敗 → 單例檢測失效 → **兩個 SmarTypeApp 實例同時運行** → 所有事件（錄音、識別、注入）×2

**已修改的程式碼：**
```python
# 已改為（dictation.py）
ctypes.windll.kernel32.CreateMutexW(None, True, "SmarType_v6_SingleInstance")
```
✅ 代碼已改好，**但尚未生效**，因為舊的兩個進程仍在運行。

**待完成動作：**
- 用任務管理器手動結束所有 `python.exe` 進程（PowerShell 因權限不足無法強制停止）
- 或直接重開機
- 重新雙擊 `start.bat`

---

### 4. Dashboard 閃退
**現象：** 點擊托盤 → Dashboard 出現後立刻關閉

**根本原因（推測）：**
問題 3 導致兩個 dictation.py 實例都在跑，兩個都呼叫 `_on_show_dashboard()`，各自 `Popen dashboard.py`。第二個 dashboard.py 進程看到 mutex 已存在，立刻退出 → 這就是「閃退」。

**預期結果：** 解決問題 3（重啟進程）後，閃退應自動消失，無需額外修改。

---

### 5. Dashboard 字體過大、內容被遮蔽
**現象：** 字體偏大，部分內容超出視窗被遮蓋

**已修改的程式碼（`dashboard.py`）：**
```python
# 全部縮小 2 號
FONT_TITLE  = ("Microsoft YaHei", 22, "bold")  # 原 24
FONT_HEAD   = ("Microsoft YaHei", 15, "bold")  # 原 17
FONT_BODY   = ("Microsoft YaHei", 13)           # 原 15
FONT_SMALL  = ("Microsoft YaHei", 11)           # 原 13
FONT_MONO   = ("Consolas", 12)                  # 原 14
# sidebar 標題 34→30，卡片數字 22→20，等
```
✅ 代碼已改好，**重啟後生效**。

---

## 三、下一步行動順序

```
1. 重啟所有進程
   → 任務管理器結束所有 python.exe
   → 雙擊 start.bat

2. 驗證識別重複是否消失（問題 3）

3. 驗證 Dashboard 閃退是否消失（問題 4）

4. 確認字體大小是否合適（問題 5）
   → 若還是太大/太小，告知再調整

5. 下一個功能：Flet 重寫 Dashboard（用戶有興趣，待確認）
```

---

## 四、關鍵技術備忘

| 問題類型 | 原因 | 解法 |
|---------|------|------|
| mutex 失效 | `Global\\` 前綴需要 admin 權限 | 去掉 `Global\\`，改用 session 級 mutex |
| 啟動崩潰 | JSON 文件損壞 | 備份並重建 `userdata/vocabulary.json` |
| UAC 問題 | `ensure_admin()` 靜默失敗 | 直接移除，Windows 11 keyboard 不需要 admin |

**診斷技巧（可重用）：**
- 在 `if __name__ == "__main__":` 第一行加 `_dbg(f"PROCESS START pid={os.getpid()}")` 確認進程是否啟動
- 用 `try/except` 包住 `App().run()` 並寫 traceback 到 log，捕捉啟動崩潰
- 雙進程問題的特徵：log 裡每個事件都出現兩次，時間差 < 5ms
