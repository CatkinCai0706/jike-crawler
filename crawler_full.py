"""
即刻爬虫（增强版）：
1. 采集全量动态（不限30条）
2. 采集每条动态的评论（含评论人ID、链接）
3. Token 自动刷新
4. 风控策略（请求间隔、失败重试、限流检测）
"""
import json
import time
import os
import requests
from playwright.sync_api import sync_playwright

PROJECT_DIR = "/Users/xiaokang/my_project/jike-crawler"
BROWSER_DATA = f"{PROJECT_DIR}/browser_data"
API_BASE = "https://api.ruguoapp.com/1.0"
TARGET_USERNAME = "E04918BA-823C-4284-B2FA-7E00D0849023"
OUTPUT_FILE = f"{PROJECT_DIR}/result_full.json"
TOKEN_FILE = f"{PROJECT_DIR}/token.txt"

# 配置项
CONFIG = {
    "posts_limit": None,  # None = 全量，数字 = 限制条数
    "fetch_comments": True,  # 是否采集评论
    "comments_limit": 50,  # 每条动态最多采集多少评论
    "request_interval": 0.5,  # 请求间隔（秒）
    "retry_times": 3,  # 失败重试次数
    "retry_delay": 2,  # 重试延迟（秒）
}


def get_token(force_refresh=False):
    """从浏览器获取 Token"""
    if not force_refresh and os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
        if token:
            # 验证有效性
            try:
                resp = requests.get(
                    f"{API_BASE}/users/profile",
                    headers={"x-jike-access-token": token},
                    timeout=10,
                )
                if resp.status_code == 200:
                    print("Token 有效")
                    return token
            except:
                pass
            print("Token 失效，重新获取...")

    print("从浏览器获取 Token...")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA,
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        cdp = context.new_cdp_session(page)
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})

        captured = {}

        def on_request(request):
            if "api.ruguoapp.com" in request.url:
                t = request.headers.get("x-jike-access-token", "")
                if t:
                    captured["token"] = t

        page.on("request", on_request)
        page.goto("https://web.okjike.com/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        if "login" in page.url.lower() or not captured.get("token"):
            page.goto(
                f"https://web.okjike.com/u/{TARGET_USERNAME}",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            time.sleep(3)

            if "login" in page.url.lower():
                print("\n请在浏览器中完成登录，登录后按回车...")
                input()
                page.goto(
                    f"https://web.okjike.com/u/{TARGET_USERNAME}",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                time.sleep(5)

        if not captured.get("token"):
            token_from_storage = page.evaluate("() => localStorage.getItem('JK_ACCESS_TOKEN')")
            if token_from_storage:
                captured["token"] = token_from_storage

        context.close()

    token = captured.get("token", "")
    if token:
        with open(TOKEN_FILE, "w") as f:
            f.write(token)
        print("Token 已保存")
    return token


class JikeAPI:
    def __init__(self, token):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://web.okjike.com/",
            "Origin": "https://web.okjike.com",
            "x-jike-access-token": token,
            "Content-Type": "application/json",
        })
        self.request_count = 0
        self.last_request_time = 0

    def _wait_interval(self):
        """控制请求频率"""
        elapsed = time.time() - self.last_request_time
        if elapsed < CONFIG["request_interval"]:
            time.sleep(CONFIG["request_interval"] - elapsed)
        self.last_request_time = time.time()

    def _request(self, method, url, **kwargs):
        """带重试和风控的请求"""
        self._wait_interval()
        self.request_count += 1

        for attempt in range(CONFIG["retry_times"]):
            try:
                if method == "GET":
                    resp = self.session.get(url, timeout=30, **kwargs)
                else:
                    resp = self.session.post(url, timeout=30, **kwargs)

                # 检测限流
                if resp.status_code == 429:
                    print(f"    触发限流，等待 {CONFIG['retry_delay'] * 2} 秒...")
                    time.sleep(CONFIG["retry_delay"] * 2)
                    continue

                # Token 过期
                if resp.status_code == 401:
                    print(f"    Token 过期，刷新中...")
                    new_token = get_token(force_refresh=True)
                    if new_token:
                        self.token = new_token
                        self.session.headers["x-jike-access-token"] = new_token
                        continue
                    else:
                        return None

                return resp

            except Exception as e:
                print(f"    请求失败 (尝试 {attempt + 1}/{CONFIG['retry_times']}): {e}")
                if attempt < CONFIG["retry_times"] - 1:
                    time.sleep(CONFIG["retry_delay"])

        return None

    def get_following_list(self, username):
        """获取关注列表"""
        all_users = []
        load_more_key = None

        while True:
            body = {"username": username, "limit": 20}
            if load_more_key:
                body["loadMoreKey"] = load_more_key

            resp = self._request("POST", f"{API_BASE}/userRelation/getFollowingList", json=body)
            if not resp or resp.status_code != 200:
                break

            result = resp.json()
            users = result.get("data", [])
            all_users.extend(users)
            load_more_key = result.get("loadMoreKey")

            if not load_more_key or not users:
                break

        return all_users

    def get_user_profile(self, username):
        """获取用户详情"""
        resp = self._request("GET", f"{API_BASE}/users/profile", params={"username": username})
        if resp and resp.status_code == 200:
            return resp.json().get("user", {})
        return None

    def get_user_posts(self, username, limit=None):
        """获取用户动态（全量或限制条数）"""
        all_posts = []
        load_more_key = None

        while True:
            if limit and len(all_posts) >= limit:
                break

            body = {"username": username, "limit": 20}
            if load_more_key:
                body["loadMoreKey"] = load_more_key

            resp = self._request("POST", f"{API_BASE}/personalUpdate/single", json=body)
            if not resp or resp.status_code != 200:
                break

            result = resp.json()
            posts = result.get("data", [])
            all_posts.extend(posts)
            load_more_key = result.get("loadMoreKey")

            if not load_more_key or not posts:
                break

        return all_posts[:limit] if limit else all_posts

    def get_post_comments(self, post_id, post_type="ORIGINAL_POST", limit=None):
        """获取动态评论"""
        all_comments = []
        load_more_key = None

        while True:
            if limit and len(all_comments) >= limit:
                break

            body = {"targetId": post_id, "targetType": post_type, "limit": 20}
            if load_more_key:
                body["loadMoreKey"] = load_more_key

            resp = self._request("POST", f"{API_BASE}/comments/listPrimary", json=body)
            if not resp or resp.status_code != 200:
                break

            result = resp.json()
            comments = result.get("data", [])
            all_comments.extend(comments)
            load_more_key = result.get("loadMoreKey")

            if not load_more_key or not comments:
                break

        return all_comments[:limit] if limit else all_comments


def extract_profile_info(profile):
    """提取用户信息"""
    stats = profile.get("statsCount", {})
    return {
        "id": profile.get("username", ""),
        "screenName": profile.get("screenName", ""),
        "briefIntro": profile.get("briefIntro", ""),
        "bio": profile.get("bio", ""),
        "gender": profile.get("gender", ""),
        "followingCount": stats.get("followingCount", 0),
        "followedCount": stats.get("followedCount", 0),
        "respectedCount": stats.get("respectedCount", 0),
        "isSponsor": profile.get("isSponsor", False),
    }


def extract_post_info(post):
    """提取动态信息"""
    return {
        "id": post.get("id", ""),
        "type": post.get("type", ""),
        "content": post.get("content", ""),
        "createdAt": post.get("createdAt", ""),
        "likeCount": post.get("likeCount", 0),
        "commentCount": post.get("commentCount", 0),
        "shareCount": post.get("shareCount", 0),
    }


def extract_comment_info(comment):
    """提取评论信息"""
    user = comment.get("user", {})
    return {
        "id": comment.get("id", ""),
        "content": comment.get("content", ""),
        "createdAt": comment.get("createdAt", ""),
        "likeCount": comment.get("likeCount", 0),
        "replyCount": comment.get("replyCount", 0),
        "user": {
            "id": user.get("username", ""),
            "screenName": user.get("screenName", ""),
            "link": f"https://web.okjike.com/u/{user.get('username', '')}",
        },
    }


def load_progress():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE) as f:
            return json.load(f)
    return {}


def save_progress(data):
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print("=== 即刻爬虫（增强版）===")
    print(f"配置: 动态限制={CONFIG['posts_limit'] or '全量'}, 评论={CONFIG['fetch_comments']}, 评论限制={CONFIG['comments_limit']}")
    print(f"风控: 请求间隔={CONFIG['request_interval']}s, 重试={CONFIG['retry_times']}次\n")

    token = get_token()
    if not token:
        print("未获取到 Token，退出")
        return

    api = JikeAPI(token)
    result = load_progress()
    done_ids = set(result.keys())

    # 获取关注列表
    print(f"获取 {TARGET_USERNAME} 的关注列表...")
    following = api.get_following_list(TARGET_USERNAME)
    print(f"共 {len(following)} 人\n")

    # 逐个采集
    for i, user in enumerate(following):
        uid = user.get("username", "")
        name = user.get("screenName", "")

        if uid in done_ids:
            print(f"[{i+1}/{len(following)}] {name} - 已采集，跳过")
            continue

        print(f"[{i+1}/{len(following)}] {name} ({uid})")

        # 获取详情
        profile = api.get_user_profile(uid)
        if profile:
            info = extract_profile_info(profile)
        else:
            info = {
                "id": uid,
                "screenName": name,
                "briefIntro": user.get("briefIntro", ""),
                "bio": user.get("bio", ""),
                "followingCount": 0,
                "followedCount": 0,
            }
            print(f"  profile 获取失败")

        print(f"  关注 {info['followingCount']}, 被关注 {info['followedCount']}")

        # 获取动态
        posts = api.get_user_posts(uid, limit=CONFIG["posts_limit"])
        info["posts"] = []
        print(f"  动态 {len(posts)} 条")

        # 处理每条动态
        for j, post in enumerate(posts):
            post_info = extract_post_info(post)

            # 获取评论
            if CONFIG["fetch_comments"] and post_info["commentCount"] > 0:
                comments = api.get_post_comments(
                    post_info["id"],
                    post_type=post_info["type"],
                    limit=CONFIG["comments_limit"],
                )
                post_info["comments"] = [extract_comment_info(c) for c in comments]
                if (j + 1) % 10 == 0:
                    print(f"    已处理 {j+1}/{len(posts)} 条动态")
            else:
                post_info["comments"] = []

            info["posts"].append(post_info)

        # 保存
        result[uid] = info
        save_progress(result)

        print(f"  已保存，累计请求 {api.request_count} 次")

    print(f"\n采集完成，共 {len(result)} 人，已保存: {OUTPUT_FILE}")
    print(f"总请求数: {api.request_count}")


if __name__ == "__main__":
    main()
