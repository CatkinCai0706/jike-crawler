# 即刻技术人挖掘 MVP

这个目录现在不是单纯的“抓一个人关注列表”的调试脚本了，而是一条完整的 MVP 流程：

- 输入 20 个即刻种子账号链接
- 批量抓取种子账号的关注列表、被关注列表
- 从一跳关系里筛出优先候选人，再抓主页简介、动态、评论和评论人 ID
- 结合内容信号和关系信号，输出三类名单：
  - 确定是 AI 技术的人
  - 高概率 AI 技术人
  - 关系型候选人
- 对命中过滤规则的人打本地标签，下次再遇到直接跳过
- 对已经处理过的人复用本地缓存，默认不重复爬

## 目录说明

- `jike_pipeline.py`
  - 主入口。负责批量采集、断点续跑、分析、出报告。
- `seeds.example.txt`
  - 种子账号文件示例。
- `runs/<run_name>/`
  - 每次运行的结果目录。
  - `raw/seed_relations.json`：种子账号关注/被关注原始数据
  - `raw/candidate_index.json`：一跳候选池
  - `raw/candidate_details.json`：候选人的主页、动态、评论
  - `raw/anchor_followers.json`：已确认 AI 技术人的 follower 扩展
  - `raw/filtered_users.json`：本轮命中过滤规则的用户
  - `analysis.json`：结构化分析结果
  - `report.md`：面向业务查看的汇总报告
- `state/`
  - 本地缓存和标签库。
  - `user_registry.json`：用户标签、处理状态
  - `relations/*.json`：关系缓存
  - `details/*.json`：内容缓存

## 运行方式

1. 安装依赖

```bash
cd /Users/xiaokang/my_project/jike-crawler
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

2. 准备种子文件

- 新建一个文本文件，每行一个即刻主页链接。
- 建议先放 20 个你确认偏技术的种子账号。

3. 运行完整流程

```bash
python3 jike_pipeline.py full --seed-file seeds.txt --run-name demo
```

默认策略：

- 每个种子账号最多抓 `500` 个关系人
- 关系池里最多深入抓 `250` 个候选人内容
- 每个候选人最多抓 `12` 条动态
- 每条动态最多抓 `20` 条评论
- 会对“确定是 AI 技术的人”再做一轮 follower 扩展
- 先应用两层过滤，再决定是否深入爬取

过滤规则：

- 名字、简介、签名命中这些词，直接打 `ROLE_KEYWORD_FILTERED` 标签并跳过深爬：
  - `产品经理`
  - `投资人`
  - `记者`
  - `自媒体`
  - `投资经理`
  - `天使投资`
  - `基金`
  - `vc`
- 如果发帖内容为空，且被关注数 `< 10`，打 `LOW_ACTIVITY_FILTERED` 标签并跳过深爬
- 这两类标签会存进本地缓存，下次遇到同一个人默认直接跳过

如果你要更激进地拉全量，可以把限制放开：

```bash
python3 jike_pipeline.py full \
  --seed-file seeds.txt \
  --run-name full-run \
  --relation-limit 0 \
  --candidate-limit 0 \
  --posts-limit 20 \
  --comments-limit 50
```

其中：

- `--relation-limit 0` 表示抓某个种子账号的全量关注/被关注
- `--candidate-limit 0` 表示对候选池全量抓内容
- `--posts-limit 0` 表示抓该人的全量动态
- `--comments-limit -1` 表示抓单条动态的全量评论

## 二次分析

如果原始数据已经在 `runs/<run_name>/` 里，只想重跑分析：

```bash
python3 jike_pipeline.py analyze --run-dir runs/demo
```

## 现在这版的判断逻辑

这版先用规则分析，不依赖外部大模型，目的是先把高概率名单稳定做出来。

主要看四类信号：

- 简介里是否出现 AI / 技术角色关键词
- 最近动态里是否持续出现 AI / 工程 / 开源 / 模型相关内容
- 是否被多个种子账号共同关注或共同反向关注
- 是否关注了多位已确认的 AI 技术人

## 建议使用方式

- 第一次先用默认参数跑，先验证名单质量
- 如果结果质量对了，再把 `relation-limit` 和 `candidate-limit` 放大
- 结果不要直接当最终结论，先看 `report.md` 里的理由做一次人工复核

## 风险

- 即刻接口和风控可能变化，脚本依赖登录态和当前接口可用
- 全量抓取的成本会迅速变高，建议优先用“种子一跳 + 关系扩展”
- 规则分析可以先出结果，但最终准确率还可以继续用大模型做二次判断
