import os
import sys
import json
import base64
import csv
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

    # 1. 查詢該 Key 真正支援的模型清單
    available_models = []
    for ver in ["v1beta", "v1"]:
        try:
            req = urllib.request.Request(f"https://generativelanguage.googleapis.com/{ver}/models?key={api_key}")
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("models", []):
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        # m["name"] 格式通常為 "models/gemini-..."
                        name = m["name"]
                        available_models.append((ver, name))
        except Exception:
            pass

    # 依優先順序排序: flash > pro
    def score_model(item):
        ver, name = item
        score = 0
    # 排除非視覺/非多模態模型 (如 tts, embedding, audio, imagen 等)
    def is_vision_model(name: str) -> bool:
        low = name.lower()
        if any(bad in low for bad in ["-tts", "audio", "embed", "imagen", "search"]):
            return False
        return True

    available_models = [m for m in available_models if is_vision_model(m[1])]

    # 依優先順序排序: 穩定正式版 flash 優先
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
        # 若無法獲取列表，提供官方最通用的多模態模型
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
            # 只有在 API Key 本身無效 (403/API_KEY_INVALID) 才直接中止
            if "API_KEY_INVALID" in err_msg or "API key not valid" in err_msg:
                raise RuntimeError(f"API 金鑰無效：{err_msg}")
            # 其它錯誤 (包含 400 該模型不吃圖片、404 模型未開放等) 繼續嘗試下一個候選模型
            continue
        except Exception as e:
            last_err = str(e)
            continue

    raise RuntimeError(f"所有可用模型皆無法產生回應：\n{last_err}")

def parse_with_claude(api_key: str, file_path: Path) -> dict:
    """使用 Anthropic Claude API"""
    import urllib.request
    
    with open(file_path, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode("utf-8")

    is_pdf = file_path.suffix.lower() == ".pdf"
    suffix = file_path.suffix.lower()
    mime_type = "application/pdf" if is_pdf else f"image/{suffix.replace('.', '')}"
    if mime_type == "image/jpg":
        mime_type = "image/jpeg"

    content_block = {
        "type": "document" if is_pdf else "image",
        "source": {
            "type": "base64",
            "media_type": mime_type,
            "data": b64_data
        }
    }

    req_body = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 2500,
        "messages": [
            {
                "role": "user",
                "content": [content_block, {"type": "text", "text": PROMPT_TEXT}]
            }
        ]
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(req_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
    )

    with urllib.request.urlopen(req) as resp:
        res_data = json.loads(resp.read().decode("utf-8"))
        text = "".join([b.get("text", "") for b in res_data.get("content", [])])

    return clean_and_parse_json(text)

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

    # 同時在專案目錄儲存一份 menu.json (包含更新時間戳記，供網頁端比對與自動載入)
    import time
    project_dir = Path(__file__).parent
    out_json_path = project_dir / "menu.json"
    payload = {
        "updatedAt": int(time.time() * 1000),
        "menu": data
    }
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return len(rows), out_json_path

def try_git_push(repo_dir: Path):
    """嘗試執行 git add, commit, push 自動同步至 GitHub"""
    import subprocess
    try:
        # 檢查是否為 git repo
        check = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo_dir, capture_output=True, text=True)
        if check.returncode != 0:
            print("\nℹ️ 當前目錄尚未初始化 git 倉庫，略過自動推送到 GitHub。")
            return

        print("\n📦 正在自動同步至 GitHub...")
        subprocess.run(["git", "add", "menu.json"], cwd=repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", "chore: auto update menu.json from AI tool"], cwd=repo_dir, check=True)
        push_res = subprocess.run(["git", "push"], cwd=repo_dir, capture_output=True, text=True)
        
        if push_res.returncode == 0:
            print("✨ 成功推送到 GitHub！GitHub Pages 上的菜單已自動完成更新！")
        else:
            print(f"⚠️ git push 失敗 (請手動檢查遠端設定): {push_res.stderr.strip()}")
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

    gemini_key = os.environ.get("GEMINI_API_KEY")
    claude_key = os.environ.get("ANTHROPIC_API_KEY")

    if not gemini_key and not claude_key:
        print("\n⚠️ 找不到 API 金鑰環境變數。")
        print("請選擇你要使用的 API 並輸入金鑰：")
        print("1. Google Gemini API (推薦)")
        print("2. Anthropic Claude API")
        choice = input("請輸入選項 (1 或 2): ").strip()
        if choice == "2":
            claude_key = input("請輸入 ANTHROPIC_API_KEY: ").strip()
        else:
            gemini_key = input("請輸入 GEMINI_API_KEY: ").strip()

    print(f"\n🚀 正在解析檔案: {input_file.name} ...")

    try:
        if gemini_key:
            print("👉 使用 Google Gemini 進行視覺識別...")
            result = parse_with_gemini(gemini_key, input_file)
        elif claude_key:
            print("👉 使用 Claude 進行視覺識別...")
            result = parse_with_claude(claude_key, input_file)
        else:
            print("❌ 未提供任何 API 金鑰，終止。")
            return

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
