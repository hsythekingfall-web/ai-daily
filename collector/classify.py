"""基于关键词规则的分类与重要度评分。

不依赖外部 API,离线可用;后续接入 LLM 时替换这两个函数即可。
"""

# 按顺序匹配,命中即归入该分类
CATEGORY_RULES = [
    ("大模型", ["llm", "gpt", "claude", "gemini", "llama", "mistral", "qwen",
               "deepseek", "grok", "kimi", "language model", "foundation model",
               "chatbot", "chatgpt"]),
    ("智能体", ["agent", "agentic", "mcp", "tool use", "autonomous",
               "copilot", "computer use"]),
    ("多模态", ["image generation", "video generation", "text-to-image",
               "text-to-video", "diffusion", "sora", "midjourney",
               "stable diffusion", "multimodal", "vision", "image model",
               "voice", "speech"]),
    ("芯片与基础设施", ["chip", "gpu", "tpu", "nvidia", "datacenter",
                  "data center", "inference", "training cluster",
                  "semiconductor", "compute"]),
    ("开源项目", ["open source", "open-source", "open weights", "open model",
               "github"]),
    ("政策与行业", ["regulation", "policy", "lawsuit", "copyright", "ban",
               "funding", "raise", "acquisition", "ipo", "senate", "eu act",
               "market"]),
    ("研究前沿", ["paper", "arxiv", "benchmark", "research", "study",
               "breakthrough", "nobel"]),
]
FALLBACK = "行业动态"

# 出现这些词通常意味着大事件,重要度上调
HIGH_SIGNAL = [
    "release", "launch", "open source", "open-source", "sota",
    "state-of-the-art", "breakthrough", "record", "billion", "million users",
    "acquire", "acquisition", "sues", "sued", "lawsuit", "ban", "shutdown",
    "nobel", "agi", "superintelligence",
]

# 官方博客本身就是大事件;HN 已经过社区热度筛选
BOOSTED_SOURCES = ("openai", "deepmind", "hackernews")


def classify(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    for category, keywords in CATEGORY_RULES:
        if any(k in text for k in keywords):
            return category
    return FALLBACK


def score_importance(title: str, summary: str = "", source_key: str = "") -> int:
    text = f"{title} {summary}".lower()
    score = 3 + sum(1 for kw in HIGH_SIGNAL if kw in text)
    if source_key in BOOSTED_SOURCES:
        score += 1
    return max(1, min(5, score))
