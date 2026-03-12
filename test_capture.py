"""
从浏览器捕获完整的 API 请求信息（method、headers、body）
"""
from playwright.sync_api import sync_playwright
import time
import json

TARGET_URL = "https://web.okjike.com/u/E04918BA-823C-4284-B2FA-7E00D0849023"
PROJECT_DIR = "/Users/xiaokang/my_project/jike-crawler"
BROWSER_DATA = f"{PROJECT_DIR}/browser_data"


def run():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA,
            headless=False,
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        api_requests = []

        def handle_request(request):
            if "api.ruguoapp.com" in request.url:
                info = {
                    "url": request.url,
                    "method": request.method,
                    "headers": dict(request.headers),
                }
                try:
                    info["post_data"] = request.post_data
                except:
                    info["post_data"] = None
                api_requests.append(info)

        page.on("request", handle_request)

        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        if "login" in page.url.lower():
            print("请登录后按回车...")
            input()
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

        time.sleep(5)

        # 保存所有 API 请求
        with open(f"{PROJECT_DIR}/api_requests.json", "w") as f:
            json.dump(api_requests, f, ensure_ascii=False, indent=2)

        print(f"捕获到 {len(api_requests)} 个 API 请求:")
        for req in api_requests:
            print(f"  {req['method']} {req['url'][:80]}")
            # 打印认证相关 headers
            for key in ['x-jike-access-token', 'authorization', 'cookie', 'x-jike-refresh-token']:
                if key in req['headers'] and req['headers'][key]:
                    val = req['headers'][key]
                    print(f"    {key}: {val[:50]}...")
            if req['post_data']:
                print(f"    body: {req['post_data'][:100]}")

        context.close()


if __name__ == "__main__":
    run()
