"""
即刻爬虫（正式版）
- 采集指定用户关注列表中所有人的详细信息、动态、评论
- 支持断点续爬、Token 自动刷新、风控策略
- 支持后台运行
"""
import json
import time
import os
import random
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

PROJECT_DIR = "/Users/xiaokang/my_project/jike-crawler"
BROWSER_DATA = f"{PROJECT_DIR}/browser_data"
API_BASE = "https://api.ruguoapp.com/1.0"
TARGET_USERNAME = "E04918BA-823C-4284-B2FA-7E00D0849023"
OUTPUT_FILE = f"{PROJECT_DIR}/result_full.json"
TOKEN_FILE = f"{PROJECT_DIR}/token.txt"
LOG_FILE = f"{PROJECT_DIR}/crawler.log"

# === 配置 ===
POSTS_LIMIT = 40          # 每人动态条数
COMMENTS_LIMIT = 100      # 每条动态评论条数
REQUEST_INTERVAL = (1, 4)  # 请求间隔（秒），随机范围
BATCH_SIZE = (30, 50)      # 每多少次请求触发休息
BATCH_REST = (10, 40)      # 批次休息时间（秒），随机范围
USER_REST = (5, 20)        # 每个用户采完休息时间（秒），随机范围
RETRY_TIMES = 3            # 失败重试次数
RETRY_DELAY = 5            # 重试基础延迟（秒）


def log(msg):
    """同时输出到终端和日志文件"""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_token(force_refresh=False):
    """获取 Token，优先用已有的，失效则从浏览器刷新"""
    if not force_refresh and os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
        if token:
            try:
                resp = requests.get(
                    f"{API_BASE}/users/profile",
                    headers={"x-jike-access-token": token},
                    timeout=10,
                )
                if resp.status_code == 200:
                    log("Token 有效")
                    return token
            except:
                pass
            log("Token 失效，重新获取...")

    log("从浏览器获取 Token...")
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

        if "login" in page.url.lower():
            log("检测到需要登录，请先运行 get_token.py 登录")
            context.close()
            return ""

        # 首页可能不触发 API 请求，访问一个用户页面确保捕获 Token
        if not captured.get("token"):
            page.goto(f"https://web.okjike.com/u/{TARGET_USERNAME}", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

        if not captured.get("token"):
            token_from_storage = page.evaluate("() => localStorage.getItem('JK_ACCESS_TOKEN')")
            if token_from_storage:
                captured["token"] = token_from_storage

        if not captured.get("token"):
            log("未能捕获 Token，请检查登录状态")

        context.close()

    token = captured.get("token", "")
    if token:
        with open(TOKEN_FILE, "w") as f:
            f.write(token)
        log("Token 已保存")
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
        self.batch_count = 0
        self.next_batch_threshold = random.randint(*BATCH_SIZE)

    def _throttle(self):
        """风控：请求间隔 + 批次休息"""
        # 随机请求间隔
        time.sleep(random.uniform(*REQUEST_INTERVAL))

        # 批次休息
        self.batch_count += 1
        if self.batch_count >= self.next_batch_threshold:
            rest = random.uniform(*BATCH_REST)
            log(f"    风控休息 {rest:.0f}s（已请求 {self.request_count} 次）")
            time.sleep(rest)
            self.batch_count = 0
            self.next_batch_threshold = random.randint(*BATCH_SIZE)

    def _request(self, method, url, **kwargs):
        """带风控、重试、Token 刷新的请求"""
        self._throttle()
        self.request_count += 1

        for attempt in range(RETRY_TIMES):
            try:
                if method == "GET":
                    resp = self.session.get(url, timeout=30, **kwargs)
                else:
                    resp = self.session.post(url, timeout=30, **kwargs)

                if resp.status_code == 429:
                    wait = RETRY_DELAY * (attempt + 2)
                    log(f"    限流 429，等待 {wait}s...")
                    time.sleep(wait)
                    continue

                if resp.status_code == 401:
                    log("    Token 过期，刷新...")
                    new_token = get_token(force_refresh=True)
                    if new_token:
                        self.token = new_token
                        self.session.headers["x-jike-access-token"] = new_token
                        continue
                    return None

                return resp

            except Exception as e:
                if attempt < RETRY_TIMES - 1:
                    wait = RETRY_DELAY * (attempt + 1)
                    log(f"    请求异常: {e}，{wait}s 后重试")
                    time.sleep(wait)
                else:
                    log(f"    请求失败: {e}")

        return None

    def get_following_list(self, username):
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
        resp = self._request("GET", f"{API_BASE}/users/profile", params={"username": username})
        if resp and resp.status_code == 200:
            return resp.json().get("user", {})
        return None

    def get_user_posts(self, username, limit=POSTS_LIMIT):
        all_posts = []
        load_more_key = None
        while len(all_posts) < limit:
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
        return all_posts[:limit]

    def get_post_comments(self, post_id, post_type="ORIGINAL_POST", limit=COMMENTS_LIMIT):
        all_comments = []
        load_more_key = None
        while len(all_comments) < limit:
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
        return all_comments[:limit]


def extract_profile(profile):
    stats = profile.get("statsCount", {})
    return {
        "id": profile.get("username", ""),
        "screenName": profile.get("screenName", ""),
        "briefIntro": profile.get("briefIntro", ""),
        "bio": profile.get("bio", ""),
        "gender": profile.get("gender", ""),
        "link": f"https://web.okjike.com/u/{profile.get('username', '')}",
        "followingCount": stats.get("followingCount", 0),
        "followedCount": stats.get("followedCount", 0),
        "respectedCount": stats.get("respectedCount", 0),
        "isSponsor": profile.get("isSponsor", False),
    }


def extract_post(post):
    return {
        "id": post.get("id", ""),
        "type": post.get("type", ""),
        "content": post.get("content", ""),
        "createdAt": post.get("createdAt", ""),
        "likeCount": post.get("likeCount", 0),
        "commentCount": post.get("commentCount", 0),
        "shareCount": post.get("shareCount", 0),
    }


def extract_comment(comment):
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
    log("=== 即刻爬虫启动 ===")
    log(f"动态 {POSTS_LIMIT} 条/人, 评论 {COMMENTS_LIMIT} 条/动态")
    log(f"请求间隔 {REQUEST_INTERVAL[0]}-{REQUEST_INTERVAL[1]}s, 批次休息 {BATCH_REST[0]}-{BATCH_REST[1]}s")

    token = get_token()
    if not token:
        log("未获取到 Token，退出")
        return

    api = JikeAPI(token)
    result = load_progress()
    done_ids = set(result.keys())

    log(f"获取关注列表...")
    following = api.get_following_list(TARGET_USERNAME)
    log(f"共 {len(following)} 人, 已采集 {len(done_ids)} 人\n")

    for i, user in enumerate(following):
        uid = user.get("username", "")
        name = user.get("screenName", "")

        if uid in done_ids:
            log(f"[{i+1}/{len(following)}] {name} - 跳过")
            continue

        log(f"[{i+1}/{len(following)}] {name}")

        # profile
        profile = api.get_user_profile(uid)
        if profile:
            info = extract_profile(profile)
        else:
            info = {
                "id": uid, "screenName": name,
                "briefIntro": user.get("briefIntro", ""),
                "bio": user.get("bio", ""),
                "link": f"https://web.okjike.com/u/{uid}",
                "followingCount": 0, "followedCount": 0,
            }
        log(f"  关注 {info.get('followingCount', 0)}, 被关注 {info.get('followedCount', 0)}")

        # 动态
        posts = api.get_user_posts(uid, limit=POSTS_LIMIT)
        info["posts"] = []
        comment_total = 0

        for j, post in enumerate(posts):
            post_info = extract_post(post)

            # 评论
            if post_info["commentCount"] > 0:
                comments = api.get_post_comments(
                    post_info["id"],
                    post_type=post_info["type"],
                    limit=COMMENTS_LIMIT,
                )
                post_info["comments"] = [extract_comment(c) for c in comments]
                comment_total += len(post_info["comments"])
            else:
                post_info["comments"] = []

            info["posts"].append(post_info)

        log(f"  动态 {len(info['posts'])} 条, 评论 {comment_total} 条, 累计请求 {api.request_count}")

        result[uid] = info
        save_progress(result)

        # 用户间休息
        rest = random.uniform(*USER_REST)
        log(f"  休息 {rest:.0f}s")
        time.sleep(rest)

    log(f"\n=== 采集完成 ===")
    log(f"共 {len(result)} 人, 总请求 {api.request_count} 次")
    log(f"数据文件: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
