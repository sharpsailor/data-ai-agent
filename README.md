# AI Data Agent

A multi-agent system built with LangGraph. It takes a plain-English data request and either
**queries Postgres** (SQL Analyst) or **runs an ETL job** (ETL Analyst), with a router that decides which.

**Cost: $0.** LLMs run locally through Ollama, and Postgres and Adminer run in Docker.
You can switch to a free cloud tier (Groq or Gemini) by changing one line in `.env`.

```
User ─► router_node ──sql──► Curate ► Schema ctx ► Generate SQL ► Safety judge ─yes─► Execute ─ok─► Answer
                    │                                     ▲            └─no─► Cancel       │
                    │                                     └──── retry once with DB error ◄─┘
                    └─etl──► llm_node ⇄ tool_node (extract_load_tool / transform_load_tool)
```

Print the real Mermaid graphs with `uv run python main.py --graphs`.

## Quick start

```bash
cd data-ai-agent
cp .env.example .env              # already done here
uv sync
docker compose up -d --wait       # Postgres on :5437 (seeded), Adminer on http://localhost:8080
ollama pull qwen2.5:3b

uv run python test_guards.py      # safety-layer checks, no LLM
uv run python main.py "What is the average fare by city?"
uv run python main.py             # interactive
uv run python smoke_test.py       # 5 end-to-end scenarios with real LLM + DB
```

Adminer login: system `PostgreSQL`, server `db`, user `agent_user`, password `agent_pass`, database `agent_db`.

## Example requests

| Request | Route | Result |
|---|---|---|
| What are the different types of payment methods? | sql | `SELECT DISTINCT payment_method ...`, then a plain-English answer |
| What is the average fare by city? | sql | `GROUP BY city` |
| Delete all failed payments | sql | Blocked; nothing is executed |
| Extract https://pokeapi.co/api/v2/pokemon into data/extract as CSV | etl | `data/extract/extracted_data.csv` |
| Transform data/extract/extracted_data.csv to keep only bulbasaur, save as csv in data/transform | etl | `data/transform/transformed_data.csv` |

## Models (`.env`)

| Option | `.env` | Cost |
|---|---|---|
| Local Ollama (default) | `LLM_BASIC=LLM_ADVANCED=ollama:qwen2.5:3b` (5/5 smoke test; `llama3.2` 4/5; `qwen2.5-coder` can't tool-call) | $0, offline |
| Groq free tier | `LLM_*=groq:llama-3.3-70b-versatile` + `GROQ_API_KEY`, `uv sync --extra groq` | $0 within rate limits |
| Gemini free tier | `LLM_*=google_genai:gemini-2.5-flash` + `GOOGLE_API_KEY`, `uv sync --extra gemini` | $0 within rate limits |

Any LangChain-supported provider works, for example paid Claude via `anthropic:claude-haiku-4-5` after `uv add langchain-anthropic`.
3B local models are slow (about 15–60 s per request on a 4 GB GPU) and sometimes write wrong SQL. A free 70B model on Groq is the easiest quality upgrade.

## Layout

```
agents/data_agent.py    router graph (structured output RouterSchema)
agents/sql_analyst.py   SQL pipeline + safety judge + one retry on DB error
agents/etl_analyst.py   ReAct loop over two @tools, recursion_limit=12
models/schema.py        Pydantic state + structured-output schemas
utils/llm_pick.py       tier -> any LangChain chat model (init_chat_model)
utils/database.py       schema-to-text for prompts, read-only query execution
utils/etl_tools.py      API -> csv/json/parquet, file preview, run generated pandas code
init/*.sql              schema, read-only role, synthetic ride-share data (200 users, 1500 rides)
```

## Design decisions

- **Defence in depth for SQL:** writes are blocked in three layers: a static check (a single `SELECT`/`WITH` only), the LLM judge, and an `agent_reader` DB role set to `default_transaction_read_only`. The read-only role is the guarantee, because the LLM judge alone can be fooled.
- **Self-correction:** on a DB error, the error is fed back to `Generate_SQL` for one retry.
- **Partial state updates:** nodes return only the fields they change, so the `messages` reducer appends cleanly. DB connections are closed after every call.
- **Generic extraction:** `extract_load` handles both paginated (`results`) and plain JSON APIs.
- **Isolated code execution:** generated pandas code runs in a separate process with a 60 s timeout. **It is not a sandbox:** the code still has filesystem and network access. Only run trusted prompts.
- **Bounded agent loop:** the ETL reason/act loop is capped with `recursion_limit`.
