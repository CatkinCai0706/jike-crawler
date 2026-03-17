#!/usr/bin/env python3
"""
convert_pipeline_results.py — 把 pipeline 的 analysis.json 转成 jike_auto.py 需要的用户列表

用法:
  python3 convert_pipeline_results.py --run-dir runs/demo
  python3 convert_pipeline_results.py --run-dir runs/demo --category all
  python3 convert_pipeline_results.py --run-dir runs/demo --category confirmed_ai

类别说明:
  all              — 所有识别出的技术人员（默认）
  confirmed_dev    — 确定是开发人员
  probable_dev     — 高概率开发人员
  confirmed_ai     — 确定是 AI 技术的人
  probable_ai      — 高概率 AI 技术人
  graph            — 技术关系扩散候选人
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PROJECT_DIR / "auto_targets.json"


def load_analysis(run_dir: Path) -> dict:
    path = run_dir / "analysis.json"
    if not path.exists():
        print(f"找不到 {path}，请先运行 jike_pipeline.py")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_targets(analysis: dict, category: str) -> list[dict]:
    """从 analysis 中提取目标用户列表"""
    category_map = {
        "confirmed_dev": "confirmedDevelopers",
        "probable_dev": "probableDevelopers",
        "confirmed_ai": "confirmedAiTech",
        "probable_ai": "probableAiTech",
        "graph": "knownTechGraphCandidates",
    }

    if category == "all":
        # 合并所有类别，按 confidenceScore 排序，去重
        seen = set()
        all_records = []
        for key in category_map.values():
            for record in analysis.get(key, []):
                uid = record["id"]
                if uid not in seen:
                    seen.add(uid)
                    all_records.append(record)
        all_records.sort(key=lambda r: -r.get("confidenceScore", 0))
    else:
        key = category_map.get(category)
        if not key:
            print(f"未知类别: {category}")
            print(f"可选: {', '.join(['all'] + list(category_map.keys()))}")
            sys.exit(1)
        all_records = analysis.get(key, [])

    # 转成 jike_auto.py 需要的格式
    targets = []
    for record in all_records:
        targets.append({
            "user_id": record["id"],
            "username": record.get("screenName", ""),
            "intro": record.get("briefIntro", ""),
            "confidence_score": record.get("confidenceScore", 0),
            "reasons": record.get("reasons", []),
            "link": record.get("link", ""),
        })

    return targets


def main():
    parser = argparse.ArgumentParser(description="把 pipeline 分析结果转成自动操作的用户列表")
    parser.add_argument("--run-dir", required=True, help="pipeline 运行目录，如 runs/demo")
    parser.add_argument("--category", default="all",
                        help="要提取的类别: all, confirmed_dev, probable_dev, confirmed_ai, probable_ai, graph")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出文件路径")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    analysis = load_analysis(run_dir)
    targets = extract_targets(analysis, args.category)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(targets, f, ensure_ascii=False, indent=2)

    print(f"已生成 {len(targets)} 个目标用户 -> {args.output}")


if __name__ == "__main__":
    main()
