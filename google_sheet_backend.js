/**
 * 🍱 點餐系統 - Google Apps Script 後端與全域雲端設定同步服務
 * 支援功能：
 * 1. 訂單即時寫入與同座號覆蓋
 * 2. 系統設定（座位數、截止時間、管理Email、回報時間、管理密碼）雲端雙向同步
 * 3. 每日定時自動發送訂單彙總 Email
 */

// ===================== 基本常數 =====================
const SHEET_ORDERS = "訂單紀錄";
const SHEET_SETTINGS = "系統設定";
const EMAIL_SUBJECT_PREFIX = "🍱 今日點餐統計回報";

/**
 * 取得或初始化「系統設定」工作表
 */
function getSettingsMap() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_SETTINGS);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_SETTINGS);
    sheet.appendRow(["設定鍵值", "設定內容", "備註說明"]);
    sheet.setFrozenRows(1);
    sheet.getRange("B:B").setNumberFormat("@");
    // 寫入預設值
    sheet.appendRow(["seatCount", "30", "座位數量"]);
    sheet.appendRow(["cutoffTime", "12:00", "每日點餐截止時間 (HH:mm)"]);
    sheet.appendRow(["adminEmail", "", "管理者 Email"]);
    sheet.appendRow(["reportTime", "12:00", "自動回報時間 (HH:mm)"]);
    sheet.appendRow(["adminPassword", "admin1234", "維護端登入密碼"]);
  }

  const rows = sheet.getDataRange().getValues();
  const settings = {
    seatCount: 30,
    cutoffTime: "12:00",
    adminEmail: "",
    reportTime: "12:00",
    adminPassword: "admin1234"
  };

  for (let i = 1; i < rows.length; i++) {
    const key = String(rows[i][0]).trim();
    const rawVal = rows[i][1];
    let val = String(rawVal).trim();
    if (key && rawVal !== undefined) {
      if (key === "seatCount") {
        settings[key] = Number(val) || 30;
      } else if (key === "cutoffTime" || key === "reportTime") {
        settings[key] = normalizeTimeStr(rawVal) || "12:00";
      } else {
        settings[key] = val;
      }
    }
  }
  return settings;
}

/**
 * 儲存設定至「系統設定」工作表
 */
function saveSettingsToSheet(newSettings) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_SETTINGS);
  if (!sheet) {
    getSettingsMap();
    sheet = ss.getSheetByName(SHEET_SETTINGS);
  }
  sheet.getRange("B:B").setNumberFormat("@");

  const rows = sheet.getDataRange().getValues();
  const keys = Object.keys(newSettings);

  for (const key of keys) {
    let saveVal = String(newSettings[key]);
    if (key === "cutoffTime" || key === "reportTime") {
      saveVal = normalizeTimeStr(newSettings[key]) || "12:00";
    }
    let found = false;
    for (let i = 1; i < rows.length; i++) {
      if (String(rows[i][0]).trim() === key) {
        const cell = sheet.getRange(i + 1, 2);
        cell.setNumberFormat("@");
        cell.setValue(saveVal);
        found = true;
        break;
      }
    }
    if (!found) {
      sheet.appendRow([key, saveVal, "自訂設定"]);
      sheet.getRange(sheet.getLastRow(), 2).setNumberFormat("@");
    }
  }
}

/**
 * 輔助函式：格式化日期為 YYYY-MM-DD
 */
function normalizeDateStr(val) {
  if (!val) return "";
  if (val instanceof Date) {
    return Utilities.formatDate(val, "Asia/Taipei", "yyyy-MM-dd");
  }
  const s = String(val).trim();
  if (s.indexOf("T") !== -1) {
    try {
      const d = new Date(s);
      return Utilities.formatDate(d, "Asia/Taipei", "yyyy-MM-dd");
    } catch(e) {}
  }
  return s.split(" ")[0];
}

/**
 * 輔助函式：格式化時間為 HH:mm
 */
function normalizeTimeStr(val) {
  if (!val) return "";
  if (val instanceof Date) {
    return Utilities.formatDate(val, "Asia/Taipei", "HH:mm");
  }
  const s = String(val).trim();
  if (s.indexOf("T") !== -1) {
    try {
      const d = new Date(s);
      return Utilities.formatDate(d, "Asia/Taipei", "HH:mm");
    } catch(e) {}
  }
  return s;
}

/**
 * 1. 處理網頁端 POST 請求 (支援點餐寫入 OR 儲存系統設定)
 */
function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    
    // 【模式 A】：儲存系統設定
    if (data.action === "saveSettings") {
      saveSettingsToSheet(data.settings || {});
      return ContentService.createTextOutput(JSON.stringify({ status: "success", message: "設定已儲存至雲端" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 【模式 B】：由網頁立即觸發由雲端寄信
    if (data.action === "sendEmailNow") {
      const targetDate = data.targetDateStr ? normalizeDateStr(data.targetDateStr) : null;
      const res = sendDailySummaryEmail(targetDate, true);
      return ContentService.createTextOutput(JSON.stringify(res))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 【模式 C】：刪除單筆訂單
    if (data.action === "deleteOrder") {
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const sheet = ss.getSheetByName(SHEET_ORDERS);
      if (sheet) {
        const rows = sheet.getDataRange().getValues();
        for (let i = rows.length - 1; i >= 1; i--) {
          const rowId = String(rows[i][0]);
          const rowDate = normalizeDateStr(rows[i][1]);
          const rowSeat = Number(rows[i][3]);
          if ((data.id && rowId === String(data.id)) || (data.targetDateStr && rowDate === normalizeDateStr(data.targetDateStr) && rowSeat === Number(data.seat))) {
            sheet.deleteRow(i + 1);
          }
        }
      }
      return ContentService.createTextOutput(JSON.stringify({ status: "success", message: "訂單已從雲端刪除" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 【模式 D】：清除指定日期的所有訂單
    if (data.action === "clearDayOrders") {
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const sheet = ss.getSheetByName(SHEET_ORDERS);
      if (sheet) {
        const rows = sheet.getDataRange().getValues();
        const targetDate = data.targetDateStr ? normalizeDateStr(data.targetDateStr) : null;
        const targetDayOfWeek = data.dayOfWeek ? Number(data.dayOfWeek) : null;
        const dayKeys = { '週一': 1, '週二': 2, '週三': 3, '週四': 4, '週五': 5 };

        for (let i = rows.length - 1; i >= 1; i--) {
          const rowDate = normalizeDateStr(rows[i][1]);
          const rowDayName = String(rows[i][2] || '');
          const rowDayOfWeek = dayKeys[rowDayName] || 0;

          if (targetDate && rowDate === targetDate) {
            sheet.deleteRow(i + 1);
          } else if (targetDayOfWeek && rowDayOfWeek === targetDayOfWeek) {
            sheet.deleteRow(i + 1);
          }
        }
      }
      return ContentService.createTextOutput(JSON.stringify({ status: "success", message: "指定日訂單已從雲端清除" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 【模式 E】：清除全部訂單
    if (data.action === "clearAllOrders") {
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const sheet = ss.getSheetByName(SHEET_ORDERS);
      if (sheet && sheet.getLastRow() > 1) {
        sheet.deleteRows(2, sheet.getLastRow() - 1);
      }
      return ContentService.createTextOutput(JSON.stringify({ status: "success", message: "全部訂單已從雲端清除" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 【模式 F】：點餐送出
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = ss.getSheetByName(SHEET_ORDERS);
    
    if (!sheet) {
      sheet = ss.insertSheet(SHEET_ORDERS);
      sheet.appendRow(["訂單ID", "預訂日期", "星期", "座號", "餐點名稱", "價格", "訂購時間"]);
      sheet.setFrozenRows(1);
      sheet.getRange("B:B").setNumberFormat("@");
      sheet.getRange("G:G").setNumberFormat("@");
    }

    const targetDate = normalizeDateStr(data.targetDateStr);
    const seat = Number(data.seat);
    const nowTime = normalizeTimeStr(data.time || new Date());
    const dayName = data.dayName || "";

    const rows = sheet.getDataRange().getValues();

    // 檢查同日同座號，落實覆蓋更新
    let updated = false;
    for (let i = 1; i < rows.length; i++) {
      const rowDate = normalizeDateStr(rows[i][1]);
      const rowSeat = Number(rows[i][3]);

      if (rowDate === targetDate && rowSeat === seat) {
        sheet.getRange(i + 1, 1, 1, 7).setValues([[
          data.id || Utilities.getUuid(),
          targetDate,
          dayName,
          seat,
          data.mealName,
          Number(data.price) || 0,
          nowTime
        ]]);
        updated = true;
        break;
      }
    }

    if (!updated) {
      sheet.appendRow([
        data.id || Utilities.getUuid(),
        targetDate,
        dayName,
        seat,
        data.mealName,
        Number(data.price) || 0,
        nowTime
      ]);
    }

    return ContentService.createTextOutput(JSON.stringify({ status: "success", updated: updated }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: error.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * 2. 處理網頁端 GET 請求 (同時回傳訂單與雲端設定)
 */
function doGet(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_ORDERS);
  
  // 1. 取得雲端設定
  const settings = getSettingsMap();

  // 2. 取得訂單紀錄
  const cleanOrders = [];
  if (sheet) {
    const rows = sheet.getDataRange().getValues();
    const orderMap = {};

    for (let i = 1; i < rows.length; i++) {
      const rawDate = rows[i][1];
      const rawSeat = rows[i][3];
      if (!rawDate || !rawSeat) continue;

      const dateStr = normalizeDateStr(rawDate);
      const seatNum = Number(rawSeat);
      const timeStr = normalizeTimeStr(rows[i][6]);

      const orderKey = dateStr + "_" + seatNum;
      orderMap[orderKey] = {
        id: String(rows[i][0] || Utilities.getUuid()),
        targetDateStr: dateStr,
        dayName: String(rows[i][2] || ''),
        seat: seatNum,
        mealName: String(rows[i][4] || ''),
        price: Number(rows[i][5]) || 0,
        time: timeStr
      };
    }

    Object.values(orderMap).forEach(o => cleanOrders.push(o));
    cleanOrders.sort((a, b) => a.seat - b.seat);
  }

  // 同時打包回傳 orders 與 settings
  const payload = {
    orders: cleanOrders,
    settings: settings
  };

  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * 3. 每日定時自動寄信函式
 * @param {string} customDateStr - 指定寄送日期 (YYYY-MM-DD)，若無則使用當日
 * @param {boolean} isTest - 是否為測試/手動發送模式 (若當日無訂單，自動抓取最新紀錄測試發信)
 */
function sendDailySummaryEmail(customDateStr, isTest) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_ORDERS);
  if (!sheet) {
    console.error("❌ 找不到工作表「" + SHEET_ORDERS + "」");
    return { status: "error", message: "找不到訂單工作表" };
  }

  const settings = getSettingsMap();
  const adminEmail = settings.adminEmail;
  if (!adminEmail) {
    console.warn("⚠️ 未設定管理者 Email，略過寄信。請先至系統設定填寫 adminEmail。");
    return { status: "error", message: "尚未設定管理者 Email" };
  }

  const targetDateStr = customDateStr ? normalizeDateStr(customDateStr) : Utilities.formatDate(new Date(), "Asia/Taipei", "yyyy-MM-dd");
  const rows = sheet.getDataRange().getValues();
  
  const targetMap = {};
  const allOrdersList = [];

  for (let i = 1; i < rows.length; i++) {
    const dateStr = normalizeDateStr(rows[i][1]);
    const seatNum = Number(rows[i][3]);
    if (!dateStr || !seatNum) continue;

    const orderObj = {
      dateStr: dateStr,
      seat: seatNum,
      mealName: String(rows[i][4]),
      price: Number(rows[i][5]) || 0,
      time: normalizeTimeStr(rows[i][6])
    };
    allOrdersList.push(orderObj);

    if (dateStr === targetDateStr) {
      targetMap[seatNum] = orderObj;
    }
  }

  let finalOrders = Object.values(targetMap);
  finalOrders.sort((a, b) => a.seat - b.seat);
  let isFallbackTest = false;

  if (finalOrders.length === 0) {
    if (isTest) {
      // 測試模式下若今日無訂單，自動抓取最新一天的訂單寄出測試
      if (allOrdersList.length > 0) {
        allOrdersList.sort((a, b) => b.dateStr.localeCompare(a.dateStr));
        const latestDate = allOrdersList[0].dateStr;
        finalOrders = allOrdersList.filter(o => o.dateStr === latestDate);
        finalOrders.sort((a, b) => a.seat - b.seat);
        isFallbackTest = true;
      } else {
        // 試算表完全沒有任何訂單，發送系統連線成功驗證信
        MailApp.sendEmail({
          to: adminEmail,
          subject: "【測試成功】點餐系統自動回報服務運作正常",
          body: "您好！\n\n這是一封來自點餐系統的測試信件。\n代表您的 Google Apps Script Gmail 發信權限已順利授權，信件發送服務完全正常！\n\n目前試算表中尚無任何訂單紀錄，當有訂單時將會在自動回報時間發送每日統計。\n\n管理者 Email: " + adminEmail
        });
        console.log("✅ 已成功發送測試驗證信至: " + adminEmail);
        return { status: "success", message: "已發送連線驗證信至 " + adminEmail };
      }
    } else {
      console.log("今日 (" + targetDateStr + ") 尚無訂單，略過寄信。");
      return { status: "skipped", message: "今日無訂單，略過寄信" };
    }
  }

  const sendDateStr = isFallbackTest ? finalOrders[0].dateStr + " (最新紀錄)" : targetDateStr;
  const totalAmount = finalOrders.reduce((acc, cur) => acc + cur.price, 0);
  const counts = {};
  const seats = {};
  finalOrders.forEach(o => {
    counts[o.mealName] = (counts[o.mealName] || 0) + 1;
    if (!seats[o.mealName]) seats[o.mealName] = [];
    seats[o.mealName].push(o.seat);
  });

  let body = "📋 點餐統計回報 (" + sendDateStr + ")\n";
  body += "━━━━━━━━━━━━━━━━━━━━━━━\n";
  body += "總訂單數：" + finalOrders.length + " 筆\n";
  body += "總計金額：$" + totalAmount + " 元\n\n";

  body += "── 🍱 餐點數量統計 ──\n";
  Object.keys(counts).sort((a, b) => counts[b] - counts[a]).forEach(name => {
    const seatList = (seats[name] || []).sort((a, b) => a - b).join("、");
    body += "・" + name + " (" + seatList + ") " + counts[name] + " 份\n";
  });

  body += "\n── 📝 座號詳細清單 ──\n";
  finalOrders.forEach(o => {
    body += "座號 " + o.seat + " ➔ " + o.mealName + " ($" + o.price + ")\n";
  });

  body += "\n━━━━━━━━━━━━━━━━━━━━━━━\n";
  body += "本信件由 Google 試算表點餐系統自動發送。";

  MailApp.sendEmail({
    to: adminEmail,
    subject: EMAIL_SUBJECT_PREFIX + " (" + sendDateStr + ") - 共 " + finalOrders.length + " 筆",
    body: body
  });

  console.log("✅ 已成功發送訂單統計信件至: " + adminEmail);
  return { status: "success", message: "已成功發送信件至 " + adminEmail, count: finalOrders.length };
}

/**
 * 4. 自動建立每日定時寄信觸發條件
 * 在 Apps Script 編輯器上方選擇此函式並點擊「執行」，即可一鍵設定好排程！
 */
function setupDailyTrigger() {
  // 1. 刪除既有的 sendDailySummaryEmail 觸發器，避免重複建立
  const triggers = ScriptApp.getProjectTriggers();
  for (let i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === "sendDailySummaryEmail") {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }

  // 2. 讀取設定的自動回報時間 (預設 12:00)
  const settings = getSettingsMap();
  const reportTime = settings.reportTime || "12:00";
  const hour = parseInt(reportTime.split(":")[0], 10) || 12;

  // 3. 建立每日指定小時的定時觸發器
  ScriptApp.newTrigger("sendDailySummaryEmail")
    .timeBased()
    .everyDays(1)
    .atHour(hour)
    .inTimezone("Asia/Taipei")
    .create();

  console.log("✅ 已成功建立每日定時回報觸發條件！預計每天 " + hour + ":00 ~ " + (hour + 1) + ":00 自動發送回報至 " + (settings.adminEmail || "（未設定 Email）"));
  return "觸發條件建立成功（每日 " + hour + " 點執行）";
}

/**
 * 5. 手動測試發送 Email 函式
 * 在 Apps Script 編輯器上方選擇此函式並點擊「執行」，即可立即測試發信並完成 Gmail 授權！
 */
function testSendEmail() {
  console.log("🚀 開始執行測試發信...");
  const settings = getSettingsMap();
  if (!settings.adminEmail) {
    console.error("❌ 失敗：尚未設定 adminEmail！請先至網頁「設定」頁面填寫管理者 Email 並儲存。");
    return;
  }
  const res = sendDailySummaryEmail(null, true);
  console.log("執行結果：", res);
}
