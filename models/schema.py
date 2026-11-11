from operator import add
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class AgentSchema(BaseModel):
    """State of the SQL Analyst graph."""
    messages: Annotated[list, add] = []
    user_question: str = ""
    curated_question: str = ""
    prompt_query_context: str = ""
    generated_sql_query: str = ""
    is_safe: Literal["yes", "no"] = "no"
    comments: str = ""
    sql_query_execution_result: str = ""
    final_answer: str = ""


class JudgeAgentSchema(BaseModel):
    """Verdict of the SQL safety judge."""
    answer: Literal["yes", "no"] = Field(description="'yes' if the SQL is a read-only query, otherwise 'no'")
    comments: str = Field(description="Short reason for the verdict")


class ETLAgentSchema(BaseModel):
    """State of the ETL Analyst graph."""
    messages: Annotated[list, add] = []


class RouterSchema(BaseModel):
    """Router decision."""
    answer: Literal["sql", "etl"] = Field(description="'sql' to query the database, 'etl' to extract/transform files or APIs")
    comments: str = Field(default="", description="Short reason")


class DataAgentSchema(BaseModel):
    """State of the top-level Data Agent graph."""
    messages: Annotated[list, add] = []
    route_response: str = ""
    final_answer: str = ""
