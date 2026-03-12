#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright

PROJECT_DIR = Path(__file__).resolve().parent
RUNS_DIR = PROJECT_DIR / "runs"
BROWSER_DATA = PROJECT_DIR / "browser_data"
TOKEN_FILE = PROJECT_DIR / "token.txt"
STATE_DIR = PROJECT_DIR / "state"
REGISTRY_FILE = STATE_DIR / "user_registry.json"
RELATION_CACHE_DIR = STATE_DIR / "relations"
DETAIL_CACHE_DIR = STATE_DIR / "details"
API_BASE = "https://api.ruguoapp.com/1.0"
LOGIN_HINT_USERNAME = "E04918BA-823C-4284-B2FA-7E00D0849023"
PAGE_SIZE = 20
REPORT_LIMIT = 50
LOW_ACTIVITY_FOLLOWED_THRESHOLD = 10
LOW_ACTIVITY_POST_SCAN_LIMIT = 3
FILTER_TAG_ROLE = "ROLE_KEYWORD_FILTERED"
FILTER_TAG_LOW_ACTIVITY = "LOW_ACTIVITY_FILTERED"

FILTER_ROLE_KEYWORDS = (
    "产品经理",
    "投资人",
    "记者",
    "自媒体",
    "投资经理",
    "天使投资",
    "基金",
    "vc",
)

AI_KEYWORDS = (
    "ai",
    "aigc",
    "llm",
    "mcp",
    "rag",
    "agent",
    "agents",
    "transformer",
    "diffusion",
    "embedding",
    "prompt",
    "prompts",
    "inference",
    "fine-tuning",
    "fine tuning",
    "eval",
    "benchmark",
    "anthropic",
    "openai",
    "claude",
    "gpt",
    "deepseek",
    "qwen",
    "kimi",
    "gemini",
    "cursor",
    "copilot",
    "claude code",
    "智能体",
    "大模型",
    "模型",
    "推理",
    "训练",
    "微调",
    "蒸馏",
    "多模态",
    "向量",
    "提示词",
    "生成式",
    "代码生成",
    "模型评测",
    "上下文工程",
    "推理加速",
)

TECH_KEYWORDS = (
    "python",
    "golang",
    "go ",
    "rust",
    "typescript",
    "javascript",
    "java",
    "kotlin",
    "swift",
    "c++",
    "cuda",
    "pytorch",
    "tensorflow",
    "docker",
    "k8s",
    "kubernetes",
    "postgres",
    "mysql",
    "redis",
    "api",
    "sdk",
    "infra",
    "backend",
    "frontend",
    "fullstack",
    "open source",
    "github",
    "repo",
    "架构",
    "后端",
    "前端",
    "开发",
    "工程",
    "工程化",
    "部署",
    "数据库",
    "算法",
    "开源",
    "代码",
    "编程",
    "服务端",
    "芯片",
    "算力",
    "编译器",
    "系统设计",
    "工程师",
    "研发",
)

ROLE_KEYWORDS = (
    "cto",
    "founding engineer",
    "software engineer",
    "ml engineer",
    "ai engineer",
    "research engineer",
    "research scientist",
    "architect",
    "staff engineer",
    "tech lead",
    "工程师",
    "研发",
    "算法",
    "研究员",
    "架构师",
    "技术负责人",
    "技术合伙人",
    "程序员",
    "开发者",
)

NEGATIVE_KEYWORDS = (
    "投资人",
    "投资机构",
    "基金",
    "vc",
    "招聘",
    "猎头",
    "市场",
    "营销",
    "销售",
    "品牌",
    "运营",
    "课程",
    "训练营",
    "顾问",
    "咨询",
    "podcast",
    "播客",
)

DISCUSSION_QUALITY_KEYWORDS = (
    "原理",
    "实现",
    "架构",
    "训练",
    "推理",
    "优化",
    "benchmark",
    "eval",
    "latency",
    "throughput",
    "agent",
    "rag",
    "mcp",
    "cuda",
    "pytorch",
    "tensorflow",
    "python",
    "golang",
    "rust",
    "代码",
    "工程",
    "部署",
    "系统",
    "模型",
)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def load_registry() -> dict[str, Any]:
    return load_json(REGISTRY_FILE, {})


def save_registry(registry: dict[str, Any]) -> None:
    save_json(REGISTRY_FILE, registry)


def cache_path(cache_dir: Path, user_id: str) -> Path:
    safe_user_id = re.sub(r"[^0-9A-Za-z._-]", "_", user_id)
    return cache_dir / f"{safe_user_id}.json"


def load_cached_record(cache_dir: Path, user_id: str) -> dict[str, Any] | None:
    path = cache_path(cache_dir, user_id)
    if not path.exists():
        return None
    return load_json(path, {})


def save_cached_record(cache_dir: Path, user_id: str, data: dict[str, Any]) -> None:
    save_json(cache_path(cache_dir, user_id), data)


def log(message: str, log_file: Path | None = None) -> None:
    line = f"[{now_text()}] {message}"
    print(line, flush=True)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def truncate_text(text: str, limit: int = 96) -> str:
    compact = re.sub(r"\s+", " ", (text or "")).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def unique_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def blank_text(value: Any) -> bool:
    return not normalize_text("" if value is None else str(value))


def keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    haystack = normalize_text(text)
    return [keyword for keyword in keywords if keyword in haystack]


def parse_seed_username(raw: str) -> str | None:
    value = raw.strip()
    if not value or value.startswith("#"):
        return None
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        match = re.search(r"/u/([^/?#]+)", parsed.path)
        if match:
            return match.group(1)
    if re.fullmatch(r"[0-9A-Za-z-]{8,}", value):
        return value
    return None


def load_seed_usernames(seed_file: Path) -> list[str]:
    usernames: list[str] = []
    for line in seed_file.read_text(encoding="utf-8").splitlines():
        username = parse_seed_username(line)
        if username:
            usernames.append(username)
    deduped = unique_preserve(usernames)
    if not deduped:
        raise ValueError(f"seed file has no valid Jike user links: {seed_file}")
    return deduped


def make_run_dir(run_name: str | None) -> Path:
    run_id = run_name or datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def registry_entry(registry: dict[str, Any], user_id: str) -> dict[str, Any]:
    current = registry.get(user_id)
    if current is None:
        current = {
            "id": user_id,
            "tags": [],
            "filterReasons": [],
            "skipDeepCrawl": False,
            "relationCaptured": False,
            "detailCaptured": False,
            "firstSeenAt": now_text(),
            "lastSeenAt": now_text(),
        }
        registry[user_id] = current
    return current


def update_registry_summary(registry: dict[str, Any], user_record: dict[str, Any]) -> dict[str, Any]:
    user_id = user_record.get("id") or user_record.get("username")
    if not user_id:
        raise ValueError("user record missing id")
    entry = registry_entry(registry, user_id)
    entry["lastSeenAt"] = now_text()
    for field in (
        "screenName",
        "briefIntro",
        "bio",
        "link",
        "followingCount",
        "followedCount",
        "respectedCount",
        "isSponsor",
    ):
        value = user_record.get(field)
        if value in (None, "", [], {}):
            continue
        entry[field] = value
    return entry


def set_registry_filter(
    registry: dict[str, Any],
    user_record: dict[str, Any],
    tag: str,
    reasons: list[str],
) -> dict[str, Any]:
    entry = update_registry_summary(registry, user_record)
    entry["skipDeepCrawl"] = True
    entry["tags"] = unique_preserve(entry.get("tags", []) + [tag])
    entry["filterReasons"] = unique_preserve(entry.get("filterReasons", []) + reasons)
    entry["filteredAt"] = now_text()
    return entry


def clear_registry_filter(registry: dict[str, Any], user_record: dict[str, Any]) -> dict[str, Any]:
    entry = update_registry_summary(registry, user_record)
    tags = [tag for tag in entry.get("tags", []) if tag not in (FILTER_TAG_ROLE, FILTER_TAG_LOW_ACTIVITY)]
    entry["tags"] = tags
    if not tags:
        entry["skipDeepCrawl"] = False
    return entry


def profile_to_summary(profile: dict[str, Any]) -> dict[str, Any]:
    stats = profile.get("statsCount", {})
    username = profile.get("username", "") or profile.get("id", "")
    return {
        "id": username,
        "screenName": profile.get("screenName", ""),
        "briefIntro": profile.get("briefIntro", ""),
        "bio": profile.get("bio", ""),
        "gender": profile.get("gender", ""),
        "link": f"https://web.okjike.com/u/{username}" if username else "",
        "followingCount": stats.get("followingCount", profile.get("followingCount", 0)),
        "followedCount": stats.get("followedCount", profile.get("followedCount", 0)),
        "respectedCount": stats.get("respectedCount", profile.get("respectedCount", 0)),
        "isSponsor": profile.get("isSponsor", False),
    }


def relation_user_to_summary(user: dict[str, Any]) -> dict[str, Any]:
    stats = user.get("statsCount", {})
    username = user.get("username", "") or user.get("id", "")
    return {
        "id": username,
        "screenName": user.get("screenName", ""),
        "briefIntro": user.get("briefIntro", ""),
        "bio": user.get("bio", ""),
        "link": f"https://web.okjike.com/u/{username}" if username else "",
        "followingCount": stats.get("followingCount", user.get("followingCount", 0)),
        "followedCount": stats.get("followedCount", user.get("followedCount", 0)),
        "isSponsor": user.get("isSponsor", False),
    }


def post_to_summary(post: dict[str, Any]) -> dict[str, Any]:
    topic = post.get("topic") or {}
    return {
        "id": post.get("id", ""),
        "type": post.get("type", ""),
        "topic": topic.get("content", ""),
        "content": post.get("content", ""),
        "createdAt": post.get("createdAt", ""),
        "likeCount": post.get("likeCount", 0),
        "commentCount": post.get("commentCount", 0),
        "shareCount": post.get("shareCount", 0),
    }


def comment_to_summary(comment: dict[str, Any]) -> dict[str, Any]:
    user = comment.get("user") or {}
    username = user.get("username", "")
    return {
        "id": comment.get("id", ""),
        "content": comment.get("content", ""),
        "createdAt": comment.get("createdAt", ""),
        "likeCount": comment.get("likeCount", 0),
        "replyCount": comment.get("replyCount", 0),
        "user": {
            "id": username,
            "screenName": user.get("screenName", ""),
            "link": f"https://web.okjike.com/u/{username}" if username else "",
        },
    }


def merge_relation_cache(existing: dict[str, Any] | None, update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing or {})
    for key in (
        "id",
        "profile",
        "following",
        "followers",
        "followingCaptured",
        "followersCaptured",
        "captureComplete",
        "capturedAt",
        "relationLimitRequested",
    ):
        value = update.get(key)
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


def relation_target_count(record: dict[str, Any], relation_type: str) -> int:
    profile = record.get("profile") or {}
    key = "followingCount" if relation_type == "following" else "followedCount"
    return int(profile.get(key, 0) or 0)


def relation_cache_satisfies(record: dict[str, Any] | None, relation_limit: int | None) -> bool:
    if not record:
        return False
    for relation_type, flag in (("following", "followingCaptured"), ("followers", "followersCaptured")):
        if not record.get(flag):
            return False
        items = record.get(relation_type, [])
        total = relation_target_count(record, relation_type)
        if relation_limit is None:
            if total and len(items) < total:
                return False
        else:
            target = relation_limit if total <= 0 else min(total, relation_limit)
            if len(items) < target:
                return False
    return True


def merge_user_records(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


def filter_text_for_user(user_record: dict[str, Any]) -> str:
    return " ".join(
        [
            user_record.get("screenName", ""),
            user_record.get("briefIntro", ""),
            user_record.get("bio", ""),
        ]
    )


def role_filter_reasons(user_record: dict[str, Any]) -> list[str]:
    hits = unique_preserve(keyword_hits(filter_text_for_user(user_record), FILTER_ROLE_KEYWORDS))
    if not hits:
        return []
    return [f"命中过滤词: {', '.join(hits)}"]


def post_text(post: dict[str, Any]) -> str:
    topic = post.get("topic")
    topic_text = topic.get("content", "") if isinstance(topic, dict) else post.get("topic", "")
    return " ".join([topic_text, post.get("content", "")]).strip()


def has_meaningful_post_content(posts: list[dict[str, Any]]) -> bool:
    return any(not blank_text(post_text(post)) for post in posts)


def low_activity_filter_reasons(user_record: dict[str, Any], posts: list[dict[str, Any]]) -> list[str]:
    followed_count = int(user_record.get("followedCount", 0) or 0)
    if followed_count >= LOW_ACTIVITY_FOLLOWED_THRESHOLD:
        return []
    if has_meaningful_post_content(posts):
        return []
    return [f"发帖内容为空且被关注少于 {LOW_ACTIVITY_FOLLOWED_THRESHOLD}"]


def skip_payload(user_record: dict[str, Any], tag: str, reasons: list[str]) -> dict[str, Any]:
    payload = dict(user_record)
    payload["skipDeepCrawl"] = True
    payload["tags"] = unique_preserve(payload.get("tags", []) + [tag])
    payload["filterReasons"] = unique_preserve(payload.get("filterReasons", []) + reasons)
    return payload


def extract_browser_token(login_hint_username: str, log_file: Path | None = None) -> str:
    captured: dict[str, str] = {}
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        cdp = context.new_cdp_session(page)
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})

        def on_request(request: Any) -> None:
            if "api.ruguoapp.com" not in request.url:
                return
            token = request.headers.get("x-jike-access-token", "")
            if token:
                captured["token"] = token

        page.on("request", on_request)
        page.goto("https://web.okjike.com/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        if "login" in page.url.lower():
            log("browser requires login, complete it and press Enter in terminal", log_file)
            input()

        if not captured.get("token"):
            page.goto(
                f"https://web.okjike.com/u/{login_hint_username}",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            time.sleep(5)

        if not captured.get("token"):
            token_from_storage = page.evaluate("() => localStorage.getItem('JK_ACCESS_TOKEN')")
            if token_from_storage:
                captured["token"] = token_from_storage

        context.close()
    return captured.get("token", "")


def get_token(
    login_hint_username: str = LOGIN_HINT_USERNAME,
    force_refresh: bool = False,
    log_file: Path | None = None,
) -> str:
    if not force_refresh and TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            try:
                response = requests.get(
                    f"{API_BASE}/users/profile",
                    headers={"x-jike-access-token": token},
                    timeout=10,
                )
                if response.status_code == 200:
                    log("reusing cached token", log_file)
                    return token
            except requests.RequestException:
                pass
            log("cached token expired, refreshing", log_file)

    token = extract_browser_token(login_hint_username, log_file=log_file)
    if token:
        TOKEN_FILE.write_text(token, encoding="utf-8")
        log("token refreshed", log_file)
    else:
        log("failed to capture token from browser", log_file)
    return token


class JikeClient:
    def __init__(
        self,
        token: str,
        login_hint_username: str,
        log_file: Path | None = None,
        request_interval: tuple[float, float] = (1.0, 3.0),
        batch_size: tuple[int, int] = (25, 40),
        batch_rest: tuple[float, float] = (8.0, 20.0),
        retry_times: int = 3,
        retry_delay: float = 4.0,
    ) -> None:
        self.token = token
        self.login_hint_username = login_hint_username
        self.log_file = log_file
        self.request_interval = request_interval
        self.batch_size = batch_size
        self.batch_rest = batch_rest
        self.retry_times = retry_times
        self.retry_delay = retry_delay
        self.request_count = 0
        self.batch_count = 0
        self.next_batch_threshold = random.randint(*batch_size)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://web.okjike.com/",
                "Origin": "https://web.okjike.com",
                "x-jike-access-token": token,
                "Content-Type": "application/json",
            }
        )

    def _throttle(self) -> None:
        time.sleep(random.uniform(*self.request_interval))
        self.batch_count += 1
        if self.batch_count < self.next_batch_threshold:
            return
        rest = random.uniform(*self.batch_rest)
        log(f"anti-bot rest {rest:.0f}s after {self.request_count} requests", self.log_file)
        time.sleep(rest)
        self.batch_count = 0
        self.next_batch_threshold = random.randint(*self.batch_size)

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response | None:
        self._throttle()
        self.request_count += 1

        for attempt in range(1, self.retry_times + 1):
            try:
                if method == "GET":
                    response = self.session.get(url, timeout=30, **kwargs)
                else:
                    response = self.session.post(url, timeout=30, **kwargs)

                if response.status_code == 429:
                    wait_seconds = self.retry_delay * (attempt + 1)
                    log(f"rate limited, wait {wait_seconds:.0f}s", self.log_file)
                    time.sleep(wait_seconds)
                    continue

                if response.status_code == 401:
                    log("token expired, refreshing", self.log_file)
                    new_token = get_token(
                        login_hint_username=self.login_hint_username,
                        force_refresh=True,
                        log_file=self.log_file,
                    )
                    if not new_token:
                        return None
                    self.token = new_token
                    self.session.headers["x-jike-access-token"] = new_token
                    continue

                return response
            except requests.RequestException as exc:
                if attempt >= self.retry_times:
                    log(f"request failed: {exc}", self.log_file)
                    return None
                wait_seconds = self.retry_delay * attempt
                log(f"request error: {exc}, retry in {wait_seconds:.0f}s", self.log_file)
                time.sleep(wait_seconds)
        return None

    def get_user_profile(self, username: str) -> dict[str, Any] | None:
        response = self._request("GET", f"{API_BASE}/users/profile", params={"username": username})
        if response and response.status_code == 200:
            return response.json().get("user")
        return None

    def get_relation_list(
        self,
        username: str,
        relation_type: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        endpoint = {
            "following": "userRelation/getFollowingList",
            "followers": "userRelation/getFollowerList",
        }[relation_type]
        results: list[dict[str, Any]] = []
        load_more_key: str | None = None

        while True:
            page_limit = PAGE_SIZE
            if limit:
                page_limit = min(PAGE_SIZE, max(limit - len(results), 1))
            body: dict[str, Any] = {"username": username, "limit": page_limit}
            if load_more_key:
                body["loadMoreKey"] = load_more_key
            response = self._request("POST", f"{API_BASE}/{endpoint}", json=body)
            if not response or response.status_code != 200:
                break
            payload = response.json()
            page_data = payload.get("data", [])
            results.extend(page_data)
            load_more_key = payload.get("loadMoreKey")
            if not load_more_key or not page_data:
                break
            if limit and len(results) >= limit:
                break

        return results[:limit] if limit else results

    def get_user_posts(self, username: str, limit: int | None) -> list[dict[str, Any]]:
        posts: list[dict[str, Any]] = []
        load_more_key: str | None = None
        while True:
            if limit and len(posts) >= limit:
                break
            page_limit = PAGE_SIZE
            if limit:
                page_limit = min(PAGE_SIZE, max(limit - len(posts), 1))
            body: dict[str, Any] = {"username": username, "limit": page_limit}
            if load_more_key:
                body["loadMoreKey"] = load_more_key
            response = self._request("POST", f"{API_BASE}/personalUpdate/single", json=body)
            if not response or response.status_code != 200:
                break
            payload = response.json()
            page_data = payload.get("data", [])
            posts.extend(page_data)
            load_more_key = payload.get("loadMoreKey")
            if not load_more_key or not page_data:
                break
        return posts[:limit] if limit else posts

    def get_post_comments(
        self,
        post_id: str,
        post_type: str,
        limit: int | None,
    ) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        load_more_key: str | None = None
        while True:
            if limit and len(comments) >= limit:
                break
            page_limit = PAGE_SIZE
            if limit:
                page_limit = min(PAGE_SIZE, max(limit - len(comments), 1))
            body: dict[str, Any] = {
                "targetId": post_id,
                "targetType": post_type or "ORIGINAL_POST",
                "limit": page_limit,
            }
            if load_more_key:
                body["loadMoreKey"] = load_more_key
            response = self._request("POST", f"{API_BASE}/comments/listPrimary", json=body)
            if not response or response.status_code != 200:
                break
            payload = response.json()
            page_data = payload.get("data", [])
            comments.extend(page_data)
            load_more_key = payload.get("loadMoreKey")
            if not load_more_key or not page_data:
                break
        return comments[:limit] if limit else comments


def crawl_seed_relations(
    client: JikeClient,
    seed_ids: list[str],
    run_dir: Path,
    relation_limit: int | None,
    registry: dict[str, Any],
) -> dict[str, Any]:
    raw_dir = run_dir / "raw"
    log_file = run_dir / "crawl.log"
    output_path = raw_dir / "seed_relations.json"
    records = load_json(output_path, {})

    for index, seed_id in enumerate(seed_ids, start=1):
        current = records.get(seed_id)
        if current and current.get("skipDeepCrawl"):
            log(f"seed {index}/{len(seed_ids)} {seed_id} already captured", log_file)
            continue
        if relation_cache_satisfies(current, relation_limit):
            log(f"seed {index}/{len(seed_ids)} {seed_id} already captured", log_file)
            continue

        entry = registry.get(seed_id, {})
        if entry.get("skipDeepCrawl"):
            skip_tag = (entry.get("tags") or [FILTER_TAG_ROLE])[0]
            records[seed_id] = skip_payload(entry, skip_tag, entry.get("filterReasons", []))
            save_json(output_path, records)
            log(f"seed {seed_id} skipped by registry tag {skip_tag}", log_file)
            continue

        cached = load_cached_record(RELATION_CACHE_DIR, seed_id)
        if entry.get("relationCaptured") and relation_cache_satisfies(cached, relation_limit):
            if cached:
                records[seed_id] = cached
                save_json(output_path, records)
                log(f"seed {seed_id} reused cached relations", log_file)
                continue

        log(f"seed {index}/{len(seed_ids)} {seed_id} relation crawl start", log_file)
        profile = client.get_user_profile(seed_id) or {"username": seed_id}
        profile_summary = profile_to_summary(profile)
        update_registry_summary(registry, profile_summary)

        role_reasons = role_filter_reasons(profile_summary)
        if role_reasons:
            set_registry_filter(registry, profile_summary, FILTER_TAG_ROLE, role_reasons)
            records[seed_id] = skip_payload(profile_summary, FILTER_TAG_ROLE, role_reasons)
            save_json(output_path, records)
            save_registry(registry)
            log(f"seed {seed_id} skipped by role filter", log_file)
            continue

        quick_posts = client.get_user_posts(seed_id, LOW_ACTIVITY_POST_SCAN_LIMIT)
        low_activity_reasons = low_activity_filter_reasons(profile_summary, quick_posts)
        if low_activity_reasons:
            set_registry_filter(registry, profile_summary, FILTER_TAG_LOW_ACTIVITY, low_activity_reasons)
            records[seed_id] = skip_payload(profile_summary, FILTER_TAG_LOW_ACTIVITY, low_activity_reasons)
            save_json(output_path, records)
            save_registry(registry)
            log(f"seed {seed_id} skipped by low activity filter", log_file)
            continue

        clear_registry_filter(registry, profile_summary)
        following = client.get_relation_list(seed_id, "following", relation_limit)
        followers = client.get_relation_list(seed_id, "followers", relation_limit)
        relation_record = {
            "id": seed_id,
            "profile": profile_summary,
            "following": [relation_user_to_summary(user) for user in following],
            "followers": [relation_user_to_summary(user) for user in followers],
            "followingCaptured": True,
            "followersCaptured": True,
            "captureComplete": True,
            "capturedAt": now_text(),
            "relationLimitRequested": relation_limit,
        }
        records[seed_id] = relation_record
        save_cached_record(RELATION_CACHE_DIR, seed_id, relation_record)
        entry = registry_entry(registry, seed_id)
        entry["relationCaptured"] = True
        entry["followingCaptured"] = True
        entry["followersCaptured"] = True
        entry["relationCapturedAt"] = now_text()
        save_json(output_path, records)
        save_registry(registry)
        log(
            f"seed {seed_id} captured: following={len(following)} followers={len(followers)} requests={client.request_count}",
            log_file,
        )

    return records


def candidate_priority(record: dict[str, Any]) -> float:
    return round(
        len(record["followedBySeedIds"]) * 3.0
        + len(record["followsSeedIds"]) * 2.0
        + math.log1p(record.get("followedCount", 0))
        + math.log1p(record.get("followingCount", 0)) * 0.2,
        2,
    )


def build_candidate_index(seed_relations: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    seed_ids = set(seed_relations.keys())
    candidates: dict[str, Any] = {}

    for seed_id, seed in seed_relations.items():
        for relation_type, field_name in (("following", "followedBySeedIds"), ("followers", "followsSeedIds")):
            for user in seed.get(relation_type, []):
                user_id = user.get("id")
                if not user_id:
                    continue
                current = candidates.get(
                    user_id,
                    {
                        "id": user_id,
                        "screenName": user.get("screenName", ""),
                        "briefIntro": user.get("briefIntro", ""),
                        "bio": user.get("bio", ""),
                        "link": user.get("link", ""),
                        "followingCount": user.get("followingCount", 0),
                        "followedCount": user.get("followedCount", 0),
                        "followedBySeedIds": [],
                        "followsSeedIds": [],
                        "isSeed": user_id in seed_ids,
                        "skipDeepCrawl": False,
                        "tags": [],
                        "filterReasons": [],
                    },
                )
                current = merge_user_records(current, user)
                current[field_name] = unique_preserve(current[field_name] + [seed_id])
                current["isSeed"] = user_id in seed_ids
                update_registry_summary(registry, current)
                entry = registry.get(user_id, {})
                role_reasons = role_filter_reasons(current)
                if role_reasons:
                    entry = set_registry_filter(registry, current, FILTER_TAG_ROLE, role_reasons)
                if entry.get("skipDeepCrawl"):
                    current["skipDeepCrawl"] = True
                    current["tags"] = unique_preserve(current.get("tags", []) + entry.get("tags", []))
                    current["filterReasons"] = unique_preserve(
                        current.get("filterReasons", []) + entry.get("filterReasons", [])
                    )
                candidates[user_id] = current

    for record in candidates.values():
        record["seedTouchIds"] = unique_preserve(record["followedBySeedIds"] + record["followsSeedIds"])
        record["seedTouchCount"] = len(record["seedTouchIds"])
        record["priorityScore"] = candidate_priority(record)

    save_registry(registry)
    return dict(
        sorted(
            candidates.items(),
            key=lambda item: (
                item[1].get("skipDeepCrawl", False),
                -item[1]["priorityScore"],
                -item[1].get("followedCount", 0),
                item[1].get("screenName", ""),
            ),
        )
    )


def crawl_candidate_details(
    client: JikeClient,
    candidate_index: dict[str, Any],
    run_dir: Path,
    posts_limit: int | None,
    comments_limit: int | None,
    candidate_limit: int | None,
    registry: dict[str, Any],
) -> dict[str, Any]:
    raw_dir = run_dir / "raw"
    log_file = run_dir / "crawl.log"
    output_path = raw_dir / "candidate_details.json"
    queue_path = raw_dir / "crawl_queue.json"
    records = load_json(output_path, {})

    ranked = [
        record
        for record in candidate_index.values()
        if not record.get("isSeed") and not record.get("skipDeepCrawl")
    ]
    if candidate_limit:
        ranked = ranked[:candidate_limit]

    queue_payload = {
        "generatedAt": now_text(),
        "candidateCount": len(ranked),
        "candidateIds": [record["id"] for record in ranked],
    }
    save_json(queue_path, queue_payload)

    for index, candidate in enumerate(ranked, start=1):
        user_id = candidate["id"]
        current = records.get(user_id)
        if current and current.get("captureComplete"):
            log(f"candidate {index}/{len(ranked)} {user_id} already captured", log_file)
            continue

        entry = registry.get(user_id, {})
        if entry.get("skipDeepCrawl"):
            skip_tag = (entry.get("tags") or [FILTER_TAG_ROLE])[0]
            log(f"candidate {user_id} skipped by registry tag {skip_tag}", log_file)
            continue

        if entry.get("detailCaptured"):
            cached = load_cached_record(DETAIL_CACHE_DIR, user_id)
            if cached:
                records[user_id] = cached
                save_json(output_path, records)
                log(f"candidate {user_id} reused cached details", log_file)
                continue

        log(
            f"candidate {index}/{len(ranked)} {candidate.get('screenName') or user_id} capture start",
            log_file,
        )
        profile = client.get_user_profile(user_id)
        summary = profile_to_summary(profile) if profile else {}
        record = merge_user_records(candidate, summary)
        update_registry_summary(registry, record)

        role_reasons = role_filter_reasons(record)
        if role_reasons:
            set_registry_filter(registry, record, FILTER_TAG_ROLE, role_reasons)
            save_registry(registry)
            log(f"candidate {user_id} skipped by role filter after profile", log_file)
            continue

        probe_posts = client.get_user_posts(user_id, LOW_ACTIVITY_POST_SCAN_LIMIT)
        low_activity_reasons = low_activity_filter_reasons(record, probe_posts)
        if low_activity_reasons:
            set_registry_filter(registry, record, FILTER_TAG_LOW_ACTIVITY, low_activity_reasons)
            save_registry(registry)
            log(f"candidate {user_id} skipped by low activity filter", log_file)
            continue

        clear_registry_filter(registry, record)
        if posts_limit is None or posts_limit > LOW_ACTIVITY_POST_SCAN_LIMIT:
            posts = client.get_user_posts(user_id, posts_limit)
        else:
            posts = probe_posts[:posts_limit]
        record["posts"] = []
        commenter_counter: Counter[str] = Counter()
        commenter_names: dict[str, str] = {}

        for post in posts:
            post_info = post_to_summary(post)
            comments: list[dict[str, Any]] = []
            if comments_limit != 0 and post_info["commentCount"] > 0:
                raw_comments = client.get_post_comments(
                    post_info["id"],
                    post_info["type"],
                    comments_limit,
                )
                comments = [comment_to_summary(comment) for comment in raw_comments]
                for comment in comments:
                    comment_user = comment.get("user", {})
                    comment_user_id = comment_user.get("id", "")
                    if comment_user_id:
                        commenter_counter[comment_user_id] += 1
                        commenter_names[comment_user_id] = comment_user.get("screenName", "")
            post_info["comments"] = comments
            record["posts"].append(post_info)

        record["uniqueCommenterCount"] = len(commenter_counter)
        record["topCommenters"] = [
            {
                "id": user_id,
                "screenName": commenter_names.get(user_id, ""),
                "count": count,
                "link": f"https://web.okjike.com/u/{user_id}",
            }
            for user_id, count in commenter_counter.most_common(20)
        ]
        record["captureComplete"] = True
        record["capturedAt"] = now_text()
        entry = registry_entry(registry, user_id)
        entry["detailCaptured"] = True
        entry["detailCapturedAt"] = now_text()
        records[user_id] = record
        save_cached_record(DETAIL_CACHE_DIR, user_id, record)
        save_json(output_path, records)
        save_registry(registry)
        log(
            f"candidate {user_id} saved: posts={len(record['posts'])} commenters={record['uniqueCommenterCount']} requests={client.request_count}",
            log_file,
        )

    return records


def build_anchor_map(anchor_followers: dict[str, Any]) -> dict[str, list[str]]:
    reverse_map: defaultdict[str, list[str]] = defaultdict(list)
    for anchor_id, payload in anchor_followers.items():
        for user in payload.get("followers", []):
            user_id = user.get("id")
            if not user_id:
                continue
            reverse_map[user_id].append(anchor_id)
    return {user_id: unique_preserve(anchor_ids) for user_id, anchor_ids in reverse_map.items()}


def crawl_anchor_followers(
    client: JikeClient,
    run_dir: Path,
    anchor_ids: list[str],
    follower_limit: int | None,
    registry: dict[str, Any],
) -> dict[str, Any]:
    raw_dir = run_dir / "raw"
    log_file = run_dir / "crawl.log"
    output_path = raw_dir / "anchor_followers.json"
    records = load_json(output_path, {})

    for anchor_id in anchor_ids:
        current = records.get(anchor_id)
        if current and current.get("captureComplete"):
            log(f"anchor {anchor_id} follower list already captured", log_file)
            continue
        entry = registry.get(anchor_id, {})
        if entry.get("relationCaptured"):
            cached = load_cached_record(RELATION_CACHE_DIR, anchor_id)
            if cached and cached.get("followers"):
                records[anchor_id] = {
                    "anchorId": anchor_id,
                    "followers": cached.get("followers", []),
                    "captureComplete": True,
                    "capturedAt": cached.get("capturedAt", now_text()),
                }
                save_json(output_path, records)
                log(f"anchor {anchor_id} reused cached followers", log_file)
                continue
        followers = client.get_relation_list(anchor_id, "followers", follower_limit)
        records[anchor_id] = {
            "anchorId": anchor_id,
            "followers": [relation_user_to_summary(user) for user in followers],
            "followersCaptured": True,
            "captureComplete": True,
            "capturedAt": now_text(),
        }
        cached = merge_relation_cache(load_cached_record(RELATION_CACHE_DIR, anchor_id), records[anchor_id])
        save_cached_record(RELATION_CACHE_DIR, anchor_id, cached)
        update_registry_summary(registry, {"id": anchor_id})
        entry = registry_entry(registry, anchor_id)
        entry["followersCaptured"] = True
        entry["followersCapturedAt"] = now_text()
        save_json(output_path, records)
        save_registry(registry)
        log(f"anchor {anchor_id} followers={len(followers)}", log_file)

    return records


def collect_filtered_users(
    seed_relations: dict[str, Any],
    candidate_index: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    encountered_ids = set(seed_relations.keys()) | set(candidate_index.keys())
    filtered: list[dict[str, Any]] = []
    for user_id in encountered_ids:
        entry = registry.get(user_id, {})
        tags = entry.get("tags", [])
        if not any(tag in (FILTER_TAG_ROLE, FILTER_TAG_LOW_ACTIVITY) for tag in tags):
            continue
        filtered.append(
            {
                "id": user_id,
                "screenName": entry.get("screenName", ""),
                "link": entry.get("link", f"https://web.okjike.com/u/{user_id}"),
                "tags": tags,
                "filterReasons": entry.get("filterReasons", []),
            }
        )
    filtered.sort(key=lambda item: (item["tags"][0], item["screenName"], item["id"]))
    return {
        "roleKeywordFiltered": [item for item in filtered if FILTER_TAG_ROLE in item["tags"]],
        "lowActivityFiltered": [item for item in filtered if FILTER_TAG_LOW_ACTIVITY in item["tags"]],
    }


def analyze_candidate(
    seed_ids: set[str],
    candidate_index: dict[str, Any],
    candidate_id: str,
    detail: dict[str, Any] | None,
    anchor_map: dict[str, list[str]],
) -> dict[str, Any]:
    base = merge_user_records(candidate_index[candidate_id], detail or {})
    profile_text = " ".join([base.get("screenName", ""), base.get("briefIntro", ""), base.get("bio", "")])
    profile_ai_hits = unique_preserve(keyword_hits(profile_text, AI_KEYWORDS))
    profile_role_hits = unique_preserve(keyword_hits(profile_text, ROLE_KEYWORDS))
    profile_negative_hits = unique_preserve(keyword_hits(profile_text, NEGATIVE_KEYWORDS))

    posts = base.get("posts", [])
    ai_post_count = 0
    tech_post_count = 0
    negative_post_count = 0
    tech_discussion_comment_count = 0
    high_quality_discussion_comment_count = 0
    evidence_posts: list[dict[str, Any]] = []
    evidence_comments: list[dict[str, Any]] = []
    comment_user_ids: set[str] = set()

    for post in posts:
        post_text = " ".join([post.get("topic", ""), post.get("content", "")])
        ai_hits = keyword_hits(post_text, AI_KEYWORDS)
        tech_hits = keyword_hits(post_text, TECH_KEYWORDS)
        negative_hits = keyword_hits(post_text, NEGATIVE_KEYWORDS)
        if ai_hits:
            ai_post_count += 1
        if tech_hits:
            tech_post_count += 1
        if negative_hits:
            negative_post_count += 1
        if (ai_hits or tech_hits) and len(evidence_posts) < 3:
            evidence_posts.append(
                {
                    "id": post.get("id", ""),
                    "snippet": truncate_text(post_text, 120),
                    "keywords": unique_preserve(ai_hits + tech_hits)[:6],
                }
            )
        for comment in post.get("comments", []):
            comment_user_id = (comment.get("user") or {}).get("id", "")
            if comment_user_id:
                comment_user_ids.add(comment_user_id)
            comment_text = comment.get("content", "")
            comment_ai_hits = keyword_hits(comment_text, AI_KEYWORDS)
            comment_tech_hits = keyword_hits(comment_text, TECH_KEYWORDS)
            discussion_hits = keyword_hits(comment_text, DISCUSSION_QUALITY_KEYWORDS)
            if comment_ai_hits or comment_tech_hits:
                tech_discussion_comment_count += 1
            if discussion_hits and len(normalize_text(comment_text)) >= 24:
                high_quality_discussion_comment_count += 1
                if len(evidence_comments) < 3:
                    evidence_comments.append(
                        {
                            "id": comment.get("id", ""),
                            "snippet": truncate_text(comment_text, 120),
                            "keywords": unique_preserve(comment_ai_hits + comment_tech_hits + discussion_hits)[:6],
                            "user": (comment.get("user") or {}).get("screenName", ""),
                        }
                    )

    followed_by_seed_count = len(base.get("followedBySeedIds", []))
    follows_seed_count = len(base.get("followsSeedIds", []))
    follows_ai_anchor_ids = anchor_map.get(candidate_id, [])
    follows_ai_anchor_count = len(follows_ai_anchor_ids)
    unique_commenter_count = len(comment_user_ids) or base.get("uniqueCommenterCount", 0)
    seed_comment_overlap = len(comment_user_ids & seed_ids)
    followed_count = int(base.get("followedCount", 0) or 0)
    seed_count = max(len(seed_ids), 1)
    seed_touch_count = len(base.get("seedTouchIds", []))
    seed_followed_rate = round(followed_by_seed_count / seed_count, 4)
    seed_connected_rate = round(seed_touch_count / seed_count, 4)

    ai_signal_score = (
        len(profile_ai_hits) * 3
        + len(profile_role_hits) * 2
        + ai_post_count * 2
        + tech_post_count
        - len(profile_negative_hits) * 2
        - negative_post_count
    )
    developer_signal_score = (
        len(profile_role_hits) * 3
        + tech_post_count * 2
        + ai_post_count
        + tech_discussion_comment_count
        + high_quality_discussion_comment_count * 2
        - len(profile_negative_hits) * 2
        - negative_post_count
    )
    relation_score = (
        followed_by_seed_count * 3
        + follows_seed_count * 2
        + follows_ai_anchor_count * 4
        + seed_comment_overlap
    )
    known_tech_graph_score = round(
        followed_by_seed_count * 5
        + follows_seed_count * 2
        + follows_ai_anchor_count * 4
        + seed_touch_count * 1.5
        + high_quality_discussion_comment_count * 0.5,
        2,
    )
    confidence_score = round(
        ai_signal_score * 1.2
        + relation_score
        + math.log1p(followed_count)
        + min(unique_commenter_count, 20) * 0.2,
        2,
    )

    reasons: list[str] = []
    if profile_role_hits:
        reasons.append(f"简介命中技术角色: {', '.join(profile_role_hits[:3])}")
    if profile_ai_hits:
        reasons.append(f"简介命中 AI 关键词: {', '.join(profile_ai_hits[:4])}")
    if ai_post_count:
        reasons.append(f"最近动态里有 {ai_post_count} 条 AI 相关内容")
    if tech_post_count:
        reasons.append(f"最近动态里有 {tech_post_count} 条技术相关内容")
    if tech_discussion_comment_count:
        reasons.append(f"评论区里有 {tech_discussion_comment_count} 条技术讨论")
    if high_quality_discussion_comment_count:
        reasons.append(f"其中 {high_quality_discussion_comment_count} 条像高质量技术讨论")
    if followed_by_seed_count:
        reasons.append(f"被 {followed_by_seed_count} 个种子账号关注")
    if follows_seed_count:
        reasons.append(f"关注了 {follows_seed_count} 个种子账号")
    if follows_ai_anchor_count:
        reasons.append(f"关注了 {follows_ai_anchor_count} 个已确认 AI 技术人")
    if seed_connected_rate >= 0.03:
        reasons.append(f"与已知技术号连接率 {seed_connected_rate:.1%}")
    if seed_comment_overlap:
        reasons.append(f"有 {seed_comment_overlap} 个种子账号出现在其评论区")
    if unique_commenter_count:
        reasons.append(f"评论区涉及 {unique_commenter_count} 个不同用户")
    if profile_negative_hits:
        reasons.append(f"存在非技术信号: {', '.join(profile_negative_hits[:3])}")

    confirmed_developer = (
        developer_signal_score >= 12
        and (
            len(profile_role_hits) >= 1
            or tech_post_count >= 2
            or high_quality_discussion_comment_count >= 2
        )
    )
    probable_developer = (
        not confirmed_developer
        and developer_signal_score >= 7
        and (
            tech_post_count >= 1
            or tech_discussion_comment_count >= 2
            or len(profile_role_hits) >= 1
        )
    )
    confirmed_ai = (
        ai_signal_score >= 12
        and confirmed_developer
        and (ai_post_count >= 2 or len(profile_role_hits) >= 1)
    ) or (
        ai_signal_score >= 9 and confirmed_developer and followed_by_seed_count >= 2 and tech_post_count >= 2
    )
    probable_ai = (
        not confirmed_ai
        and (confirmed_developer or probable_developer)
        and (
            (ai_signal_score >= 8 and tech_post_count >= 1)
            or (relation_score >= 10 and (ai_post_count >= 1 or follows_ai_anchor_count >= 2))
        )
    )
    known_tech_graph_candidate = (
        not confirmed_developer
        and not probable_developer
        and (
            follows_ai_anchor_count >= 2
            or followed_by_seed_count >= 3
            or seed_touch_count >= 4
            or seed_followed_rate >= 0.02
        )
    )

    return {
        "id": candidate_id,
        "screenName": base.get("screenName", ""),
        "link": base.get("link", ""),
        "briefIntro": base.get("briefIntro", ""),
        "bio": base.get("bio", ""),
        "followingCount": base.get("followingCount", 0),
        "followedCount": followed_count,
        "seedTouchCount": seed_touch_count,
        "followedBySeedIds": base.get("followedBySeedIds", []),
        "followsSeedIds": base.get("followsSeedIds", []),
        "followsAiAnchorIds": follows_ai_anchor_ids,
        "aiSignalScore": ai_signal_score,
        "developerSignalScore": developer_signal_score,
        "relationScore": relation_score,
        "knownTechGraphScore": known_tech_graph_score,
        "confidenceScore": confidence_score,
        "aiPostCount": ai_post_count,
        "techPostCount": tech_post_count,
        "techDiscussionCommentCount": tech_discussion_comment_count,
        "highQualityDiscussionCommentCount": high_quality_discussion_comment_count,
        "seedFollowedRate": seed_followed_rate,
        "seedConnectedRate": seed_connected_rate,
        "uniqueCommenterCount": unique_commenter_count,
        "evidencePosts": evidence_posts,
        "evidenceComments": evidence_comments,
        "reasons": reasons,
        "confirmedDeveloper": confirmed_developer,
        "probableDeveloper": probable_developer,
        "confirmedAiTech": confirmed_ai,
        "probableAiTech": probable_ai,
        "knownTechGraphCandidate": known_tech_graph_candidate,
        "contentCaptured": bool(detail),
    }


def write_report(run_dir: Path, analysis: dict[str, Any]) -> Path:
    path = run_dir / "report.md"
    lines: list[str] = []
    summary = analysis["summary"]
    lines.append("# 即刻技术人分析报告")
    lines.append("")
    lines.append(f"- 生成时间: {summary['generatedAt']}")
    lines.append(f"- 种子账号: {summary['seedCount']}")
    lines.append(f"- 关系池候选人: {summary['candidatePoolSize']}")
    lines.append(f"- 已抓内容候选人: {summary['detailCapturedCount']}")
    lines.append(f"- 角色词过滤: {summary['roleKeywordFilteredCount']}")
    lines.append(f"- 低活跃过滤: {summary['lowActivityFilteredCount']}")
    lines.append(f"- 确定是开发人员: {summary['confirmedDeveloperCount']}")
    lines.append(f"- 高概率开发人员: {summary['probableDeveloperCount']}")
    lines.append(f"- 确定是 AI 技术的人: {summary['confirmedAiTechCount']}")
    lines.append(f"- 高概率 AI 技术人: {summary['probableAiTechCount']}")
    lines.append(f"- 技术关系扩散候选人: {summary['knownTechGraphCandidateCount']}")
    lines.append("")

    sections = [
        ("确定是开发人员", analysis["confirmedDevelopers"]),
        ("高概率开发人员", analysis["probableDevelopers"]),
        ("确定是 AI 技术的人", analysis["confirmedAiTech"]),
        ("高概率 AI 技术人", analysis["probableAiTech"]),
        ("技术关系扩散候选人", analysis["knownTechGraphCandidates"]),
    ]

    for title, records in sections:
        lines.append(f"## {title}")
        lines.append("")
        if not records:
            lines.append("- 暂无")
            lines.append("")
            continue
        for rank, record in enumerate(records[:REPORT_LIMIT], start=1):
            lines.append(
                f"{rank}. {record['screenName'] or record['id']} | 分数 {record['confidenceScore']} | {record['link']}"
            )
            if record["briefIntro"]:
                lines.append(f"   - 简介: {truncate_text(record['briefIntro'], 80)}")
            lines.append(f"   - 判定: {'; '.join(record['reasons'][:4])}")
            if record["evidencePosts"]:
                example = record["evidencePosts"][0]
                lines.append(f"   - 代表动态: {example['snippet']}")
            elif record["evidenceComments"]:
                example = record["evidenceComments"][0]
                lines.append(f"   - 代表讨论: {example['snippet']}")
        lines.append("")

    filtered_sections = [
        ("角色词过滤名单", analysis["filteredUsers"]["roleKeywordFiltered"]),
        ("低活跃过滤名单", analysis["filteredUsers"]["lowActivityFiltered"]),
    ]
    for title, records in filtered_sections:
        lines.append(f"## {title}")
        lines.append("")
        if not records:
            lines.append("- 暂无")
            lines.append("")
            continue
        for rank, record in enumerate(records[:REPORT_LIMIT], start=1):
            lines.append(f"{rank}. {record['screenName'] or record['id']} | {record['link']}")
            lines.append(f"   - 标签: {', '.join(record['tags'])}")
            if record["filterReasons"]:
                lines.append(f"   - 原因: {'; '.join(record['filterReasons'][:2])}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_analysis(
    run_dir: Path,
    expand_top_tech: int,
    anchor_follower_limit: int | None,
    seed_ids_for_login: list[str] | None = None,
) -> dict[str, Any]:
    raw_dir = run_dir / "raw"
    log_file = run_dir / "crawl.log"
    seed_relations = load_json(raw_dir / "seed_relations.json", {})
    candidate_index = load_json(raw_dir / "candidate_index.json", {})
    candidate_details = load_json(raw_dir / "candidate_details.json", {})
    anchor_followers = load_json(raw_dir / "anchor_followers.json", {})
    registry = load_registry()
    if not seed_relations or not candidate_index:
        raise ValueError(f"missing raw crawl data under {run_dir}")

    seed_ids = set(seed_relations.keys())
    anchor_map = build_anchor_map(anchor_followers)
    filtered_users = collect_filtered_users(seed_relations, candidate_index, registry)

    records = [
        analyze_candidate(seed_ids, candidate_index, candidate_id, candidate_details.get(candidate_id), anchor_map)
        for candidate_id in candidate_index.keys()
        if not candidate_index[candidate_id].get("isSeed") and not candidate_index[candidate_id].get("skipDeepCrawl")
    ]
    records.sort(key=lambda item: (-item["confidenceScore"], -item["relationScore"], item["screenName"]))

    confirmed_developers = [item for item in records if item["confirmedDeveloper"]]
    probable_developers = [item for item in records if item["probableDeveloper"]]
    confirmed = [item for item in records if item["confirmedAiTech"]]
    probable = [item for item in records if item["probableAiTech"]]
    known_tech_graph_candidates = [item for item in records if item["knownTechGraphCandidate"]]

    if expand_top_tech:
        selected_anchor_ids = [item["id"] for item in confirmed[:expand_top_tech]]
        if selected_anchor_ids:
            login_hint = (seed_ids_for_login or list(seed_ids) or [LOGIN_HINT_USERNAME])[0]
            token = get_token(login_hint_username=login_hint, log_file=log_file)
            if not token:
                raise ValueError("cannot refresh token for anchor expansion")
            client = JikeClient(token=token, login_hint_username=login_hint, log_file=log_file)
            anchor_followers = crawl_anchor_followers(
                client=client,
                run_dir=run_dir,
                anchor_ids=selected_anchor_ids,
                follower_limit=anchor_follower_limit,
                registry=registry,
            )
            anchor_map = build_anchor_map(anchor_followers)
            records = [
                analyze_candidate(seed_ids, candidate_index, candidate_id, candidate_details.get(candidate_id), anchor_map)
                for candidate_id in candidate_index.keys()
                if not candidate_index[candidate_id].get("isSeed") and not candidate_index[candidate_id].get("skipDeepCrawl")
            ]
            records.sort(key=lambda item: (-item["confidenceScore"], -item["relationScore"], item["screenName"]))
            confirmed_developers = [item for item in records if item["confirmedDeveloper"]]
            probable_developers = [item for item in records if item["probableDeveloper"]]
            confirmed = [item for item in records if item["confirmedAiTech"]]
            probable = [item for item in records if item["probableAiTech"]]
            known_tech_graph_candidates = [item for item in records if item["knownTechGraphCandidate"]]

    analysis = {
        "summary": {
            "generatedAt": now_text(),
            "seedCount": len(seed_relations),
            "candidatePoolSize": len([item for item in candidate_index.values() if not item.get("isSeed")]),
            "detailCapturedCount": len(candidate_details),
            "roleKeywordFilteredCount": len(filtered_users["roleKeywordFiltered"]),
            "lowActivityFilteredCount": len(filtered_users["lowActivityFiltered"]),
            "confirmedDeveloperCount": len(confirmed_developers),
            "probableDeveloperCount": len(probable_developers),
            "confirmedAiTechCount": len(confirmed),
            "probableAiTechCount": len(probable),
            "knownTechGraphCandidateCount": len(known_tech_graph_candidates),
        },
        "filteredUsers": filtered_users,
        "confirmedDevelopers": confirmed_developers,
        "probableDevelopers": probable_developers,
        "confirmedAiTech": confirmed,
        "probableAiTech": probable,
        "knownTechGraphCandidates": known_tech_graph_candidates,
        "allRanked": records,
    }
    save_json(raw_dir / "filtered_users.json", filtered_users)
    save_json(run_dir / "analysis.json", analysis)
    report_path = write_report(run_dir, analysis)
    log(f"analysis saved to {run_dir / 'analysis.json'}", log_file)
    log(f"report saved to {report_path}", log_file)
    return analysis


def cmd_full(args: argparse.Namespace) -> None:
    seed_file = Path(args.seed_file).expanduser().resolve()
    seed_ids = load_seed_usernames(seed_file)
    run_dir = make_run_dir(args.run_name)
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_file = run_dir / "crawl.log"
    registry = load_registry()
    relation_limit = None if args.relation_limit <= 0 else args.relation_limit
    posts_limit = None if args.posts_limit <= 0 else args.posts_limit
    comments_limit = None if args.comments_limit < 0 else args.comments_limit
    candidate_limit = None if args.candidate_limit <= 0 else args.candidate_limit
    anchor_follower_limit = None if args.anchor_follower_limit <= 0 else args.anchor_follower_limit

    save_json(
        run_dir / "meta.json",
        {
            "createdAt": now_text(),
            "seedFile": str(seed_file),
            "seedIds": seed_ids,
            "relationLimit": relation_limit,
            "postsLimit": posts_limit,
            "commentsLimit": comments_limit,
            "candidateLimit": candidate_limit,
            "anchorFollowerLimit": anchor_follower_limit,
        },
    )

    token = get_token(login_hint_username=seed_ids[0], log_file=log_file)
    if not token:
        raise ValueError("failed to get Jike token")

    client = JikeClient(
        token=token,
        login_hint_username=seed_ids[0],
        log_file=log_file,
        request_interval=(args.request_min_interval, args.request_max_interval),
        batch_size=(args.batch_min_size, args.batch_max_size),
        batch_rest=(args.batch_min_rest, args.batch_max_rest),
        retry_times=args.retry_times,
        retry_delay=args.retry_delay,
    )

    seed_relations = crawl_seed_relations(client, seed_ids, run_dir, relation_limit, registry)
    candidate_index = build_candidate_index(seed_relations, registry)
    save_json(raw_dir / "candidate_index.json", candidate_index)
    crawl_candidate_details(
        client=client,
        candidate_index=candidate_index,
        run_dir=run_dir,
        posts_limit=posts_limit,
        comments_limit=comments_limit,
        candidate_limit=candidate_limit,
        registry=registry,
    )
    analysis = run_analysis(
        run_dir=run_dir,
        expand_top_tech=args.expand_top_tech,
        anchor_follower_limit=anchor_follower_limit,
        seed_ids_for_login=seed_ids,
    )
    log(
        (
            "full pipeline done: "
            f"developer={analysis['summary']['confirmedDeveloperCount']} "
            f"confirmed={analysis['summary']['confirmedAiTechCount']} "
            f"probable={analysis['summary']['probableAiTechCount']} "
            f"graph={analysis['summary']['knownTechGraphCandidateCount']}"
        ),
        log_file,
    )


def cmd_analyze(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir).expanduser().resolve()
    anchor_follower_limit = None if args.anchor_follower_limit <= 0 else args.anchor_follower_limit
    run_analysis(
        run_dir=run_dir,
        expand_top_tech=args.expand_top_tech,
        anchor_follower_limit=anchor_follower_limit,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jike seed crawler and AI-tech analyzer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    full = subparsers.add_parser("full", help="crawl seed network and analyze candidates")
    full.add_argument("--seed-file", required=True, help="text file with Jike profile links")
    full.add_argument("--run-name", help="optional run directory name")
    full.add_argument("--relation-limit", type=int, default=500, help="0 means crawl all relations")
    full.add_argument("--candidate-limit", type=int, default=250, help="0 means crawl all candidates")
    full.add_argument("--posts-limit", type=int, default=12, help="0 means crawl all posts")
    full.add_argument("--comments-limit", type=int, default=20, help="-1 means crawl all comments")
    full.add_argument("--expand-top-tech", type=int, default=8, help="expand follower graph for top confirmed AI-tech users")
    full.add_argument("--anchor-follower-limit", type=int, default=200, help="0 means crawl all anchor followers")
    full.add_argument("--request-min-interval", type=float, default=1.0)
    full.add_argument("--request-max-interval", type=float, default=3.0)
    full.add_argument("--batch-min-size", type=int, default=25)
    full.add_argument("--batch-max-size", type=int, default=40)
    full.add_argument("--batch-min-rest", type=float, default=8.0)
    full.add_argument("--batch-max-rest", type=float, default=20.0)
    full.add_argument("--retry-times", type=int, default=3)
    full.add_argument("--retry-delay", type=float, default=4.0)
    full.set_defaults(func=cmd_full)

    analyze = subparsers.add_parser("analyze", help="reanalyze an existing run")
    analyze.add_argument("--run-dir", required=True, help="existing run directory")
    analyze.add_argument("--expand-top-tech", type=int, default=0, help="optionally recrawl top confirmed AI-tech followers")
    analyze.add_argument("--anchor-follower-limit", type=int, default=200, help="0 means crawl all anchor followers")
    analyze.set_defaults(func=cmd_analyze)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
