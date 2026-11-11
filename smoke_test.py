"""End-to-end smoke test with the real LLMs + DB. Run: uv run python smoke_test.py"""
import shutil

import pandas as pd

from main import ask
from utils.etl_tools import ROOT

shutil.rmtree(ROOT / "data", ignore_errors=True)
fails = []


def check(name, cond, out):
    print(("PASS " if cond else "FAIL ") + name, "|", out.get("route_response"), "|", out["final_answer"][:160].replace("\n", " "))
    if not cond:
        fails.append(name)


o = ask("What are the different types of payment methods we have in our database?")
check("sql distinct", o["route_response"] == "sql" and all(m in o["final_answer"].lower().replace(" ", "_")
      for m in ["credit_card", "debit_card", "paypal", "apple_pay"]), o)

o = ask("What is the average fare by city?")
check("sql group by", o["route_response"] == "sql" and "toronto" in o["final_answer"].lower(), o)

o = ask("Delete all failed payments")
check("unsafe blocked", o["route_response"] == "sql" and "not executed" in o["final_answer"].lower(), o)

o = ask("Extract https://pokeapi.co/api/v2/pokemon into data/extract as CSV")
f = ROOT / "data/extract/extracted_data.csv"
check("etl extract", o["route_response"] == "etl" and f.exists() and "bulbasaur" in f.read_text(), o)

o = ask("Transform data/extract/extracted_data.csv to keep only the row where name is bulbasaur, save as csv in data/transform")
t = ROOT / "data/transform/transformed_data.csv"
check("etl transform", o["route_response"] == "etl" and t.exists() and pd.read_csv(t)["name"].tolist() == ["bulbasaur"], o)

print(f"\n{5 - len(fails)}/5 passed", fails or "")
raise SystemExit(bool(fails))
