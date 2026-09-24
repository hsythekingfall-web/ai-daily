"""同一事件的多来源聚合。

用归一化标题的相似度判断两条资讯是否报道同一事件,
并查集把成对关系合并成簇。纯算法实现,不依赖外部 API;
后续可升级为 embedding / LLM 判断。
"""
import re
from difflib import SequenceMatcher

_WORD_RE = re.compile(r"[^\w\s]")

# 英文虚词:对判断"同一事件"没有区分度,反而稀释重叠率
_STOPWORDS = frozenset("""
the a an on of to in for with at by from as is are was were be been it its
this that and or but not after before over under up down out about into
than then so if when while has have had do does did will would can could
should may might must you your we our they their he she his her i me my
s t ll re ve don won
""".split())


def _tokens(title: str) -> list[str]:
    words = _WORD_RE.sub(" ", title.lower()).split()
    return [w for w in words if len(w) > 1 and w not in _STOPWORDS]


def _same_event(ta: list[str], tb: list[str]) -> bool:
    sa, sb = set(ta), set(tb)
    if not sa or not sb:
        return False
    inter = len(sa & sb)
    shorter = min(len(sa), len(sb))
    overlap = inter / shorter
    ratio = SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    if ratio >= 0.75:
        return True
    # 短标题几乎是长标题的子集
    # (如 HN 的简短讨论标题 vs 媒体的完整标题)
    if overlap >= 0.9 and inter >= 3 and shorter >= 3:
        return True
    # 中间档:足够多的共同实词 + 整体相似度过线
    # (如两家媒体对同一发布的不同措辞)
    return inter >= 3 and overlap >= 0.6 and ratio >= 0.35


def cluster_items(items: list[dict]) -> list[dict]:
    """把一天内的资讯聚合成事件。返回 [{lead, members}],按 lead 重要度降序。

    lead = 簇内重要度最高的一条;同源条目不互相合并
    (同一家媒体的两篇文章不算"多来源报道同一事件")。
    """
    toks = [_tokens(it["title"]) for it in items]
    n = len(items)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if items[i]["source_key"] == items[j]["source_key"]:
                continue
            if _same_event(toks[i], toks[j]):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri

    groups: dict[int, list[int]] = {}
    for idx in range(n):
        groups.setdefault(find(idx), []).append(idx)

    clusters = []
    for members in groups.values():
        member_items = [items[k] for k in members]
        lead = max(
            member_items,
            key=lambda it: (it["importance"], it["published_at"] or ""),
        )
        related = [it for it in member_items if it["id"] != lead["id"]]
        related.sort(
            key=lambda it: (-it["importance"], it["published_at"] or "")
        )
        clusters.append({"lead": lead, "related": related})
    clusters.sort(
        key=lambda c: (-c["lead"]["importance"], c["lead"]["published_at"] or "")
    )
    return clusters
