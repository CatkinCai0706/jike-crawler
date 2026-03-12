"""
验证评论接口：打开一条动态，抓取浏览器发出的评论相关 API
"""
from playwright.sync_api import sync_playwright
import time
import json

PROJECT_DIR = "/Users/xiaokang/my_project/jike-crawler"
BROWSER_DATA = f"{PROJECT_DIR}/browser_data"

# 从已有数据里找一条有评论的动态
with open(f"{PROJECT_DIR}/result.json") as f:
    result = json.load(f)

# 找一条评论数 > 0 的动态
test_post = None
test_user = None
for uid, info in result.items():
    for post in info.get("posts", []):
        if post.get("commentCount", 0) > 3:
            test_post = post
            test_user = info
            break
    if test_post:
        break

print(f"测试用户: {test_user['screenName']}")
print(f"测试动态: {test_post['content'][:60]}")
print(f"评论数: {test_post['commentCount']}, ID: {test_post['id']}")


def run():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA,
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

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

        page.on("request", handle_request)

        # 打开动态详情页
        post_url = f"https://web.okjike.com/post/{test_post['id']}"
        print(f"\n打开: {post_url}")
        page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)

        # 滚动一下加载评论
        page.evaluate("window.scrollBy(0, 500)")
        time.sleep(2)

        print(f"\n捕获到 {len(api_requests)} 个请求:")
        for req in api_requests:
            print(f"  {req['method']} {req['url']}")
            if req['post_data']:
                print(f"    body: {req['post_data'][:200]}")

        with open(f"{PROJECT_DIR}/comment_requests.json", "w") as f:
            json.dump(api_requests, f, ensure_ascii=False, indent=2)

        time.sleep(3)
        context.close()


if __name__ == "__main__":
    run()
