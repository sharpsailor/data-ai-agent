import os
import re

import psycopg2
from dotenv import load_dotenv

load_dotenv()

MAX_ROWS = 100
_WRITE = re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge|copy|call|do|vacuum)\b", re.I)


def db_config() -> dict:
    return dict(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5437")),
        dbname=os.getenv("DB_DATABASE", "agent_db"),
        user=os.getenv("DB_USER", "agent_reader"),
        password=os.getenv("DB_PASSWORD", "reader_pass"),
    )


def is_read_only_sql(sql: str) -> bool:
    """Deterministic pre-check: one SELECT/WITH statement, no write keywords."""
    s = sql.strip().rstrip(";").strip()
    return bool(s) and ";" not in s and s.lower().startswith(("select", "with")) and not _WRITE.search(s)


class Database:
    def __init__(self, config: dict | None = None):
        self.config = config or db_config()

    def _connect(self):
        conn = psycopg2.connect(**self.config)
        conn.set_session(readonly=True)  # belt and braces on top of the read-only role
        return conn

    def get_schema_details(self, schema: str = "public", sample_rows: int = 5) -> str:
        """Plain-text description of every table: columns, types and a few sample rows (LLM context)."""
        out = []
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = %s ORDER BY table_name, ordinal_position", (schema,))
            tables: dict[str, list[str]] = {}
            for table, col, dtype in cur.fetchall():
                tables.setdefault(table, []).append(f"{col} ({dtype})")
            for table, cols in tables.items():
                cur.execute(f'SELECT * FROM "{schema}"."{table}" LIMIT %s', (sample_rows,))
                rows = "\n".join(f"    {r}" for r in cur.fetchall())
                out.append(f"Table: {table}\n  Columns: {', '.join(cols)}\n  Sample rows:\n{rows}")
        conn.close()
        return "\n\n".join(out)

    def execute_query(self, sql: str) -> tuple[list[str], list[tuple]]:
        """Run a query; raises psycopg2.Error on failure so callers can react."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [d[0] for d in cur.description], cur.fetchmany(MAX_ROWS)
        finally:
            conn.close()
