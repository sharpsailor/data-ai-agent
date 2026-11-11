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
# Docker sandbox for LLM-generated code.
import os
os.environ["SECRET_PROBE"] = "leak-me"


def sandbox_fails(code: str) -> bool:
    try:
        ETLTools.execute_code(code, timeout=30)
        return False
    except RuntimeError:
        return True


assert "leak-me" not in ETLTools.execute_code("import os; print(os.environ)"), "host env leaked into sandbox"
assert ETLTools.execute_code("import pandas; print('ok')").strip() == "ok"
assert sandbox_fails("import urllib.request; urllib.request.urlopen('https://pokeapi.co', timeout=5)"), "network reachable"
assert sandbox_fails("import socket; socket.create_connection(('172.17.0.1', 5437), timeout=3)"), "host DB reachable"
assert sandbox_fails(f"open({str(DATA.parent / '.env')!r}).read()"), "project .env readable"
assert sandbox_fails("open('/usr/evil.txt', 'w').write('x')"), "root filesystem writable"
assert sandbox_fails(f"open('{os.path.expanduser('~')}/.ssh/id_ed25519').read()"), "ssh key readable"
assert ETLTools.execute_code("open('sandbox_probe.txt','w').write('ok'); print('wrote')").strip() == "wrote"
assert (DATA / "sandbox_probe.txt").read_text() == "ok" and (DATA / "sandbox_probe.txt").stat().st_uid == os.getuid()
(DATA / "sandbox_probe.txt").unlink()
try:
    ETLTools.execute_code("while True: pass", timeout=5)
    raise AssertionError("infinite loop not killed")
except RuntimeError as e:
    assert "killed" in str(e)

cols, rows = Database().execute_query("SELECT DISTINCT payment_method FROM payments ORDER BY 1")
assert cols == ["payment_method"] and len(rows) == 4
print("all guard checks passed")
