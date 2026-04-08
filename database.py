import aiosqlite
import logging
from typing import Any, Optional
from datetime import datetime

logger = logging.getLogger('PluginMarket.DB')


class Database:
    def __init__(self, path: str = 'plugins.db'):
        self.path = path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._create_tables()
        await self._db.commit()
        logger.info("Database tables ready")

    async def _create_tables(self):
        await self._db.executescript("""
        CREATE TABLE IF NOT EXISTS plugins (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            description TEXT NOT NULL,
            version     TEXT NOT NULL DEFAULT '1.0.0',
            category    TEXT NOT NULL DEFAULT 'Utility',
            tags        TEXT NOT NULL DEFAULT '',
            file_url    TEXT NOT NULL,
            file_name   TEXT NOT NULL,
            image_url   TEXT,
            author_id   INTEGER NOT NULL,
            guild_id    INTEGER NOT NULL,
            approved    INTEGER NOT NULL DEFAULT 0,
            rejected    INTEGER NOT NULL DEFAULT 0,
            reject_reason TEXT,
            price       REAL NOT NULL DEFAULT 0.0,
            downloads   INTEGER NOT NULL DEFAULT 0,
            rating_sum  INTEGER NOT NULL DEFAULT 0,
            rating_count INTEGER NOT NULL DEFAULT 0,
            is_leaked   INTEGER NOT NULL DEFAULT 0,
            plugin_type TEXT NOT NULL DEFAULT 'Spigot',
            mc_version  TEXT NOT NULL DEFAULT '1.20+',
            source_url  TEXT,
            msg_id      INTEGER,
            channel_id  INTEGER,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ratings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_id   INTEGER NOT NULL REFERENCES plugins(id) ON DELETE CASCADE,
            user_id     INTEGER NOT NULL,
            rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            review      TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(plugin_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS droppers (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL UNIQUE,
            guild_id     INTEGER NOT NULL,
            drops_count  INTEGER NOT NULL DEFAULT 0,
            verified     INTEGER NOT NULL DEFAULT 0,
            bio          TEXT,
            joined_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS purchases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_id   INTEGER NOT NULL REFERENCES plugins(id) ON DELETE CASCADE,
            user_id     INTEGER NOT NULL,
            purchased_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(plugin_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS leak_requests (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_name  TEXT NOT NULL,
            description  TEXT,
            requester_id INTEGER NOT NULL,
            fulfilled    INTEGER NOT NULL DEFAULT 0,
            fulfilled_by INTEGER,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS plugin_versions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_id   INTEGER NOT NULL REFERENCES plugins(id) ON DELETE CASCADE,
            version     TEXT NOT NULL,
            changelog   TEXT,
            file_url    TEXT NOT NULL,
            file_name   TEXT NOT NULL,
            released_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS bot_config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS warnings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            guild_id    INTEGER NOT NULL,
            mod_id      INTEGER NOT NULL,
            reason      TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS plugin_reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_id   INTEGER NOT NULL REFERENCES plugins(id) ON DELETE CASCADE,
            reporter_id INTEGER NOT NULL,
            reason      TEXT NOT NULL,
            resolved    INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

    # ── Generic helpers ──────────────────────────────────────────────────────

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        cursor = await self._db.execute(sql, params)
        await self._db.commit()
        return cursor

    async def fetchone(self, sql: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        cursor = await self._db.execute(sql, params)
        return await cursor.fetchone()

    async def fetchall(self, sql: str, params: tuple = ()) -> list:
        cursor = await self._db.execute(sql, params)
        return await cursor.fetchall()

    # ── Plugin helpers ───────────────────────────────────────────────────────

    async def add_plugin(self, **kwargs) -> int:
        cols = ', '.join(kwargs.keys())
        placeholders = ', '.join('?' for _ in kwargs)
        cursor = await self.execute(
            f"INSERT INTO plugins ({cols}) VALUES ({placeholders})",
            tuple(kwargs.values())
        )
        return cursor.lastrowid

    async def get_plugin(self, plugin_id: int) -> Optional[aiosqlite.Row]:
        return await self.fetchone("SELECT * FROM plugins WHERE id=?", (plugin_id,))

    async def update_plugin(self, plugin_id: int, **kwargs):
        kwargs['updated_at'] = datetime.utcnow().isoformat()
        set_clause = ', '.join(f"{k}=?" for k in kwargs)
        await self.execute(
            f"UPDATE plugins SET {set_clause} WHERE id=?",
            tuple(kwargs.values()) + (plugin_id,)
        )

    async def approve_plugin(self, plugin_id: int):
        await self.update_plugin(plugin_id, approved=1, rejected=0, reject_reason=None)

    async def reject_plugin(self, plugin_id: int, reason: str):
        await self.update_plugin(plugin_id, approved=0, rejected=1, reject_reason=reason)

    async def search_plugins(self, query: str, category: str = None,
                              leaked: bool = False, limit: int = 10, offset: int = 0) -> list:
        base = """SELECT * FROM plugins WHERE approved=1 AND is_leaked=?
                  AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(tags) LIKE ?)"""
        params = [int(leaked), f'%{query.lower()}%', f'%{query.lower()}%', f'%{query.lower()}%']
        if category:
            base += " AND LOWER(category)=?"
            params.append(category.lower())
        base += " ORDER BY downloads DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        return await self.fetchall(base, tuple(params))

    async def get_plugins(self, category: str = None, leaked: bool = False,
                          pending: bool = False, limit: int = 10, offset: int = 0) -> list:
        if pending:
            sql = "SELECT * FROM plugins WHERE approved=0 AND rejected=0 ORDER BY created_at ASC LIMIT ? OFFSET ?"
            return await self.fetchall(sql, (limit, offset))
        base = "SELECT * FROM plugins WHERE approved=1 AND is_leaked=?"
        params: list = [int(leaked)]
        if category:
            base += " AND LOWER(category)=?"
            params.append(category.lower())
        base += " ORDER BY downloads DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        return await self.fetchall(base, tuple(params))

    async def count_plugins(self, category: str = None, leaked: bool = False, pending: bool = False) -> int:
        if pending:
            row = await self.fetchone("SELECT COUNT(*) as c FROM plugins WHERE approved=0 AND rejected=0")
        elif category:
            row = await self.fetchone(
                "SELECT COUNT(*) as c FROM plugins WHERE approved=1 AND is_leaked=? AND LOWER(category)=?",
                (int(leaked), category.lower())
            )
        else:
            row = await self.fetchone(
                "SELECT COUNT(*) as c FROM plugins WHERE approved=1 AND is_leaked=?", (int(leaked),)
            )
        return row['c'] if row else 0

    async def increment_downloads(self, plugin_id: int):
        await self.execute("UPDATE plugins SET downloads=downloads+1 WHERE id=?", (plugin_id,))

    # ── Rating helpers ───────────────────────────────────────────────────────

    async def add_rating(self, plugin_id: int, user_id: int, rating: int, review: str = None) -> bool:
        existing = await self.fetchone(
            "SELECT id FROM ratings WHERE plugin_id=? AND user_id=?", (plugin_id, user_id)
        )
        if existing:
            return False
        await self.execute(
            "INSERT INTO ratings (plugin_id, user_id, rating, review) VALUES (?,?,?,?)",
            (plugin_id, user_id, rating, review)
        )
        await self.execute(
            "UPDATE plugins SET rating_sum=rating_sum+?, rating_count=rating_count+1 WHERE id=?",
            (rating, plugin_id)
        )
        return True

    async def get_ratings(self, plugin_id: int) -> list:
        return await self.fetchall(
            "SELECT * FROM ratings WHERE plugin_id=? ORDER BY created_at DESC", (plugin_id,)
        )

    # ── Dropper helpers ──────────────────────────────────────────────────────

    async def get_dropper(self, user_id: int) -> Optional[aiosqlite.Row]:
        return await self.fetchone("SELECT * FROM droppers WHERE user_id=?", (user_id,))

    async def add_dropper(self, user_id: int, guild_id: int):
        await self.execute(
            "INSERT OR IGNORE INTO droppers (user_id, guild_id) VALUES (?,?)", (user_id, guild_id)
        )

    async def increment_drops(self, user_id: int):
        await self.execute("UPDATE droppers SET drops_count=drops_count+1 WHERE user_id=?", (user_id,))

    # ── Config helpers ───────────────────────────────────────────────────────

    async def set_config(self, key: str, value: str):
        await self.execute(
            "INSERT OR REPLACE INTO bot_config (key, value) VALUES (?,?)", (key, value)
        )

    async def get_config(self, key: str) -> Optional[str]:
        row = await self.fetchone("SELECT value FROM bot_config WHERE key=?", (key,))
        return row['value'] if row else None

    # ── Warning helpers ──────────────────────────────────────────────────────

    async def add_warning(self, user_id: int, guild_id: int, mod_id: int, reason: str) -> int:
        cursor = await self.execute(
            "INSERT INTO warnings (user_id, guild_id, mod_id, reason) VALUES (?,?,?,?)",
            (user_id, guild_id, mod_id, reason)
        )
        return cursor.lastrowid

    async def get_warnings(self, user_id: int, guild_id: int) -> list:
        return await self.fetchall(
            "SELECT * FROM warnings WHERE user_id=? AND guild_id=? ORDER BY created_at DESC",
            (user_id, guild_id)
        )

    async def close(self):
        if self._db:
            await self._db.close()
