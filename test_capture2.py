"""
强制触发 API 请求：禁用缓存 + 拦截请求获取 Token
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

        # 禁用缓存
        page.route("**/*", lambda route: route.continue_())

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

        # 通过 CDP 禁用缓存
        cdp = context.new_cdp_session(page)
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})

        # 先去一个别的页面再回来，确保触发新请求
        page.goto("https://web.okjike.com/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(2)

        # 清空已捕获的
        api_requests.clear()

        # 现在访问目标页面
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)

        if "login" in page.url.lower():
            print("请登录后按回车...")
            input()
            api_requests.clear()
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

        print(f"捕获到 {len(api_requests)} 个 API 请求:")
        for req in api_requests:
            print(f"\n  {req['method']} {req['url']}")
            auth_keys = ['x-jike-access-token', 'authorization', 'cookie', 'x-jike-refresh-token']
            for key in auth_keys:
                val = req['headers'].get(key, '')
                if val:
                    print(f"    {key}: {val[:80]}...")
            if req['post_data']:
                print(f"    body: {req['post_data'][:200]}")

        # 保存
        with open(f"{PROJECT_DIR}/api_requests.json", "w") as f:
            json.dump(api_requests, f, ensure_ascii=False, indent=2)
        print(f"\n已保存: api_requests.json")

        # 额外：从 localStorage / cookie 里找 token
        print("\n=== 检查 localStorage ===")
        storage = page.evaluate("""() => {
            const result = {};
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key.toLowerCase().includes('token') || key.toLowerCase().includes('auth') || key.toLowerCase().includes('jike')) {
                    result[key] = localStorage.getItem(key).substring(0, 100);
                }
            }
            return result;
        }""")
        for k, v in storage.items():
            print(f"  {k}: {v}")

        print("\n=== 检查 Cookies ===")
        cookies = context.cookies()
        for c in cookies:
            if 'token' in c['name'].lower() or 'auth' in c['name'].lower() or 'jike' in c['name'].lower() or 'ruguoapp' in c['domain']:
                print(f"  {c['name']}: {str(c['value'])[:80]}... (domain: {c['domain']})")

        time.sleep(3)
        context.close()


if __name__ == "__main__":
    run()
