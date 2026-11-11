from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from agents.etl_analyst import etl_analyst
from agents.sql_analyst import sql_analyst
from models.schema import DataAgentSchema, RouterSchema
from utils.llm_pick import pick_llm


def router_node(state: DataAgentSchema):
    decision = pick_llm("basic").with_structured_output(RouterSchema).invoke(
        "Classify the user's request.\n"
        "- 'sql': a question answered by querying the ride-share database "
        "(users, drivers, vehicles, rides, payments, ratings).\n"
        "- 'etl': extracting data from a URL/API into a file, or transforming/filtering an existing "
        "csv/json/parquet file. Any request that mentions a URL or a file path is 'etl'.\n\n"
        "Examples:\n"
        "'How many rides were there in Toronto?' -> sql\n"
        "'Delete all failed payments' -> sql\n"
        "'Extract https://api.example.com/items into data/extract as json' -> etl\n"
        "'Filter data/extract/extracted_data.csv to rows where name is pikachu' -> etl\n\n"
        f"Request: {state.messages[-1].content}")
    return {"route_response": decision.answer}


def route_edge(state: DataAgentSchema) -> str:
    return {"sql": "sql_node", "etl": "etl_node"}[state.route_response]


def sql_node(state: DataAgentSchema):
    q = state.messages[-1].content
    out = sql_analyst.invoke({"messages": [HumanMessage(content=q)], "user_question": q})
    answer = out["final_answer"]
    return {"final_answer": answer, "messages": [AIMessage(content=answer, response_metadata={"sql": out["generated_sql_query"]})]}


def etl_node(state: DataAgentSchema):
    out = etl_analyst.invoke({"messages": [HumanMessage(content=state.messages[-1].content)]})
    answer = out["messages"][-1].content
    return {"final_answer": answer, "messages": [AIMessage(content=answer)]}


g = StateGraph(DataAgentSchema)
g.add_node("router_node", router_node)
g.add_node("sql_node", sql_node)
g.add_node("etl_node", etl_node)
g.add_edge(START, "router_node")
g.add_conditional_edges("router_node", route_edge, ["sql_node", "etl_node"])
g.add_edge("sql_node", END)
g.add_edge("etl_node", END)
data_agent = g.compile()
