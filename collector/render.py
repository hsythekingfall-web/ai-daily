"""把数据库里的日报渲染成静态 HTML 站点。"""
import logging
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from collector.cluster import cluster_items

log = logging.getLogger(__name__)

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


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


def render_site(store, site_dir: Path, templates_dir: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["fmt_date"] = fmt_date
    env.filters["fmt_time"] = _fmt_time
    env.filters["dots"] = _dots

    day_tpl = env.get_template("day.html.j2")
    archive_tpl = env.get_template("archive.html.j2")

    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "days").mkdir(exist_ok=True)
    shutil.copyfile(templates_dir / "style.css", site_dir / "style.css")

    dates = store.dates()
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")

    if not dates:
        html = day_tpl.render(root=".", latest=True, date_str=None, fmt_date_str="",
                              total=0, top=[], groups=[], generated_at=generated_at)
        (site_dir / "index.html").write_text(html, encoding="utf-8")
        log.warning("数据库为空,已生成占位首页")
        return

    latest_date = dates[0]["first_seen_date"]
    for row in dates:
        date_str = row["first_seen_date"]
        items = [dict(r) for r in store.items_by_date(date_str)]
        clusters = cluster_items(items)

        # "今日必读"取事件(簇)的 lead;簇内其余来源跟随 lead 展示
        top_clusters = [c for c in clusters if c["lead"]["importance"] >= 4][:5]
        top_lead_ids = {c["lead"]["id"] for c in top_clusters}
        rest = [c for c in clusters if c["lead"]["id"] not in top_lead_ids]

        groups: dict[str, list[dict]] = {}
        for c in rest:
            groups.setdefault(c["lead"]["category"], []).append(c)
        ordered_groups = sorted(
            groups.items(),
            key=lambda kv: -max(x["lead"]["importance"] for x in kv[1]),
        )

        in_root = date_str == latest_date
        html = day_tpl.render(
            root="." if in_root else "..",
            latest=in_root,
            date_str=date_str,
            fmt_date_str=fmt_date(date_str),
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
    log.info("站点已生成:%s(共 %d 天)", site_dir, len(dates))
