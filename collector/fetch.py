"""RSS/Atom 抓取:把各源解析成统一的条目结构。

传输层:优先 curl(在本机受限/代理劫持的网络下比 Python TLS 稳定),
失败时退回 httpx;GitHub Actions 上两条路都可用。
"""
import html as html_mod
import logging
import re
import subprocess
from calendar import timegm
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

log = logging.getLogger(__name__)

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 ai-daily/0.1"
)


def clean_text(text: str, limit: int = 240) -> str:
    """去掉 HTML 标签和多余空白,截断到 limit 字符。"""
    cleaned = WS_RE.sub(" ", html_mod.unescape(TAG_RE.sub(" ", text or ""))).strip()
    if len(cleaned) > limit:
        return cleaned[:limit].rsplit(" ", 1)[0].rstrip() + "…"
    return cleaned


def to_utc_iso(struct) -> str | None:
    """feedparser 的 struct_time(UTC)→ ISO 8601 字符串。"""
    if not struct:
        return None
    return datetime.fromtimestamp(timegm(struct), tz=timezone.utc).isoformat()


def _http_get(url: str, transport: str = "curl") -> bytes:
    """按指定传输层抓取 URL 内容,失败抛异常。"""
    if transport == "curl":
        try:
            proc = subprocess.run(
                ["curl", "-sL", "--max-time", "30", "-A", UA, url],
                capture_output=True,
                timeout=40,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"curl 不可用:{exc}") from exc
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
        raise RuntimeError(f"curl 退出码 {proc.returncode}")

    resp = httpx.get(url, headers={"User-Agent": UA}, timeout=30.0,
                     follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def _within_age(entry, max_age_days: int) -> bool:
    """无日期的条目保留;有日期但太旧的丢弃(避免归档型 RSS 刷屏)。"""
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    if not st:
        return True
    pub = datetime.fromtimestamp(timegm(st), tz=timezone.utc)
    return datetime.now(timezone.utc) - pub <= timedelta(days=max_age_days)


def fetch_source(client: httpx.Client, source: dict,
                 max_age_days: int = 7) -> tuple[list[dict], str | None]:
    """抓取单个源;失败时返回 ([], 错误信息),不抛出,不影响其他源。

    curl 解析不出条目时(如拿到反爬 HTML 页)自动用 httpx 重试一次。
    """
    del client  # 兼容旧签名;传输层已下沉到 _http_get
    last_err: str | None = None
    for transport in ("curl", "httpx"):
        try:
            content = _http_get(source["url"], transport=transport)
        except Exception as exc:
            last_err = str(exc) or exc.__class__.__name__
            continue
        parsed = feedparser.parse(content)
        if parsed.bozo and not parsed.entries:
            last_err = f"XML 解析失败:{parsed.get('bozo_exception')}"
            continue
        items = []
        for entry in parsed.entries:
            if not _within_age(entry, max_age_days):
                continue
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue
            items.append({
                "source_key": source["key"],
                "source_name": source["name"],
                "title": clean_text(title, 300),
                "url": link,
                "summary": clean_text(entry.get("summary") or ""),
                "published_at": to_utc_iso(
                    entry.get("published_parsed") or entry.get("updated_parsed")
                ),
            })
        return items, None
    return [], last_err or "未知错误"


def fetch_all(sources: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """顺序抓取全部源。返回 (全部条目, {源key: 错误信息})。"""
    all_items: list[dict] = []
    errors: dict[str, str] = {}
    with httpx.Client(follow_redirects=True) as client:
        for source in sources:
            items, err = fetch_source(client, source)
            if err:
                errors[source["key"]] = err
                log.warning("源 %s 抓取失败:%s", source["key"], err)
            else:
                log.info("源 %s 抓到 %d 条", source["key"], len(items))
            all_items.extend(items)
    return all_items, errors
