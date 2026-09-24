"""SQLite 存储层:建表、去重写入、按日期查询。"""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key      TEXT NOT NULL,
    source_name     TEXT NOT NULL,
    title           TEXT NOT NULL,
    url             TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    published_at    TEXT,
    fetched_at      TEXT NOT NULL,
    first_seen_date TEXT NOT NULL,
    category        TEXT NOT NULL,
    importance      INTEGER NOT NULL,
    url_hash        TEXT NOT NULL UNIQUE,
    title_hash      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_date ON items(first_seen_date);
CREATE INDEX IF NOT EXISTS idx_items_title ON items(title_hash);
"""

INSERT_SQL = """
INSERT INTO items (source_key, source_name, title, url, summary, published_at,
                   fetched_at, first_seen_date, category, importance,
                   url_hash, title_hash)
VALUES (:source_key, :source_name, :title, :url, :summary, :published_at,
        :fetched_at, :first_seen_date, :category, :importance,
        :url_hash, :title_hash)
"""


class Store:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """为旧库补齐新增列(新库由 SCHEMA 直接建出)。"""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(items)")}
        if "title_zh" not in cols:
            self.conn.execute("ALTER TABLE items ADD COLUMN title_zh TEXT")
        if "summary_zh" not in cols:
            self.conn.execute("ALTER TABLE items ADD COLUMN summary_zh TEXT")
        if "llm_done" not in cols:
            self.conn.execute(
                "ALTER TABLE items ADD COLUMN llm_done INTEGER NOT NULL DEFAULT 0"
            )

    def existing_hashes(self) -> tuple[set[str], set[str]]:
        """库里已有的 (url_hash 集合, title_hash 集合)。"""
        rows = self.conn.execute("SELECT url_hash, title_hash FROM items").fetchall()
        return ({r["url_hash"] for r in rows}, {r["title_hash"] for r in rows})

    def insert_item(self, item: dict) -> bool:
        """插入新条目;url 或标题重复时静默跳过,返回 False。"""
        try:
            self.conn.execute(INSERT_SQL, item)
            return True
        except sqlite3.IntegrityError:
            return False

    def items_by_date(self, date_str: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM items WHERE first_seen_date = ? "
            "ORDER BY importance DESC, published_at DESC",
            (date_str,),
        ).fetchall()

    def items_missing_llm(self, limit: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM items WHERE llm_done = 0 "
            "ORDER BY published_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def update_llm_result(self, item_id: int, title_zh: str,
                          summary_zh: str) -> None:
        self.conn.execute(
            "UPDATE items SET title_zh = ?, summary_zh = ?, llm_done = 1 "
            "WHERE id = ?",
            (title_zh, summary_zh, item_id),
        )

    def dates(self) -> list[sqlite3.Row]:
        """所有有数据的日期及条数,倒序。"""
        return self.conn.execute(
            "SELECT first_seen_date, COUNT(*) AS n FROM items "
            "GROUP BY first_seen_date ORDER BY first_seen_date DESC"
        ).fetchall()

    def close(self):
        self.conn.commit()
        self.conn.close()
