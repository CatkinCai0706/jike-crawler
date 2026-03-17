#!/usr/bin/env python3
"""
run_daily.py — 每日一键运行：爬人 + 自动关注/私信/评论

用法:
  python3 run_daily.py --seed-file seeds.txt
  python3 run_daily.py --seed-file seeds.txt --skip-crawl    # 跳过爬人，只跑自动触达
  python3 run_daily.py --seed-file seeds.txt --skip-auto     # 只爬人，不跑自动触达
  python3 run_daily.py --seed-file seeds.txt --test 3        # 自动触达只处理前 3 个人
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def run_pipeline(seed_file: str, run_name: str) -> bool:
    """运行爬人 pipeline"""
    log("========== 第 1 步：爬取技术人员 ==========")
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

    # 检查是否生成了 auto_targets.json
    targets_file = PROJECT_DIR / "auto_targets.json"
    if targets_file.exists():
        with open(targets_file, "r", encoding="utf-8") as f:
            targets = json.load(f)
        log(f"已生成 {len(targets)} 个目标用户")
    else:
        log("未生成 auto_targets.json，可能没有找到符合条件的技术人员")
        return False

    return True


def run_auto(test_count: int | None = None) -> bool:
    """运行自动关注/私信/评论"""
    log("========== 第 2 步：自动关注/私信/评论 ==========")

    targets_file = PROJECT_DIR / "auto_targets.json"
    if not targets_file.exists():
        log("auto_targets.json 不存在，跳过自动触达")
        return False

    with open(targets_file, "r", encoding="utf-8") as f:
        targets = json.load(f)
    if not targets:
        log("目标用户列表为空，跳过")
        return False

    log(f"目标用户: {len(targets)} 个")

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

    # 读取自动触达进度
    progress_file = PROJECT_DIR / "auto_progress.json"
    if progress_file.exists():
        with open(progress_file, "r", encoding="utf-8") as f:
            progress = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = progress.get("daily_counts", {}).get(today, 0)
        processed = progress.get("processed", {})
        total = len(processed)

        # 统计今日结果
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

    # 读取目标列表
    targets_file = PROJECT_DIR / "auto_targets.json"
    if targets_file.exists():
        with open(targets_file, "r", encoding="utf-8") as f:
            targets = json.load(f)
        log(f"目标池剩余: {len(targets)} 人")


def main():
    parser = argparse.ArgumentParser(description="每日一键运行：爬人 + 自动触达")
    parser.add_argument("--seed-file", default="seeds.txt", help="种子账号文件（默认 seeds.txt）")
    parser.add_argument("--run-name", default=None, help="本次运行名称（默认按日期生成）")
    parser.add_argument("--skip-crawl", action="store_true", help="跳过爬人，只跑自动触达")
    parser.add_argument("--skip-auto", action="store_true", help="只爬人，不跑自动触达")
    parser.add_argument("--test", type=int, default=None, help="自动触达测试模式，只处理前 N 个人")
    args = parser.parse_args()

    run_name = args.run_name or datetime.now().strftime("daily_%Y%m%d")

    log("====================================")
    log("    即刻技术人挖掘 + 自动触达")
    log("====================================")
    log(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log(f"种子文件: {args.seed_file}")
    log(f"运行名称: {run_name}")
    print()

    # 第 1 步：爬人
    if not args.skip_crawl:
        crawl_ok = run_pipeline(args.seed_file, run_name)
        if not crawl_ok and not args.skip_auto:
            log("爬人未成功，但仍尝试用已有的 auto_targets.json 跑自动触达")
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
