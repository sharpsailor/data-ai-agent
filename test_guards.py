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

# ETL paths are confined to data/, URLs must be public, generated code gets no secrets.
from utils.etl_tools import DATA, ETLTools, check_public_url, resolve

assert resolve("data/extract/x.csv") == DATA.resolve() / "extract/x.csv"
for bad_path in ["../../etc/passwd", "/etc/passwd", "data/../.env", "agents/data_agent.py"]:
    try:
        resolve(bad_path)
        raise AssertionError(f"path escape allowed: {bad_path}")
    except ValueError:
        pass
for bad_url in ["http://127.0.0.1:5437/", "http://169.254.169.254/latest/meta-data/",
                "http://localhost:8080/", "http://10.0.0.1/", "file:///etc/passwd", "ftp://example.com/"]:
    try:
        check_public_url(bad_url)
        raise AssertionError(f"SSRF allowed: {bad_url}")
    except ValueError:
        pass
assert ETLTools.execute_code("import os; print(len(os.environ))").strip().startswith(("0", "1"))

cols, rows = Database().execute_query("SELECT DISTINCT payment_method FROM payments ORDER BY 1")
assert cols == ["payment_method"] and len(rows) == 4
print("all guard checks passed")
