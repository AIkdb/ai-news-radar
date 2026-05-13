---
name: ai-news-radar
description: "伯乐Skill / AI News Radar 情报系统。触发条件：用户提到「AI资讯」、「AI日报」、「AI情报」、「AI更新雷达」、「伯乐Skill」时加载。功能：抓取AI行业情报、自动整理为Obsidian日报、监控信源健康状态、30分钟自动同步。"
---

# 伯乐Skill — AI News Radar 情报系统

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                  双层信源结构                            │
│  Layer 1 一手权威源    Layer 2 聚合广度源               │
│  OpenAI/HF/GitHub等     36kr/机器之心/HN等              │
│         ↘                   ↙                          │
│      官方RSS/Atom        RSS聚合                        │
└──────────────────────────┬────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│     GitHub Actions (每30分钟)                           │
│  update_news.py → latest-24h.json + waytoagi-7d.json   │
│         ↘                   ↙                          │
│  artifact上传    (Fine-Grained PAT 无需写权限)          │
└──────────────────────────┬────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│     Hermes CronJob (每30分钟)                           │
│  news_to_obsidian.py → AI资讯日报-YYYY-MM-DD.md        │
│         ↘                   ↙                          │
│  转换+去重(65%)+霖德分级(5/4/3星)                    │
└──────────────────────────┬────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│     Obsidian NEWOB 知识库                               │
│  AI与教育资讯日报/AI资讯日报-YYYY-MM-DD.md             │
│  (186KB/天，含5星+4星+3星+行业要闻+信源状态)          │
└─────────────────────────────────────────────────────────┘
```

## 部署位置

| 组件 | 路径 |
|------|------|
| 仓库 | `~/workspace/ai-news-radar/` |
| 数据 | `~/workspace/ai-news-radar/data/` |
| OPML信源 | `~/workspace/ai-news-radar/feeds/follow.opml` |
| 抓取脚本 | `~/workspace/ai-news-radar/scripts/update_news.py` |
| 转换脚本 | `~/workspace/ai-news-radar/scripts/news_to_obsidian.py` |
| GitHub仓库 | https://github.com/AIkdb/ai-news-radar |

## 一键运行指令

### 手动抓取 + 同步到 NEWOB
```bash
cd /Users/hong/workspace/ai-news-radar && \
  /opt/homebrew/bin/python3.13 scripts/update_news.py \
    --output-dir data \
    --window-hours 24 \
    --archive-days 21 \
    --rss-opml feeds/follow.opml \
    --rss-max-feeds 50 && \
  /opt/homebrew/bin/python3.13 scripts/news_to_obsidian.py \
    --data-dir data \
    --output-dir ~/Desktop/NEWOB/AI与教育资讯日报
```

### 仅抓取（不写入）
```bash
/opt/homebrew/bin/python3.13 /Users/hong/workspace/ai-news-radar/scripts/update_news.py \
  --output-dir /Users/hong/workspace/ai-news-radar/data \
  --window-hours 24 \
  --rss-opml /Users/hong/workspace/ai-news-radar/feeds/follow.opml \
  --rss-max-feeds 50
```

### 仅转换已有JSON
```bash
/opt/homebrew/bin/python3.13 /Users/hong/workspace/ai-news-radar/scripts/news_to_obsidian.py \
  --data-dir /Users/hong/workspace/ai-news-radar/data \
  --output-dir ~/Desktop/NEWOB/AI与教育资讯日报 \
  --date 2026-05-13
```

### 触发 GitHub Actions（云端抓取）
```bash
gh workflow run update-news.yml --repo AIkdb/ai-news-radar
```

## 双层信源结构（28个RSS源）

### Layer 1：一手权威源（官方/研究）
| 信源 | 类型 | 特点 |
|------|------|------|
| OpenAI News/Blog | RSS | 官方模型发布 |
| Google DeepMind | RSS | 官方研究进展 |
| Hugging Face Blog | RSS | 开源生态 |
| GitHub AI Blog | RSS | 开发者工具 |
| Microsoft AI Blog | RSS | 企业AI |
| Anthropic News | RSS | Claude相关 |
| arXiv cs.AI/CL/LG/CV | RSS | 学术论文 |
| Simon Willison | RSS | 实战洞见 |
| 宝玉 blog | RSS | 中文技术观察 |

### Layer 2：聚合广度源
| 信源 | 类型 | 特点 |
|------|------|------|
| 36kr | RSS | 中文科技创投 |
| 机器之心 | RSS | 中文AI技术 |
| 量子位 | RSS | 中文AI媒体 |
| AIbase | RSS | AI产品库 |
| Hacker News | RSS | 全球开发者热点 |
| Techmeme | RSS | 美国科技要闻 |
| The Verge AI | RSS | AI产品报道 |
| Wired AI | RSS | 深度分析 |

## 自动处理规则

### 7天内容去重
- 标题相似度 > 65%（Jaccard词集合系数）视为重复
- URL完全相同直接去重
- 过滤转发/引用噪音（"RT @"、"转发"、"via @"等）

### 霖德维度分级
| 星级 | 标准 | 内容占比 |
|------|------|---------|
| ⭐⭐⭐⭐⭐（5星） | 直接教育/育儿/儿童场景 | ~5% |
| ⭐⭐⭐⭐（4星） | AI模型/产品重大动态 | ~30% |
| ⭐⭐⭐（3星） | AI行业重要动态 | ~20% |
| ⭐⭐以下 | 一般科技要闻 | ~45% |

### 输出格式
- Frontmatter：`created`, `tags: [AI资讯, 日报, 霖德, YYYY-MM-DD]`
- 摘要：总条数 + 3星以上高关联数
- 正文：5星 → 4星 → 3星 → 行业要闻 → WaytoAGI精选 → 信源状态
- Footer：数据来源说明 + 原文溯源链接

## CronJob 配置

| 项目 | 值 |
|------|------|
| Job ID | `d26539106c8a` |
| 名称 | AI News Radar 情报同步 |
| 周期 | 每30分钟（`:00` 和 `:30`） |
| 下次执行 | 2026-05-13 11:30 CST |
| 状态 | 启用 |

## 常见问题

**Q: 生成的日报在哪里？**
A: `/Users/hong/Desktop/NEWOB/AI与教育资讯日报/AI资讯日报-YYYY-MM-DD.md`

**Q: 如何查看当前信源健康状态？**
A: 查看 `data/source-status.json` 或直接问"信源状态"

**Q: 如何添加新的RSS信源？**
A: 编辑 `feeds/follow.opml`，按照现有格式添加 `<outline>` 节点，然后手动运行一次脚本

**Q: GitHub Actions 有什么用？**
A: 云端备份抓取结果（上传为 artifact），每次运行后约5分钟可在 Actions 页面下载 latest-24h.json

**Q: 65%相似度去重严格吗？**
A: 用的是 Jaccard 词集合系数（词袋模型），中英文标题都能处理。同一事件的不同媒体报道会被视为不同条目（URL不同），不会误杀
