#!/usr/bin/env python3
"""
news_to_obsidian.py
将 ai-news-radar 的 JSON 数据转换为 Obsidian Markdown 日报格式。

用法:
    python3 scripts/news_to_obsidian.py \
        --data-dir data \
        --output-dir ~/Desktop/NEWOB/AI与教育资讯日报 \
        --date 2026-05-13

输出:
    AI资讯日报-YYYY-MM-DD.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import textwrap
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_parse(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(s)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalize_url(url: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
    try:
        parsed = urlparse(url.strip())
        if not parsed.scheme:
            return url.strip()
        query = []
        for k, v in parse_qsl(parsed.query, keep_blank_values=True):
            lk = k.lower()
            if lk.startswith("utm_"):
                continue
            if lk in {"ref", "spm", "fbclid", "gclid", "igshid", "mkt_tok", "mc_cid", "mc_eid"}:
                continue
            query.append((k, v))
        parsed = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            fragment="",
            query=urlencode(query, doseq=True),
        )
        return urlunparse(parsed).rstrip("/")
    except Exception:
        return url.strip()


def host_of_url(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def display_host(url: str) -> str:
    h = host_of_url(url)
    if h.startswith("www."):
        h = h[4:]
    return h


def content_fingerprint(title: str, url: str) -> str:
    """内容指纹：标题去噪音+URL归一化，用于去重比较"""
    t = re.sub(r"[\[\]【】()（）]", "", (title or "").strip().lower())
    t = re.sub(r"\s+", "", t)
    u = normalize_url(url)
    return f"{t}||{u}"


def title_similarity(t1: str, t2: str) -> float:
    """简单词集合相似度（JI系数）"""
    if not t1 or not t2:
        return 0.0
    s1 = set(re.findall(r"[\w]+", t1.lower()))
    s2 = set(re.findall(r"[\w]+", t2.lower()))
    if not s1 or not s2:
        return 0.0
    inter = len(s1 & s2)
    union = len(s1 | s2)
    return inter / union if union else 0.0


def dedupe_items(items: list[dict], threshold: float = 0.65) -> list[dict]:
    """
    内容去重：两篇文章标题相似度 > threshold 视为重复，保留第一条。
    同时过滤转发/引用类噪音（如 "X上有人说..."）。
    """
    # 先过滤噪音
    filtered = []
    for item in items:
        title = item.get("title_original") or item.get("title") or ""
        url = item.get("url") or ""
        # 过滤明显转发/引用模式
        lower_title = title.lower()
        if any(kw in lower_title for kw in [
            "retweeted", "转发", "rt @", "via @", "来源：",
            "说：\"", "表示：\"", "指出：\"", "报道：\"",
        ]):
            # 保留但不作为主条目
            item["_is_mention"] = True
        filtered.append(item)

    results: list[dict] = []
    seen_fp: list[str] = []

    for item in filtered:
        title = item.get("title_original") or item.get("title") or ""
        url = item.get("url") or ""

        is_dup = False
        for prev in results:
            prev_title = prev.get("title_original") or prev.get("title") or ""
            prev_url = prev.get("url") or ""
            sim = title_similarity(title, prev_title)
            # URL相同 或 相似度>阈值 → 重复
            if normalize_url(url) == normalize_url(prev_url) or sim > threshold:
                is_dup = True
                break

        if not is_dup:
            results.append(item)
            seen_fp.append(content_fingerprint(title, url))

    return results


def classify_item(item: dict) -> tuple[int, str]:
    """
    星级分类（霖德成长手册维度）:
    5星: 直接服务AI+教育/家庭教育/育儿场景
    4星: AI模型/产品动态，与教育/儿童高度相关
    3星: AI行业重要动态，与霖德有一定关联
    2星: AI行业要闻，低关联
    1星: 其他科技要闻
    """
    title = (item.get("title_original") or item.get("title") or "").lower()
    source = (item.get("source") or "").lower()
    url = (item.get("url") or "").lower()
    site_id = item.get("site_id", "").lower()

    score = 2  # 默认：AI行业要闻

    # 直接教育/育儿场景
    education_kw = [
        "教育", "edu", "learning", "student", "teacher", "school",
        "parent", "child", "kids", "children", "family", "parenting",
        "家庭教育", "校园", "课堂", "教材", "课程", "学习",
        "霖德", "成长", "儿童", "未成年", "早教", "K12",
    ]
    if any(kw in title for kw in education_kw):
        return 5, "direct_education"

    # 模型/产品重大动态
    model_kw = [
        "gpt", "claude", "gemini", "llama", "deepseek", "mistral",
        "o1", "o3", "o4", "grok", "qwen", "kimi", "豆包", "通义",
        "chatgpt", "chat bot", "anthropic", "openai", "google deepmind",
        "hugging face", "模型", "大模型", "多模态", "reasoning",
    ]
    if any(kw in f"{title} {source}" for kw in model_kw):
        score = max(score, 4)

    # AI+教育方向
    ai_edu_kw = ["ai", "人工智能", "机器学习", "生成式", "AGI", "AIGC", "LLM"]
    if all(kw in f"{title} {source}" for kw in ai_edu_kw[:2]):
        score = max(score, 3)

    # 硬件/芯片/基础设施
    infra_kw = ["nvidia", "gpu", "tpu", "芯片", "算力", "数据中心", "server"]
    if any(kw in f"{title} {source}" for kw in infra_kw):
        score = max(score, 3)

    return score, ""


def format_beijing_time(dt: datetime | None) -> str:
    if not dt:
        return "未知时间"
    from zoneinfo import ZoneInfo
    SH_TZ = ZoneInfo("Asia/Shanghai")
    dt_sh = dt.astimezone(SH_TZ)
    return dt_sh.strftime("%Y年%m月%d日 %H:%M")


def build_frontmatter(dt: date, total: int, high: int, medium: int) -> str:
    date_str = dt.strftime("%Y-%m-%d")
    created = dt.strftime("%Y-%m-%d 08:00:00")
    tags = f"[AI资讯, 日报, 霖德, {date_str}]"
    lines = [
        "---",
        f"created: {created}",
        f"tags: {tags}",
        f"source: ai-news-radar (GitHub Actions) + Hermes Agent 自动整理",
        "---",
    ]
    return "\n".join(lines)


def build_summary_block(total: int, high: int, medium: int, report_date: date) -> str:
    blocks = [
        "",
        f"> 今日共收录 AI 动态 **{total}** 条，",
        f"> 其中与霖德相关（3星以上）{high + medium} 条。",
        f"> 高关联（4星以上）：{high} 条 | 中关联（3星）：{medium} 条",
        "",
    ]
    return "\n".join(blocks)


def build_star_section(items: list[dict], min_stars: int, label: str, emoji: str) -> str:
    filtered = [it for it in items if it.get("_stars", 0) >= min_stars]
    if not filtered:
        return ""

    lines = [f"## {emoji} {label}\n"]
    for item in filtered:
        title = item.get("title_bilingual") or item.get("title") or "无标题"
        url = item.get("url") or "#"
        source = item.get("source") or display_host(url)
        site_name = item.get("site_name") or source
        published = item.get("published_at") or item.get("first_seen_at") or ""
        dt = iso_parse(published)
        pub_str = format_beijing_time(dt) if dt else "未知"
        ai_label = item.get("ai_label", "")

        lines.append(f"**[{title}]({url})**")
        lines.append(f"- **发布时间**：北京时间 {pub_str}")
        lines.append(f"- **分类**：{ai_label or '一般'}")
        lines.append(f"- **数据来源**：{site_name}")
        lines.append("")

    return "\n".join(lines) + "\n"


def build_industry_news(items: list[dict]) -> str:
    """构建「今日AI行业要闻」列表（1-2星）"""
    filtered = [it for it in items if it.get("_stars", 0) <= 2]
    if not filtered:
        return ""

    # 随机选20条
    selected = random.sample(filtered, min(20, len(filtered)))
    lines = [
        "## 三、今日 AI 行业要闻\n",
        "*（以下为随机筛选的今日重要动态，星章越少关联度越低）*\n",
    ]
    for item in selected:
        title = item.get("title_bilingual") or item.get("title") or "无标题"
        url = item.get("url") or "#"
        stars = item.get("_stars", 0)
        lines.append(f"- [{'⭐' * stars} {title}]({url})")

    return "\n".join(lines) + "\n"


def build_waytoagi_section(waytoagi_data: dict, report_date: date) -> str:
    updates = waytoagi_data.get("updates_7d", [])
    if not updates:
        return ""

    start = report_date - timedelta(days=6)
    recent = [u for u in updates if start <= date.fromisoformat(str(u.get("date", "1970-01-01"))) <= report_date]
    if not recent:
        return ""

    lines = [
        "## 四、WaytoAGI 近7日精选更新\n",
        "*（来源：WaytoAGI 知识库每日精选）*\n",
    ]
    for u in recent[:15]:
        title = u.get("title", "")[:80]
        url = u.get("url", "#")
        d = u.get("date", "")
        lines.append(f"- **{d}**：[{title}]({url})")

    return "\n".join(lines) + "\n"


def build_source_status_section(status_data: dict) -> str:
    """信源健康状态"""
    sites = status_data.get("sites", [])
    ok = sum(1 for s in sites if s.get("ok"))
    total = len(sites)

    lines = [
        "## 五、本次采集信源状态\n",
        f"> 信源总数：{total} | 正常：{ok} | 失败：{total - ok}\n",
    ]
    # 按item_count排
    top = sorted(sites, key=lambda x: x.get("item_count", 0), reverse=True)[:8]
    for s in top:
        ok_mark = "✅" if s.get("ok") else "❌"
        sid = s.get("site_id", "")
        sname = s.get("site_name", sid)
        cnt = s.get("item_count", 0)
        err = s.get("error", "")
        err_str = f" ({err})" if err else ""
        lines.append(f"- {ok_mark} {sname}：{cnt}条{err_str}")

    return "\n".join(lines) + "\n"


def build_footer() -> str:
    return (
        "\n---\n\n"
        "*由 ai-news-radar (GitHub Actions) + Hermes Agent 自动整理*\n"
        "*数据来源：OpenAI / Google DeepMind / Hugging Face / GitHub / TechURLs / "
        "Buzzing.cc / TopHub / WaytoAGI 等一手权威源*\n"
    )


def generate_markdown(
    items: list[dict],
    waytoagi_data: dict,
    status_data: dict,
    report_date: date,
) -> str:
    # 附加星级和分类
    for item in items:
        stars, _ = classify_item(item)
        item["_stars"] = stars

    # 去重
    items = dedupe_items(items, threshold=0.65)

    # 重新计算星级（去重后）
    for item in items:
        stars, _ = classify_item(item)
        item["_stars"] = stars

    # 排序：星级降序，时间降序
    def sort_key(it):
        stars = it.get("_stars", 0)
        dt = iso_parse(it.get("published_at") or it.get("first_seen_at"))
        return (stars, dt or datetime.min.replace(tzinfo=UTC))

    items.sort(key=sort_key, reverse=True)

    total = len(items)
    high = sum(1 for it in items if it.get("_stars", 0) >= 4)
    medium = sum(1 for it in items if it.get("_stars", 0) == 3)

    # 组装
    parts: list[str] = []

    # Header
    date_str = report_date.strftime("%Y年%m月%d日")
    parts.append(f"# AI 与教育资讯日报 — {date_str}\n")

    # Frontmatter
    parts.append(build_frontmatter(report_date, total, high, medium))

    # Summary
    parts.append(build_summary_block(total, high, medium, report_date))

    # 5星
    parts.append(build_star_section(items, 5, "极度相关（5星）", "⭐⭐⭐⭐⭐"))

    # 4星
    parts.append(build_star_section(items, 4, "高度相关（4星）", "⭐⭐⭐⭐"))

    # 3星
    parts.append(build_star_section(items, 3, "中度相关（3星）", "⭐⭐⭐"))

    # 行业要闻
    parts.append(build_industry_news(items))

    # WaytoAGI
    parts.append(build_waytoagi_section(waytoagi_data, report_date))

    # 信源状态
    parts.append(build_source_status_section(status_data))

    # Footer
    parts.append(build_footer())

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Convert ai-news-radar JSON to Obsidian MD")
    parser.add_argument("--data-dir", default="data", help="Path to data/ directory")
    parser.add_argument("--output-dir", default="~/Desktop/NEWOB/AI与教育资讯日报", help="Obsidian output dir")
    parser.add_argument("--date", default="", help="Report date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--threshold", type=float, default=0.65, help="Dedupe similarity threshold")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if args.date:
        report_date = date.fromisoformat(args.date)
    else:
        report_date = datetime.now(UTC).date()

    # 加载数据
    latest = load_json(data_dir / "latest-24h.json")
    waytoagi = load_json(data_dir / "waytoagi-7d.json")
    status = load_json(data_dir / "source-status.json")

    # 取items（AI相关）
    raw_items = latest.get("items", [])
    if not raw_items:
        raw_items = latest.get("items_ai", [])

    print(f"Loaded {len(raw_items)} AI items from latest-24h.json")
    print(f"Generated at: {latest.get('generated_at', 'unknown')}")

    # 生成Markdown
    md = generate_markdown(raw_items, waytoagi, status, report_date)

    # 输出文件
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"AI资讯日报-{report_date.isoformat()}.md"
    output_path = output_dir / filename

    # 避免重复写入（内容完全相同跳过）
    if output_path.exists():
        existing = output_path.read_text(encoding="utf-8")
        if existing.strip() == md.strip():
            print(f"[SKIP] {output_path} 内容相同，跳过")
            return 0
        # 备份旧版
        backup = output_dir / f"AI资讯日报-{report_date.isoformat()}-bak.md"
        backup.write_text(existing, encoding="utf-8")
        print(f"[BACKUP] {backup}")

    output_path.write_text(md, encoding="utf-8")
    print(f"[WROTE] {output_path} ({len(md)} chars, {len(raw_items)} items)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
