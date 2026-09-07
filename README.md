# 🍱 週一至週五點餐系統 (Food Ordering System)

這是一個極簡、無伺服器後端負擔（Serverless）的便當點餐網頁系統，專門設計部署在 **GitHub Pages** 上。
搭配本機 Python 輔助工具，只需將每週菜單（PDF、PNG、JPG）丟給程式，即可自動透過 AI 辨識並推送到 GitHub，達成全自動更新菜單！

---

## ✨ 系統特色

- 📱 **用戶端 (點餐)**
  - 只需選擇「座號（純數字）」與「餐點」，一鍵送出。
  - 隱私保護：用戶端不會顯示他人點餐內容。
  - 防重複點餐：同座號當天再次點餐會提示並覆蓋前筆訂單。
  - 自動依設定的截止時間（預設中午 12:00）自動切換至隔天或下週一預訂。

- 🛠️ **維護端 (管理)**
  - 預設密碼：`admin1234`（可於設定頁面自行變更）。
  - **菜單管理**：支援手動新增/編輯/刪除，亦可上傳 CSV。
  - **訂單檢視**：按星期檢視訂單、即時統計餐點份數與總金額。
  - **匯出功能**：一鍵匯出各日訂單 CSV，或生成彙總文字供複製發送。
  - **純前端運作**：所有訂單與設定均儲存在瀏覽器 `localStorage` 中。

- 🤖 **本機 AI 自動更新工具 (`menu_to_csv.py`)**
  - 在本機端呼叫 Gemini / Claude API，**不外洩 API Key 到前端**。
  - 支援 **PDF、PNG、JPG** 菜單檔案。
  - 解析後自動產出 CSV，並自動將 `menu.json` 透過 `git push` 推送至 GitHub，線上菜單即時更新！

---

## 📁 專案檔案結構

```text
order-system/
├── index.html           # 點餐系統主要網頁 (部署到 GitHub Pages)
├── menu.json            # 線上最新菜單資料 (由本機工具自動產生與推送)
├── menu_to_csv.py       # 本機 Python 轉檔與自動 Git 推送工具
├── run_converter.bat    # Windows 雙擊快速啟動腳本
└── README.md            # 本專案說明文件
```

---

## 🚀 部署至 GitHub Pages 教學

### 步驟 1：建立 GitHub 倉庫並推送程式碼
在專案目錄下開啟終端機（Terminal / PowerShell），執行：

```bash
# 1. 初始化 Git 倉庫
git init

# 2. 加入所有檔案並提交
git add .
git commit -m "feat: initial commit for order system"

# 3. 連結到你的 GitHub 倉庫 (請替換為你的倉庫網址)
git remote add origin https://github.com/你的帳號/你的倉庫名稱.git

# 4. 推送至 main 分支
git branch -M main
git push -u origin main
```

### 步驟 2：開啟 GitHub Pages
1. 前往 GitHub 倉庫的 **Settings** 頁面。
2. 在左側選單點擊 **Pages**。
3. 在 **Build and deployment** 下的 **Branch** 選擇 `main`，資料夾選擇 `/ (root)`，點擊 **Save**。
4. 等候約 1~2 分鐘，上方會出現專屬的點餐網址（例如：`https://你的帳號.github.io/你的倉庫名稱/`）。

---

## 🤖 每週如何自動更新菜單？

### 1. 安裝環境（僅首次需要）
本機需安裝 Python 3.8+，並安裝 Google GenAI 套件（推薦，免費額度充足）：

```bash
pip install google-genai
```

> **建議設定環境變數**：在系統中新增環境變數 `GEMINI_API_KEY`，這樣每次執行都不需要重複輸入金鑰。

### 2. 更新菜單（每週只要 1 動）
1. 雙擊執行專案目錄下的 **`run_converter.bat`**。
2. 彈出的視窗中選取新一週的菜單檔案（支援 **PDF**、**PNG**、**JPG**）。
3. 程式將自動：
   - 辨識週一至週五餐點與價格。
   - 儲存本機備用 CSV。
   - 更新 `menu.json` 並自動執行 `git commit` & `git push` 上傳至 GitHub。
4. **完成！** 所有打開網頁的用戶都會自動載入最新的週菜單！

---

## 📋 CSV 格式規範（備用手動上傳）

若不使用 Python 工具，亦可在網頁維護端直接拖曳上傳 CSV，格式如下：

```csv
星期,餐點名稱,價格
週一,排骨便當,80
週一,雞腿便當,90
週二,魚排便當,75
週三,控肉飯,70
週四,燒肉便當,85
週五,牛丼,95
```

- 星期支援：`週一～週五`、`1～5`、`Monday～Friday`。
- 第一列標題列會自動識別並略過。

---

## 🔒 常見問題與安全性說明

1. **維護端密碼安全嗎？**
   - 這是純前端驗證系統，適合內部辦公室、班級使用。請勿存放高度敏感的商業機密。
2. **不同裝置可以看到彼此點的餐嗎？**
   - 網頁的訂單儲存在當前瀏覽器的 `localStorage` 中。一般員工點完送出即可；建議統一由**一台特定電腦（如行政或總務的電腦）**開啟維護端進行彙整，或作為固定的點餐公用機。
