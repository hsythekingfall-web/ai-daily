# AI 前沿日报

每天自动采集前沿 AI 资讯(RSS),去重、分类、评分后生成静态日报网站。
由 **GitHub Actions** 每日定时驱动,发布到 **GitHub Pages**,全程零服务器成本。

## 在线访问

开启 Pages 后:`https://<你的用户名>.github.io/ai-daily/`

## 工作原理

```
GitHub Actions(每天北京时间 08:00 / 支持手动触发)
    → 抓取全部 RSS 源            collector/fetch.py
    → URL/标题归一化去重          collector/dedup.py
    → 关键词分类 + 重要度评分      collector/classify.py
    → 写入 SQLite                data/aidaily.db(回写仓库实现持久化)
    → 渲染静态站 → 发布 Pages     collector/render.py
```

## 本地运行

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python run.py
open site/index.html
```

## 日常维护

- **加信息源**:编辑 `config/sources.yaml`,提交即可,下次采集自动生效
- **手动触发一次采集**:仓库 Actions 页 → 每日采集 → Run workflow
- **改采集时间**:改 `.github/workflows/daily.yml` 里的 cron(注意是 UTC 时间)
- **不再需要定时**:把 daily.yml 里的 `schedule:` 段删掉

## 目录结构

```
config/sources.yaml     信息源配置
collector/              采集管线(抓取/去重/分类/存储/渲染)
templates/              Jinja2 模板与样式
data/aidaily.db         SQLite 数据库(随仓库提交,实现跨天历史)
site/                   生成的静态站(不入库,每次重新生成)
.github/workflows/      定时采集工作流
```

## 设计原则

- 站内只存标题、摘要与原文链接,不转载全文
- 单个源抓取失败不影响整体,下次运行自动重试
- URL 归一化(去 utm 等追踪参数)+ 标题归一化,双保险去重

## 后续路线图

- LLM 摘要与中文翻译(替换 classify.py 的关键词评分)
- 同一事件多来源聚类(标题相似度 / embedding)
- Telegram 频道 / 邮件订阅推送
