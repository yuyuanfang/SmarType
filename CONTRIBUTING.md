# Contributing to SmarType

感謝你有興趣為 SmarType 做出貢獻！以下是參與方式。

## 開發環境設置

1. Fork 並 clone 本倉庫
2. 安裝 Python 3.10+
3. 安裝依賴：
   ```bash
   pip install -r requirements.txt
   ```
4. 複製設定範本：
   ```bash
   copy userdata\config.example.json userdata\config.json
   ```
5. 填入你自己的 API Key

## 提交 Pull Request

1. 從 `main` 分支建立新分支：
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. 進行修改
3. 執行自測確認通過：
   ```bash
   python test_startup.py
   ```
4. 提交變更並推送：
   ```bash
   git add .
   git commit -m "feat: 簡短描述你的變更"
   git push origin feature/your-feature-name
   ```
5. 在 GitHub 上建立 Pull Request

## Commit 訊息格式

採用 [Conventional Commits](https://www.conventionalcommits.org/)：

- `feat:` 新功能
- `fix:` 修復 Bug
- `docs:` 文件更新
- `refactor:` 重構（不改變功能）
- `test:` 測試相關
- `chore:` 建置/工具變更

## 注意事項

- **不要提交 API Key** — `userdata/config.json` 已在 `.gitignore` 中
- **不要提交模型檔案** — `models/` 目錄已在 `.gitignore` 中
- 保持程式碼風格一致（中文註釋為主）
- 新增功能請附帶使用說明

## 回報問題

請在 GitHub Issues 中回報，並附上：
- 作業系統版本
- Python 版本
- 錯誤訊息或截圖
- 重現步驟

## 授權

提交貢獻即表示你同意以 [MIT License](LICENSE) 授權你的程式碼。
