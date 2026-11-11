import re

import psycopg2
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from models.schema import AgentSchema, JudgeAgentSchema
from utils.database import Database, is_read_only_sql
from utils.llm_pick import pick_llm

MAX_ATTEMPTS = 2  # first try + one retry with the DB error fed back


class SQLState(AgentSchema):
    error: str = ""
    attempts: int = 0


def clean_sql_string(raw: str) -> str:
    """Strip ```sql fences / stray prose the model adds anyway."""
    m = re.search(r"```(?:sql)?\s*(.*?)```", raw, re.S | re.I)
    sql = (m.group(1) if m else raw).strip()
    return sql.rstrip(";").strip() + ";"


def curate_question(state: SQLState):
    q = state.user_question or state.messages[-1].content
    curated = pick_llm("basic").invoke(
        "Rewrite this data request so it is clear and unambiguous for a SQL analyst. "
        "Keep its exact meaning and action: if it asks to delete/update/insert, the rewrite must "
        "still ask for that. Do not add filters or calculations that were not requested. "
        "Return only the rewritten request.\n\nRequest: " + q).content.strip()
    return {"user_question": q, "curated_question": curated, "messages": [AIMessage(content=f"Curated question: {curated}")]}


def prompt_query_context(state: SQLState):
    schema = Database().get_schema_details("public")
    prompt = f"""You are an expert PostgreSQL analyst. Write ONE PostgreSQL query that answers the question.

Rules:
- Return ONLY the raw SQL. No markdown, no explanation.
- Read-only: a single SELECT (or WITH ... SELECT) statement.
- If the request asks to modify data (delete/update/insert/drop), write that statement anyway; a safety check will block it.
- Use only the tables and columns listed below. Include the grouping column(s) in the SELECT list.
- Unless the question asks for more, LIMIT the output to 10 rows.

Database schema (with sample rows):
{schema}

Question: {state.curated_question}"""
    return {"prompt_query_context": prompt}


def generate_sql(state: SQLState):
    prompt = state.prompt_query_context
    if state.error:
        prompt += f"\n\nYour previous query:\n{state.generated_sql_query}\nfailed with:\n{state.error}\nFix it."
    sql = clean_sql_string(pick_llm("advanced").invoke(prompt).content)
    return {"generated_sql_query": sql, "error": "", "attempts": state.attempts + 1}


def is_safe_sql(state: SQLState):
    sql = state.generated_sql_query
    if not is_read_only_sql(sql):
        return {"is_safe": "no", "comments": "Rejected by static check: only a single read-only SELECT/WITH query is allowed."}
    verdict = pick_llm("advanced").with_structured_output(JudgeAgentSchema).invoke(
        "You are an SQL safety judge. Answer 'yes' if the query below only READS data "
        "(SELECT/WITH). Answer 'no' if it could modify data or schema (INSERT, UPDATE, DELETE, "
        f"DROP, ALTER, TRUNCATE, CREATE, GRANT ...).\n\nQuery:\n{sql}")
    return {"is_safe": verdict.answer, "comments": verdict.comments}


def is_safe_sql_condition(state: SQLState) -> str:
    return "Execute_SQL" if state.is_safe == "yes" else "Cancel_SQL_if_Not_Safe"


def cancel_sql(state: SQLState):
    msg = f"Query not executed. It was judged unsafe: {state.comments}"
    return {"final_answer": msg, "messages": [AIMessage(content=msg)]}


def execute_sql(state: SQLState):
    try:
        cols, rows = Database().execute_query(state.generated_sql_query)
    except psycopg2.Error as e:
        return {"error": str(e).strip(), "sql_query_execution_result": ""}
    return {"sql_query_execution_result": f"Columns: {cols}\nRows: {rows}"}


def after_execute(state: SQLState) -> str:
    if not state.error:
        return "Present_Final_Answer"
    return "Generate_SQL" if state.attempts < MAX_ATTEMPTS else "Report_Error"


def report_error(state: SQLState):
    msg = f"Sorry, the query failed: {state.error}"
    return {"final_answer": msg, "messages": [AIMessage(content=msg)]}


def present_final_answer(state: SQLState):
    answer = pick_llm("basic").invoke(
        "Answer the user's question in plain English using only the query result below. "
        "Be concise. Do not mention SQL.\n\n"
        f"Question: {state.curated_question}\nResult:\n{state.sql_query_execution_result}").content.strip()
    return {"final_answer": answer, "messages": [AIMessage(content=answer)]}


g = StateGraph(SQLState)
for name, fn in [("Curate_Question", curate_question), ("Prompt_Query_Context", prompt_query_context),
                 ("Generate_SQL", generate_sql), ("Is_Safe_SQL", is_safe_sql),
                 ("Cancel_SQL_if_Not_Safe", cancel_sql), ("Execute_SQL", execute_sql),
                 ("Report_Error", report_error), ("Present_Final_Answer", present_final_answer)]:
    g.add_node(name, fn)
g.add_edge(START, "Curate_Question")
g.add_edge("Curate_Question", "Prompt_Query_Context")
g.add_edge("Prompt_Query_Context", "Generate_SQL")
g.add_edge("Generate_SQL", "Is_Safe_SQL")
g.add_conditional_edges("Is_Safe_SQL", is_safe_sql_condition, ["Execute_SQL", "Cancel_SQL_if_Not_Safe"])
g.add_conditional_edges("Execute_SQL", after_execute, ["Present_Final_Answer", "Generate_SQL", "Report_Error"])
g.add_edge("Cancel_SQL_if_Not_Safe", END)
g.add_edge("Report_Error", END)
g.add_edge("Present_Final_Answer", END)
sql_analyst = g.compile()


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What are the different types of Payment Methods we have in our database"
    out = sql_analyst.invoke({"messages": [HumanMessage(content=q)], "user_question": q})
    print("SQL:", out["generated_sql_query"], "\n\nAnswer:", out["final_answer"])
