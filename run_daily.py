#!/usr/bin/env python3
"""
run_daily.py — 每日一键运行：同步名单 + 自动关注/私信/评论

用法:
  python3 run_daily.py                        # 同步网站名单 + 自动触达
  python3 run_daily.py --skip-sync            # 跳过同步，用已有名单跑
  python3 run_daily.py --skip-auto            # 只同步名单，不跑自动触达
  python3 run_daily.py --test 3               # 自动触达只处理前 3 个人
  python3 run_daily.py --pipeline seeds.txt   # 用种子账号跑 pipeline 爬新人
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

PROJECT_DIR = Path(__file__).resolve().parent
TARGETS_FILE = PROJECT_DIR / "auto_targets.json"
PROGRESS_FILE = PROJECT_DIR / "auto_progress.json"

# wxk 复核台配置
SITE_URL = "http://101.43.187.45:8010"
SITE_USERNAME = "anke"
SITE_PASSWORD = "anke2026"
REVIEW_PAGES = [
    "/review/developers",
    "/review/entrepreneurs",
    "/review/entrepreneur-developers",
]


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def sync_targets_from_site() -> bool:
    """从 wxk 复核台同步最新名单"""
    log("========== 第 1 步：同步网站最新名单 ==========")

    session = requests.Session()
    try:
        resp = session.post(f"{SITE_URL}/login", json={
            "username": SITE_USERNAME,
            "password": SITE_PASSWORD,
        }, timeout=10)
        if resp.status_code != 200:
            log(f"登录失败: {resp.status_code}")
            return False
    except Exception as e:
        log(f"连接网站失败: {e}")
        return False

    log("登录成功，开始拉取名单...")

    all_users = {}
    for path in REVIEW_PAGES:
        label = path.split("/")[-1]
        page = 1
        page_total = 0
        while True:
            url = f"{SITE_URL}{path}?page={page}&page_size=50"
            try:
                resp = session.get(url, timeout=15)
            except Exception as e:
                log(f"  {label} page {page} 请求失败: {e}")
                break
            if resp.status_code != 200:
                break

            html = resp.text
            rows = re.findall(
                r'<a href="https://web\.okjike\.com/u/([^"]+)"[^>]*>([^<]+)</a>.*?col-count[^>]*>(\d+)',
                html, re.DOTALL
            )
            if not rows:
                break

            for uid, name, count in rows:
                if uid not in all_users:
                    all_users[uid] = {
                        "user_id": uid,
                        "username": name,
                        "follower_count": int(count),
                        "source": [label],
                    }
                else:
                    if label not in all_users[uid]["source"]:
                        all_users[uid]["source"].append(label)

            page_total += len(rows)

            if f"page={page+1}" not in html:
                break
            page += 1

        log(f"  {label}: {page_total} 人")

    if not all_users:
        log("未拉取到任何用户")
        return False

    # 加载已有的 targets，合并新用户
    existing = {}
    if TARGETS_FILE.exists():
        with open(TARGETS_FILE, "r", encoding="utf-8") as f:
            for item in json.load(f):
                existing[item["user_id"]] = item

    new_count = 0
    for uid, user in all_users.items():
        if uid not in existing:
            new_count += 1
        existing[uid] = user

    targets = sorted(existing.values(), key=lambda x: -x.get("follower_count", 0))

    with open(TARGETS_FILE, "w", encoding="utf-8") as f:
        json.dump(targets, f, ensure_ascii=False, indent=2)

    # 统计待处理数
    processed_ids = set()
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)
        processed_ids = set(progress.get("processed", {}).keys())

    pending = sum(1 for t in targets if t["user_id"] not in processed_ids)

    log(f"同步完成! 总计 {len(targets)} 人, 新增 {new_count} 人, 待处理 {pending} 人")
    return True


def run_pipeline(seed_file: str, run_name: str) -> bool:
    """运行爬人 pipeline"""
    log("========== 运行 Pipeline 爬取新人 ==========")
    cmd = [
        sys.executable, str(PROJECT_DIR / "jike_pipeline.py"),
        "full",
        "--seed-file", seed_file,
        "--run-name", run_name,
    ]
    log(f"运行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_DIR))
    if result.returncode != 0:
        log(f"爬人失败（退出码 {result.returncode}）")
        return False
    log("爬人完成!")
    return True


def run_auto(test_count: int | None = None) -> bool:
    """运行自动关注/私信/评论"""
    log("========== 第 2 步：自动关注/私信/评论 ==========")

    if not TARGETS_FILE.exists():
        log("auto_targets.json 不存在，跳过自动触达")
        return False

    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        targets = json.load(f)
    if not targets:
        log("目标用户列表为空，跳过")
        return False

    # 统计待处理
    processed_ids = set()
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)
        processed_ids = set(progress.get("processed", {}).keys())

    pending = sum(1 for t in targets if t["user_id"] not in processed_ids)
    log(f"目标用户: {len(targets)} 个, 待处理: {pending} 个")

    if pending == 0:
        log("所有用户已处理完毕!")
        return True

    cmd = [sys.executable, str(PROJECT_DIR / "jike_auto.py")]
    if test_count:
        cmd.extend(["--test", str(test_count)])

    log(f"运行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_DIR))
    if result.returncode != 0:
        log(f"自动触达异常（退出码 {result.returncode}）")
        return False

    log("自动触达完成!")
    return True


def print_summary():
    """打印今日汇总"""
    log("========== 今日汇总 ==========")

    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = progress.get("daily_counts", {}).get(today, 0)
        processed = progress.get("processed", {})
        total = len(processed)

        today_results = [
            v for v in processed.values()
            if v.get("time", "").startswith(today)
        ]
        followed = sum(1 for v in today_results if v["result"]["follow"] == "followed")
        messaged = sum(1 for v in today_results if v["result"]["message"] == "sent")
        commented = sum(1 for v in today_results if v["result"]["message"] == "commented")

        log(f"今日处理: {today_count} 人")
        log(f"新关注: {followed}, 私信: {messaged}, 评论: {commented}")
        log(f"累计已处理: {total} 人")
    else:
        log("暂无自动触达记录")

    if TARGETS_FILE.exists():
        with open(TARGETS_FILE, "r", encoding="utf-8") as f:
            targets = json.load(f)
        processed_ids = set()
        if PROGRESS_FILE.exists():
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                progress = json.load(f)
            processed_ids = set(progress.get("processed", {}).keys())
        pending = sum(1 for t in targets if t["user_id"] not in processed_ids)
        log(f"目标池总计: {len(targets)} 人, 剩余待处理: {pending} 人")


def main():
    parser = argparse.ArgumentParser(description="每日一键运行：同步名单 + 自动触达")
    parser.add_argument("--skip-sync", action="store_true", help="跳过同步网站名单")
    parser.add_argument("--skip-auto", action="store_true", help="只同步名单，不跑自动触达")
    parser.add_argument("--test", type=int, default=None, help="自动触达测试模式，只处理前 N 个人")
    parser.add_argument("--pipeline", type=str, default=None, metavar="SEED_FILE",
                        help="额外运行 pipeline 用种子账号爬新人（如 --pipeline seeds.txt）")
    args = parser.parse_args()

    log("====================================")
    log("    即刻自动触达 — 每日任务")
    log("====================================")
    log(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()

    # 第 1 步：同步网站名单
    if not args.skip_sync:
        sync_targets_from_site()
        print()

    # 可选：跑 pipeline 爬新人
    if args.pipeline:
        run_name = datetime.now().strftime("daily_%Y%m%d")
        run_pipeline(args.pipeline, run_name)
        print()

    # 第 2 步：自动触达
    if not args.skip_auto:
        run_auto(test_count=args.test)
        print()

    # 汇总
    print_summary()
    log("今日任务结束!")


if __name__ == "__main__":
    main()
