"""No-LLM checks for the safety layers. Run: uv run python test_guards.py (DB must be up)."""
import psycopg2

from agents.sql_analyst import clean_sql_string
from utils.database import Database, is_read_only_sql

assert clean_sql_string("```sql\nSELECT 1\n```") == "SELECT 1;"
assert clean_sql_string("SELECT 1;;") == "SELECT 1;"

assert is_read_only_sql("SELECT * FROM users LIMIT 10;")
assert is_read_only_sql("with x as (select 1) select * from x")
for bad in ["DELETE FROM payments", "SELECT 1; DROP TABLE users", "UPDATE users SET city='x'",
            "WITH d AS (DELETE FROM rides RETURNING *) SELECT * FROM d", ""]:
    assert not is_read_only_sql(bad), bad

# The database itself must refuse writes from the agent's role, even if every LLM/static check is bypassed.
try:
    Database().execute_query("DELETE FROM payments RETURNING 1")
    raise AssertionError("write was allowed!")
except psycopg2.Error as e:
    assert "read-only" in str(e), e

cols, rows = Database().execute_query("SELECT DISTINCT payment_method FROM payments ORDER BY 1")
assert cols == ["payment_method"] and len(rows) == 4
print("all guard checks passed")
