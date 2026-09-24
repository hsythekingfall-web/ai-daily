"""LLM 后处理:为每条资讯生成中文标题和中文摘要。

走 OpenAI 兼容接口,默认 DeepSeek;通过环境变量可换任意兼容服务:
  LLM_API_KEY   必填,未配置时整个阶段静默跳过
  LLM_BASE_URL  默认 https://api.deepseek.com
  LLM_MODEL     默认 deepseek-chat
失败的条目保留 llm_done=0,下次运行自动补处理。
"""
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是AI日报的编辑。根据用户给出的英文AI新闻标题和摘要,"
    '输出JSON: {"t": "不超过28个字的中文标题", '
    '"s": "两句中文摘要,第一句概括这条新闻说了什么,'
    '第二句说明它为什么重要,总共不超过80字"}。'
    "只输出JSON,不要任何多余内容。"
)


def _extract_json(text: str) -> tuple[str, str] | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if isinstance(d, dict) and d.get("t") and d.get("s"):
        return str(d["t"]).strip(), str(d["s"]).strip()
    return None


def _translate_one(client: httpx.Client, base_url: str, model: str,
                   item: dict) -> tuple[str, str] | None:
    user = f"标题: {item['title']}\n摘要: {item['summary'] or '(无)'}"
    for attempt in range(3):
        try:
            resp = client.post(
                f"{base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 300,
                    "response_format": {"type": "json_object"},
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = _extract_json(content)
            if parsed:
                return parsed
            log.debug("LLM 返回无法解析:%s", content[:120])
        except Exception as exc:
            log.debug("LLM 第 %d 次调用失败:%s", attempt + 1, exc)
        if attempt < 2:
            time.sleep(3 * (attempt + 1))
    return None


def process_pending(store, limit: int = 150, workers: int = 5) -> int:
    """处理所有 llm_done=0 的条目;未配置 Key 时不做任何事。"""
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        log.warning("未配置 LLM_API_KEY,跳过中文摘要翻译")
        return 0
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")

    pending = store.items_missing_llm(limit)
    if not pending:
        return 0
    log.info("LLM 处理 %d 条(模型 %s)…", len(pending), model)

    done = 0
    with httpx.Client(
        trust_env=False, headers={"Authorization": f"Bearer {api_key}"}
    ) as client:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_translate_one, client, base_url, model, item): item
                for item in pending
            }
            for fut in as_completed(futures):
                item = futures[fut]
                result = fut.result()
                if result:
                    store.update_llm_result(item["id"], result[0], result[1])
                    done += 1
    store.conn.commit()
    log.info("LLM 完成 %d/%d 条", done, len(pending))
    return done
