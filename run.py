#!/usr/bin/env python3
"""AI 前沿日报采集入口:抓取 → 去重 → 分类评分 → 入库 → 生成静态站点。

用法:python run.py
"""
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import yaml

from collector.classify import classify, score_importance
from collector.llm import process_pending
from collector.dedup import title_hash, url_hash
from collector.fetch import fetch_all
from collector.render import render_site
from collector.store import Store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("aidaily")


def main() -> int:
    sources = yaml.safe_load(
        (BASE_DIR / "config" / "sources.yaml").read_text(encoding="utf-8")
    )["sources"]
    store = Store(BASE_DIR / "data" / "aidaily.db")

    log.info("开始抓取 %d 个源 …", len(sources))
    raw_items, errors = fetch_all(sources)

    known_urls, known_titles = store.existing_hashes()
    now_iso = datetime.now(timezone.utc).isoformat()
    today = datetime.now().astimezone().strftime("%Y-%m-%d")

    added = 0
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for raw in raw_items:
        uh = url_hash(raw["url"])
        th = title_hash(raw["title"])
        # 批内去重 + 对库内历史去重
        if {uh, th} & (known_urls | known_titles | seen_urls | seen_titles):
            continue
        item = {
            **raw,
            "fetched_at": now_iso,
            "first_seen_date": today,
            "category": classify(raw["title"], raw["summary"]),
            "importance": score_importance(raw["title"], raw["summary"],
                                           raw["source_key"]),
            "url_hash": uh,
            "title_hash": th,
        }
        if store.insert_item(item):
            added += 1
            seen_urls.add(uh)
            seen_titles.add(th)

    log.info("抓到 %d 条,新增 %d 条,失败 %d 个源", len(raw_items), added, len(errors))
    for key, err in errors.items():
        log.warning("  源 %s 失败:%s", key, err)

    process_pending(store)

    render_site(store, BASE_DIR / "site", BASE_DIR / "templates")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
