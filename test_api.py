"""
测试 API 方案：
1. 从浏览器获取认证 Token
2. 调 getFollowingList 拿完整关注列表
3. 调 profile 拿用户详情
"""
from playwright.sync_api import sync_playwright
import requests
import time
import json

TARGET_URL = "https://web.okjike.com/u/E04918BA-823C-4284-B2FA-7E00D0849023"
TARGET_USERNAME = "E04918BA-823C-4284-B2FA-7E00D0849023"
API_BASE = "https://api.ruguoapp.com/1.0"
PROJECT_DIR = "/Users/xiaokang/my_project/jike-crawler"
BROWSER_DATA = f"{PROJECT_DIR}/browser_data"


def get_token_from_browser():
    """从浏览器获取认证 Token"""
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA,
            headless=False,
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        # 捕获 API 请求的 headers
        auth_headers = {}

        def handle_request(request):
            if "api.ruguoapp.com" in request.url:
                headers = request.headers
                for key in ['x-jike-access-token', 'authorization', 'cookie']:
                    if key in headers and headers[key]:
                        auth_headers[key] = headers[key]

        page.on("request", handle_request)

        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

        # 检查登录
        time.sleep(3)
        if "login" in page.url.lower():
            print("请登录后按回车...")
            input()
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
        else:
            time.sleep(3)

        print(f"捕获到的认证信息: {list(auth_headers.keys())}")

        # 保存 token
        with open(f"{PROJECT_DIR}/auth_token.json", "w") as f:
            json.dump(auth_headers, f, indent=2)

        context.close()
        return auth_headers


def test_api(auth_headers):
    """测试 API 调用"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://web.okjike.com/",
        "Origin": "https://web.okjike.com",
    }
    # 加入认证信息
    if "x-jike-access-token" in auth_headers:
        headers["x-jike-access-token"] = auth_headers["x-jike-access-token"]
    if "authorization" in auth_headers:
        headers["Authorization"] = auth_headers["authorization"]

    session = requests.Session()
    session.headers.update(headers)
    if "cookie" in auth_headers:
        session.headers["Cookie"] = auth_headers["cookie"]

    # 测试1：获取用户 profile
    print("\n=== 测试1：获取用户 profile ===")
    resp = session.get(f"{API_BASE}/users/profile", params={"username": TARGET_USERNAME})
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json().get("data", {})
        print(f"  用户名: {data.get('screenName')}")
        print(f"  简介: {data.get('briefIntro')}")
        print(f"  关注: {data.get('following')}")
        print(f"  被关注: {data.get('follower')}")
    else:
        print(f"  响应: {resp.text[:300]}")

    # 测试2：获取关注列表（第一页）
    print("\n=== 测试2：获取关注列表 ===")
    all_users = []
    load_more_key = None

    while True:
        params = {"username": TARGET_USERNAME}
        if load_more_key:
            params["loadMoreKey"] = load_more_key

        resp = session.get(f"{API_BASE}/userRelation/getFollowingList", params=params)
        print(f"  状态码: {resp.status_code}")

        if resp.status_code != 200:
            print(f"  失败: {resp.text[:300]}")
            break

        result = resp.json()
        users = result.get("data", [])
        all_users.extend(users)
        load_more_key = result.get("loadMoreKey")

        print(f"  本页: {len(users)} 人, 累计: {len(all_users)} 人, loadMoreKey: {load_more_key}")

        if not load_more_key or not users:
            break

        time.sleep(1)  # 避免频率限制

    print(f"\n  总计获取: {len(all_users)} 人")

    # 保存
    with open(f"{PROJECT_DIR}/following_list.json", "w") as f:
        json.dump(all_users, f, ensure_ascii=False, indent=2)
    print(f"  已保存: following_list.json")

    # 打印前5个
    for u in all_users[:5]:
        print(f"    - {u.get('screenName')}: {u.get('username')}, {u.get('briefIntro', '')[:40]}")

    # 测试3：获取某个用户的动态
    if all_users:
        print("\n=== 测试3：获取用户动态 ===")
        test_user = all_users[0]
        print(f"  测试用户: {test_user.get('screenName')} ({test_user.get('username')})")

        # 尝试 userPost/listPost
        resp = session.get(f"{API_BASE}/userPost/listPost", params={"username": test_user["username"], "limit": 5})
        print(f"  listPost 状态码: {resp.status_code}")
        if resp.status_code == 200:
            posts = resp.json().get("data", [])
            print(f"  获取到 {len(posts)} 条动态")
            for post in posts[:3]:
                content = post.get("content", "")[:60]
                print(f"    - {content}")
        else:
            print(f"  响应: {resp.text[:300]}")

            # 备选接口
            resp2 = session.get(f"{API_BASE}/userProfile/listPost", params={"username": test_user["username"], "limit": 5})
            print(f"  userProfile/listPost 状态码: {resp2.status_code}")
            if resp2.status_code == 200:
                posts = resp2.json().get("data", [])
                print(f"  获取到 {len(posts)} 条动态")


def main():
    # 先尝试读取已保存的 token
    try:
        with open(f"{PROJECT_DIR}/auth_token.json") as f:
            auth_headers = json.load(f)
        if auth_headers:
            print("使用已保存的 Token 测试...")
            test_api(auth_headers)
            return
    except FileNotFoundError:
        pass

    print("从浏览器获取 Token...")
    auth_headers = get_token_from_browser()
    if auth_headers:
        test_api(auth_headers)
    else:
        print("未获取到认证信息")


if __name__ == "__main__":
    main()
