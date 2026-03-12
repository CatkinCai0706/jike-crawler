"""
测试 API：用 Token 调用即刻 API
1. 获取关注列表（POST）
2. 获取用户详情
3. 获取用户动态
"""
import requests
import time
import json

PROJECT_DIR = "/Users/xiaokang/my_project/jike-crawler"
API_BASE = "https://api.ruguoapp.com/1.0"
TARGET_USERNAME = "E04918BA-823C-4284-B2FA-7E00D0849023"

# 读取 token
with open(f"{PROJECT_DIR}/token.txt") as f:
    TOKEN = f.read().strip()

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://web.okjike.com/",
    "Origin": "https://web.okjike.com",
    "x-jike-access-token": TOKEN,
    "Content-Type": "application/json",
})

# === 测试1：获取用户 profile ===
print("=== 测试1：获取用户 profile ===")
resp = session.get(f"{API_BASE}/users/profile", params={"username": TARGET_USERNAME})
print(f"GET profile 状态码: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json().get("data", {})
    print(f"  用户名: {data.get('screenName')}")
    print(f"  简介: {data.get('briefIntro')}")
    print(f"  关注: {data.get('following')}")
    print(f"  被关注: {data.get('follower')}")
    print(f"  bio: {data.get('bio')}")

# === 测试2：获取关注列表（POST） ===
print("\n=== 测试2：获取关注列表（POST） ===")
all_users = []
load_more_key = None
page_num = 0

while True:
    page_num += 1
    body = {"username": TARGET_USERNAME}
    if load_more_key:
        body["loadMoreKey"] = load_more_key

    resp = session.post(f"{API_BASE}/userRelation/getFollowingList", json=body)
    print(f"  第 {page_num} 页, 状态码: {resp.status_code}")

    if resp.status_code != 200:
        # 也试试 GET
        resp2 = session.get(f"{API_BASE}/userRelation/getFollowingList", params=body)
        print(f"  GET 备选, 状态码: {resp2.status_code}")
        if resp2.status_code == 200:
            resp = resp2
        else:
            print(f"  失败: {resp.text[:300]}")
            break

    result = resp.json()
    users = result.get("data", [])
    all_users.extend(users)
    load_more_key = result.get("loadMoreKey")

    print(f"  本页: {len(users)} 人, 累计: {len(all_users)} 人")

    if not load_more_key or not users:
        print("  没有更多了")
        break

    time.sleep(1)

print(f"\n总计: {len(all_users)} 人")
with open(f"{PROJECT_DIR}/following_list.json", "w") as f:
    json.dump(all_users, f, ensure_ascii=False, indent=2)
print(f"已保存: following_list.json")

for u in all_users[:5]:
    print(f"  - {u.get('screenName')}: {u.get('briefIntro', '')[:40]}")

# === 测试3：获取某用户动态 ===
if all_users:
    print(f"\n=== 测试3：获取用户动态 ===")
    test_user = all_users[0]
    print(f"测试用户: {test_user.get('screenName')} ({test_user.get('username')})")

    # 尝试 POST
    resp = session.post(f"{API_BASE}/userPost/listPost", json={"username": test_user["username"], "limit": 5})
    print(f"  POST listPost: {resp.status_code}")
    if resp.status_code == 200:
        posts = resp.json().get("data", [])
        print(f"  获取到 {len(posts)} 条动态")
        for post in posts[:3]:
            content = post.get("content", "")[:80]
            created = post.get("createdAt", "")[:10]
            print(f"    [{created}] {content}")
    else:
        print(f"  响应: {resp.text[:200]}")

        # 备选
        resp2 = session.post(f"{API_BASE}/userProfile/listPost", json={"username": test_user["username"], "limit": 5})
        print(f"  POST userProfile/listPost: {resp2.status_code}")
        if resp2.status_code == 200:
            posts = resp2.json().get("data", [])
            print(f"  获取到 {len(posts)} 条动态")
            for post in posts[:3]:
                content = post.get("content", "")[:80]
                print(f"    {content}")
        else:
            print(f"  响应: {resp2.text[:200]}")
