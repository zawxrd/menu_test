import os
import sys
import json
import base64
import csv
import time
import subprocess
from pathlib import Path

def print_help():
    print("""
=============================================================
🍱 菜單轉 CSV 工具 (Menu to CSV Converter)
=============================================================
使用方式:
  1. 直接執行 (會彈出檔案選擇視窗):
     python menu_to_csv.py

  2. 指定檔案執行:
     python menu_to_csv.py <菜單路徑.pdf / .png / .jpg> [輸出路徑.csv]

  環境變數設定 (二擇一):
     - GEMINI_API_KEY (推薦，有免費額度)
     - ANTHROPIC_API_KEY
=============================================================
""")

PROMPT_TEXT = """
你是一個菜單解析助手。請分析這份菜單，按「星期一至星期五」分類提取所有餐點與價格。
請嚴格只輸出合法 JSON 格式，不要包含任何額外 markdown 標記（如 ```json）：
{
  "週一": [{"name": "餐點名稱", "price": 80}],
  "週二": [{"name": "餐點名稱", "price": 90}],
  "週三": [{"name": "餐點名稱", "price": 75}],
  "週四": [{"name": "餐點名稱", "price": 85}],
  "週五": [{"name": "餐點名稱", "price": 80}]
}
注意事項：
1. 星期鍵值固定為："週一", "週二", "週三", "週四", "週五"。
2. 若某天未提供餐點或菜單沒寫，填 [] 空陣列。
3. price 請填整數數字（若未標價請填 0）。
"""

def clean_and_parse_json(raw_text: str) -> dict:
    s = raw_text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1:
        s = s[start:end+1]

    return json.loads(s)

def parse_with_gemini(api_key: str, file_path: Path) -> dict:
    """使用 Google Gemini 原生 REST API (自動列舉可用模型並發送)"""
    import urllib.request
    import urllib.error

    suffix = file_path.suffix.lower()
    mime_type = "application/pdf" if suffix == ".pdf" else f"image/{suffix.replace('.', '')}"
    if mime_type == "image/jpg":
        mime_type = "image/jpeg"

    with open(file_path, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode("utf-8")

    req_body = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    },
                    {
                        "text": PROMPT_TEXT
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1
        }
    }

    available_models = []
    for ver in ["v1beta", "v1"]:
        try:
            req = urllib.request.Request(f"https://generativelanguage.googleapis.com/{ver}/models?key={api_key}")
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("models", []):
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        available_models.append((ver, m["name"]))
        except Exception:
            pass

    def is_vision_model(name: str) -> bool:
        low = name.lower()
        if any(bad in low for bad in ["-tts", "audio", "embed", "imagen", "search"]):
            return False
        return True

    available_models = [m for m in available_models if is_vision_model(m[1])]

    def score_model(item):
        ver, name = item
        score = 0
        if "flash" in name: score += 10
        if "1.5" in name: score += 5
        elif "2.0" in name: score += 4
        if "latest" in name: score += 2
        if "preview" in name: score -= 3
        if ver == "v1": score += 2
        return score

    available_models.sort(key=score_model, reverse=True)

    if not available_models:
        available_models = [
            ("v1beta", "models/gemini-1.5-flash"),
            ("v1", "models/gemini-1.5-flash"),
            ("v1beta", "models/gemini-1.5-flash-latest"),
            ("v1beta", "models/gemini-2.0-flash"),
            ("v1beta", "models/gemini-1.5-pro")
        ]

    last_err = None
    for ver, model_name in available_models:
        url = f"https://generativelanguage.googleapis.com/{ver}/{model_name}:generateContent?key={api_key}"
        print(f"👉 嘗試使用模型: {ver}/{model_name} ...")

        req = urllib.request.Request(
            url,
            data=json.dumps(req_body).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if not candidates:
                    raise RuntimeError("Gemini 未產生回應內容")
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join([p.get("text", "") for p in parts])
                return clean_and_parse_json(text)
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            last_err = f"{ver}/{model_name} (HTTP {e.code}): {err_msg}"
            if "API_KEY_INVALID" in err_msg or "API key not valid" in err_msg:
                raise RuntimeError(f"API 金鑰無效：{err_msg}")
            continue
        except Exception as e:
            last_err = str(e)
            continue

    raise RuntimeError(f"所有可用模型皆無法產生回應：\n{last_err}")

def json_to_csv(data: dict, out_csv_path: Path):
    """將解析後的 JSON 轉成點餐系統標準 CSV"""
    day_order = ["週一", "週二", "週三", "週四", "週五"]
    
    rows = []
    for day in day_order:
        items = data.get(day, [])
        for item in items:
            name = str(item.get("name", "")).strip()
            price = int(item.get("price", 0))
            if name:
                rows.append([day, name, price])

    with open(out_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["星期", "餐點名稱", "價格"])
        writer.writerows(rows)

    project_dir = Path(__file__).parent
    out_json_path = project_dir / "menu.json"

    # 計算本週週一（若今天是週六/週日則取下週週一）
    today = time.localtime()
    weekday = today.tm_wday  # 0=週一, 6=週日
    if weekday <= 4:
        # 週一到週五：取本週週一
        days_to_monday = weekday
    else:
        # 週六=5, 週日=6：取下週週一
        days_to_monday = -(weekday - 7)
    monday_ts = time.mktime(today) - days_to_monday * 86400
    monday_str = time.strftime("%Y-%m-%d", time.localtime(monday_ts))

    payload = {
        "updatedAt": int(time.time() * 1000),
        "validWeekStart": monday_str,
        "menu": data
    }
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return len(rows), out_json_path

def try_git_push(repo_dir: Path):
    """嘗試強健地同步並推送到 GitHub"""
    try:
        check = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo_dir, capture_output=True, text=True)
        if check.returncode != 0:
            print("\nℹ️ 當前目錄尚未初始化 git 倉庫，略過自動推送到 GitHub。")
            return

        print("\n📦 正在自動同步至 GitHub...")
        
        # 1. 先將遠端歷史抓取下來 (fetch)
        subprocess.run(["git", "fetch", "origin"], cwd=repo_dir, capture_output=True, text=True)

        # 2. 加入本地生成的 menu.json 並 commit
        subprocess.run(["git", "add", "menu.json"], cwd=repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", "chore: auto update menu.json from AI tool"], cwd=repo_dir, capture_output=True, text=True)

        # 3. 嘗試以 -X ours 模式 merge 遠端變更，自動以本地生成的 menu.json 為主
        merge_res = subprocess.run(["git", "merge", "origin/main", "-m", "chore: merge remote changes", "-X", "ours"], cwd=repo_dir, capture_output=True, text=True)
        
        # 若預設分支名稱是 master，備用處理
        if merge_res.returncode != 0:
            subprocess.run(["git", "merge", "origin/master", "-m", "chore: merge remote changes", "-X", "ours"], cwd=repo_dir, capture_output=True, text=True)

        # 4. 執行推送
        push_res = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=repo_dir, capture_output=True, text=True)
        if push_res.returncode != 0:
            # 備用推送到預設分支
            push_res = subprocess.run(["git", "push"], cwd=repo_dir, capture_output=True, text=True)

        if push_res.returncode == 0:
            print("✨ 成功推送到 GitHub！GitHub Pages 上的菜單已自動完成更新！")
        else:
            # 若常規 merge/push 依然受阻，採用強行覆蓋 (Force Push) 保障菜單更新
            print("⚠️ 偵測到遠端歷史不一致，正在執行強制同步...")
            force_push = subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=repo_dir, capture_output=True, text=True)
            if force_push.returncode == 0:
                print("✨ 成功強制推送到 GitHub！菜單已完成更新！")
            else:
                print(f"⚠️ git push 失敗 (請檢查權限與遠端設定): {force_push.stderr.strip()}")

    except Exception as e:
        print(f"⚠️ 自動 Git 同步略過: {e}")

def select_file_gui():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        file_selected = filedialog.askopenfilename(
            title="請選擇週菜單檔案 (PDF 或 圖片)",
            filetypes=[("Menu Files", "*.pdf;*.png;*.jpg;*.jpeg"), ("All Files", "*.*")]
        )
        root.destroy()
        return file_selected
    except Exception:
        return None

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print_help()
        return

    input_file = None
    if len(sys.argv) > 1:
        input_file = Path(sys.argv[1])
    else:
        print("未指定檔案，正在開啟選擇對話框...")
        gui_file = select_file_gui()
        if gui_file:
            input_file = Path(gui_file)

    if not input_file or not input_file.exists():
        print("❌ 未選擇檔案或檔案不存在！")
        print_help()
        return

    if len(sys.argv) > 2:
        out_csv = Path(sys.argv[2])
    else:
        out_csv = input_file.parent / f"{input_file.stem}_menu.csv"

    KEY_FILE = Path(__file__).parent / ".gemini_api_key"
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key and KEY_FILE.exists():
        try:
            gemini_key = KEY_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    if not gemini_key:
        print("\n🔑 固定使用 Google Gemini 視覺識別模型。")
        print("首次使用請輸入您的 GEMINI_API_KEY：")
        print("（輸入後系統會自動安全儲存在本機，下次執行無需再輸入）")
        gemini_key = input("👉 請輸入 GEMINI_API_KEY: ").strip()
        if gemini_key:
            try:
                KEY_FILE.write_text(gemini_key, encoding="utf-8")
                print("✅ API Key 已成功儲存於本機記憶檔！下次執行將自動讀取。")
            except Exception as e:
                print(f"⚠️ 無法寫入金鑰記憶檔: {e}")

    if not gemini_key:
        print("❌ 未提供 Gemini API 金鑰，終止。")
        return

    print(f"\n🚀 正在使用 Google Gemini 解析檔案: {input_file.name} ...")

    try:
        result = parse_with_gemini(gemini_key, input_file)

        count, json_file = json_to_csv(result, out_csv)
        print(f"\n🎉 轉換成功！共提取 {count} 項餐點。")
        print(f"📄 產生的 CSV 檔案位於: {out_csv.resolve()}")
        print(f"📄 產生的 JSON 檔案位於: {json_file.resolve()}")

        # 自動執行 Git 推送
        try_git_push(Path(__file__).parent)

    except Exception as e:
        print(f"\n❌ 發生錯誤: {e}")

if __name__ == "__main__":
    main()