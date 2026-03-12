"""
打开一个关注用户的主页，抓取浏览器发出的所有 API 请求
"""
from playwright.sync_api import sync_playwright
import time
import json

PROJECT_DIR = "/Users/xiaokang/my_project/jike-crawler"
BROWSER_DATA = f"{PROJECT_DIR}/browser_data"

# 用关注列表里第一个用户测试
with open(f"{PROJECT_DIR}/following_list.json") as f:
    users = json.load(f)
test_user = users[0]
TEST_URL = f"https://web.okjike.com/u/{test_user['username']}"
print(f"测试用户: {test_user['screenName']} -> {TEST_URL}")


def run():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA,
            headless=False,
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        # 禁用缓存
        cdp = context.new_cdp_session(page)
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})

        api_requests = []

        def handle_request(request):
            if "api.ruguoapp.com" in request.url:
                info = {
                    "url": request.url,
                    "method": request.method,
                }
                try:
                    info["post_data"] = request.post_data
                except:
                    info["post_data"] = None
                api_requests.append(info)

        api_responses = []

        def handle_response(response):
            if "api.ruguoapp.com" in response.url:
                info = {"url": response.url, "status": response.status}
                try:
                    info["data_keys"] = list(response.json().keys()) if response.status == 200 else None
                    body = response.json()
                    data = body.get("data")
                    if isinstance(data, list):
                        info["data_len"] = len(data)
                        if data:
                            info["first_item_keys"] = list(data[0].keys())[:15]
                    elif isinstance(data, dict):
                        info["data_keys_inner"] = list(data.keys())[:20]
                except:
                    pass
                api_responses.append(info)

        page.on("request", handle_request)
        page.on("response", handle_response)

        page.goto(TEST_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)

        # 滚动一下触发动态加载
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(2)
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(2)

        print(f"\n捕获到 {len(api_requests)} 个请求:")
        for req in api_requests:
            body = req.get('post_data', '')
            print(f"  {req['method']} {req['url']}")
            if body:
                print(f"    body: {body[:200]}")

        print(f"\n捕获到 {len(api_responses)} 个响应:")
        for resp in api_responses:
            print(f"  {resp['status']} {resp['url']}")
            if resp.get('data_len') is not None:
                print(f"    data: {resp['data_len']} 条, keys: {resp.get('first_item_keys')}")
            if resp.get('data_keys_inner'):
                print(f"    data keys: {resp['data_keys_inner']}")

        with open(f"{PROJECT_DIR}/user_page_requests.json", "w") as f:
            json.dump({"requests": api_requests, "responses": api_responses}, f, ensure_ascii=False, indent=2)

        time.sleep(3)
        context.close()


if __name__ == "__main__":
    run()
