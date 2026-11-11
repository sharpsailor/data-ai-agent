import os
from functools import cache

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

load_dotenv()

DEFAULTS = {"basic": "ollama:qwen2.5:3b", "advanced": "ollama:qwen2.5:3b"}


@cache
def pick_llm(level: str = "basic"):
    """Tier name -> chat model. Set LLM_BASIC / LLM_ADVANCED as 'provider:model' to swap."""
    return init_chat_model(os.getenv(f"LLM_{level.upper()}", DEFAULTS[level]), temperature=0)
