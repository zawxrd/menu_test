import os
import json
import urllib.request
import urllib.error

key = os.environ.get("GEMINI_API_KEY")
if not key:
    key = input("請輸入 GEMINI_API_KEY: ").strip()

print(f"使用的 API Key: {key[:6]}...{key[-4:]}")

for ver in ["v1beta", "v1"]:
    url = f"https://generativelanguage.googleapis.com/{ver}/models?key={key}"
    print(f"\n--- 檢查端點 {ver}/models ---")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            models = data.get("models", [])
            print(f"找到 {len(models)} 個可用模型：")
            for m in models:
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    print(f"  ✅ {m['name']} (支援 generateContent)")
    except urllib.error.HTTPError as e:
        print(f"  ❌ HTTP {e.code}: {e.read().decode()[:200]}")
    except Exception as e:
        print(f"  ❌ 錯誤: {e}")
