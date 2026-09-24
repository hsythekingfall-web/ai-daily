"""URL 与标题的归一化、哈希,用于跨源去重。"""
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

# 常见统计/追踪参数,归一化时剔除
_TRACKING_PREFIXES = ("utm_", "ref_", "mc_", "fbclid", "gclid", "si", "sh")


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    params = [
        p for p in parts.query.split("&")
        if p and not p.lower().startswith(_TRACKING_PREFIXES)
    ]
    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/") or "/",
        "&".join(params),
        "",
    ))


def normalize_title(title: str) -> str:
    return re.sub(r"[\W_]+", "", title, flags=re.UNICODE).lower()


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def title_hash(title: str) -> str:
    return hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()
