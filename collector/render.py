"""把数据库里的日报渲染成静态 HTML 站点(设计规范见 DESIGN.md)。"""
import logging
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from collector.cluster import cluster_items

log = logging.getLogger(__name__)

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 分类 → 马卡龙色签 class(DESIGN.md 第 2 节)
CAT_CLASS = {
    "大模型": "c-llm",
    "智能体": "c-agent",
    "多模态": "c-mm",
    "芯片与基础设施": "c-chip",
    "开源项目": "c-oss",
    "政策与行业": "c-policy",
    "研究前沿": "c-research",
    "行业动态": "c-misc",
}


def fmt_date(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return f"{d.year}年{d.month}月{d.day}日 · {WEEKDAYS[d.weekday()]}"


def _fmt_time(dt_iso):
    if not dt_iso:
        return ""
    try:
        return datetime.fromisoformat(dt_iso).astimezone().strftime("%H:%M")
    except ValueError:
        return ""


def _dots(n: int) -> str:
    return "●" * n + "○" * (5 - n)


def _short(text: str, n: int = 18) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1] + "…"


def render_site(store, site_dir: Path, templates_dir: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["fmt_date"] = fmt_date
    env.globals["catmap"] = CAT_CLASS
    env.filters["fmt_time"] = _fmt_time
    env.filters["dots"] = _dots

    day_tpl = env.get_template("day.html.j2")
    archive_tpl = env.get_template("archive.html.j2")

    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "days").mkdir(exist_ok=True)
    shutil.copyfile(templates_dir / "style.css", site_dir / "style.css")

    dates = store.dates()
    total_days = len(dates)
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")

    if not dates:
        html = day_tpl.render(root=".", latest=True, date_str=None, fmt_date_str="",
                              issue=0, stats=None, hero=None, total=0, top=[],
                              groups=[], generated_at=generated_at)
        (site_dir / "index.html").write_text(html, encoding="utf-8")
        log.warning("数据库为空,已生成占位首页")
        return

    latest_date = dates[0]["first_seen_date"]
    for i, row in enumerate(dates):
        date_str = row["first_seen_date"]
        items = [dict(r) for r in store.items_by_date(date_str)]
        clusters = cluster_items(items)

        top_clusters = [c for c in clusters if c["lead"]["importance"] >= 4][:6]
        if not top_clusters and clusters:
            top_clusters = clusters[:1]
        top_lead_ids = {c["lead"]["id"] for c in top_clusters}
        rest = [c for c in clusters if c["lead"]["id"] not in top_lead_ids]

        groups: dict[str, list[dict]] = {}
        for c in rest:
            groups.setdefault(c["lead"]["category"], []).append(c)
        ordered_groups = sorted(
            groups.items(),
            key=lambda kv: -max(x["lead"]["importance"] for x in kv[1]),
        )

        issue = total_days - i
        stats = {
            "sources": len({x["source_key"] for x in items}),
            "collected": len(items),
            "clusters": len(clusters),
        }

        hero = None
        if date_str == latest_date:
            leads = [c["lead"] for c in top_clusters][:3]
            headline = store.get_issue(date_str) or "、".join(
                _short(l.get("title_zh") or l["title"], 18) for l in leads
            )
            brief_digest = (leads[0].get("summary_zh") or leads[0]["summary"] or "")
            if len(brief_digest) > 110:
                brief_digest = brief_digest[:109] + "…"
            hero = {"issue": issue, "headline": headline,
                    "digest": brief_digest, "date": date_str}

        in_root = date_str == latest_date
        html = day_tpl.render(
            root="." if in_root else "..",
            latest=in_root,
            date_str=date_str,
            fmt_date_str=fmt_date(date_str),
            issue=issue,
            stats=stats,
            hero=hero,
            total=len(items),
            top=top_clusters,
            groups=ordered_groups,
            generated_at=generated_at,
        )
        (site_dir / "days" / f"{date_str}.html").write_text(html, encoding="utf-8")
        if in_root:
            (site_dir / "index.html").write_text(html, encoding="utf-8")

    (site_dir / "archive.html").write_text(
        archive_tpl.render(dates=dates), encoding="utf-8"
    )
    log.info("站点已生成:%s(共 %d 期)", site_dir, total_days)
