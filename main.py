"""Usage:
    uv run python main.py "What are the different payment methods?"
    uv run python main.py                 # interactive prompt
    uv run python main.py --graphs        # print Mermaid diagrams of all three graphs
"""
import sys

from langchain_core.messages import HumanMessage

from agents.data_agent import data_agent
from agents.etl_analyst import etl_analyst
from agents.sql_analyst import sql_analyst


def ask(question: str) -> dict:
    return data_agent.invoke({"messages": [HumanMessage(content=question)]})


def show(out: dict):
    print(f"[route: {out['route_response']}]")
    sql = out["messages"][-1].response_metadata.get("sql")
    if sql:
        print(f"[sql: {sql}]")
    print(out["final_answer"], "\n")


if __name__ == "__main__":
    if sys.argv[1:] == ["--graphs"]:
        for name, graph in [("data_agent", data_agent), ("sql_analyst", sql_analyst), ("etl_analyst", etl_analyst)]:
            print(f"%% {name}\n{graph.get_graph().draw_mermaid()}")
    elif sys.argv[1:]:
        show(ask(" ".join(sys.argv[1:])))
    else:
        while (q := input("Ask (blank to quit)> ").strip()):
            show(ask(q))
