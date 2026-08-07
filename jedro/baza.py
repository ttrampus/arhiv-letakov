from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .modeli import Magazine

SCHEMA = """
CREATE TABLE IF NOT EXISTS magazines (
    id            INTEGER PRIMARY KEY,
    store         TEXT NOT NULL,
    title         TEXT,
    date_from     TEXT,
    date_to       TEXT,
    source_url    TEXT,
    file_url      TEXT,
    local_path    TEXT NOT NULL,
    sha256        TEXT NOT NULL UNIQUE,
    bytes         INTEGER,
    downloaded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_store_date ON magazines(store, date_from);
CREATE INDEX IF NOT EXISTS idx_file_url ON magazines(file_url);

CREATE TABLE IF NOT EXISTS meat_versions (
    magazine_id  INTEGER PRIMARY KEY REFERENCES magazines(id) ON DELETE CASCADE,
    local_path   TEXT NOT NULL,
    source_pages INTEGER NOT NULL,
    kept_pages   INTEGER NOT NULL,
    created_at   TEXT NOT NULL
);
"""


class Archive:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def __enter__(self) -> "Archive":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def has_url(self, url: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM magazines WHERE file_url = ? LIMIT 1", (url,)).fetchone() is not None

    def has_hash(self, sha256: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM magazines WHERE sha256 = ? LIMIT 1", (sha256,)).fetchone() is not None

    def taken_paths(self) -> set[str]:
        return {r["local_path"] for r in self.conn.execute("SELECT local_path FROM magazines")}

    def record(self, magazine: Magazine, local_path: Path, sha256: str, size: int) -> bool:
        try:
            self.conn.execute(
                """INSERT INTO magazines (store, title, date_from, date_to, source_url,
                                          file_url, local_path, sha256, bytes, downloaded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (magazine.store, magazine.title,
                 magazine.date_from.isoformat() if magazine.date_from else None,
                 magazine.date_to.isoformat() if magazine.date_to else None,
                 magazine.source_url, magazine.dedupe_key, str(local_path), sha256, size,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return False

    def record_meat_version(self, magazine_id: int, path: Path,
                            source_pages: int, kept_pages: int) -> None:
        self.conn.execute(
            """INSERT INTO meat_versions
                   (magazine_id, local_path, source_pages, kept_pages, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(magazine_id) DO UPDATE SET
                   local_path=excluded.local_path,
                   source_pages=excluded.source_pages,
                   kept_pages=excluded.kept_pages,
                   created_at=excluded.created_at""",
            (magazine_id, str(path), source_pages, kept_pages,
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        self.conn.commit()

    def magazines_without_meat_version(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT m.* FROM magazines m
               LEFT JOIN meat_versions v ON v.magazine_id = m.id
               WHERE v.magazine_id IS NULL
               ORDER BY m.store, m.date_from""").fetchall()

    def id_for_path(self, local_path: str) -> int | None:
        row = self.conn.execute(
            "SELECT id FROM magazines WHERE local_path = ?", (local_path,)).fetchone()
        return row["id"] if row else None

    def all_rows(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM magazines ORDER BY store, date_from").fetchall()

    def delete(self, row_id: int) -> None:
        self.conn.execute("DELETE FROM meat_versions WHERE magazine_id = ?", (row_id,))
        self.conn.execute("DELETE FROM magazines WHERE id = ?", (row_id,))
        self.conn.commit()

    def summary(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT store, COUNT(*) AS count, MAX(downloaded_at) AS latest
               FROM magazines GROUP BY store ORDER BY store""").fetchall()

    def meat_summary(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT m.store, COUNT(*) AS files,
                      SUM(v.source_pages) AS source_pages, SUM(v.kept_pages) AS kept_pages
               FROM meat_versions v JOIN magazines m ON m.id = v.magazine_id
               GROUP BY m.store ORDER BY m.store""").fetchall()
