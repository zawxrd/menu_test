/**
 * 🍱 點餐系統 - 全域雲端連線設定檔 (config.js)
 * 
 * 💡 說明：
 * 所有系統設定（座位數量、截止時間、管理者 Email、回報時間、管理密碼）
 * 現已全部支援【Google 試算表雲端自動同步】！
 * 
 * 🚀 部署至 GitHub Pages 前：
 * 請將你在 Google Apps Script 部署取得的「網路應用程式網址」填入下方的 googleSheetUrl。
 * 這樣任何同仁用自己的手機打開網頁，就會自動連上雲端，同步所有最新設定與訂單！
 */
window.DEFAULT_CONFIG = {
  // Google 試算表 Web App 網址 (必填，例如：https://script.google.com/macros/s/.../exec)
  googleSheetUrl: ""
};
