import ipaddress
import os
import socket
import subprocess
import sys
import uuid
from functools import cache
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FORMATS = ("csv", "json", "parquet")


def resolve(path: str) -> Path:
    """Anchor at the project root and refuse anything outside data/ (blocks ../ and symlink escapes)."""
    p = (ROOT / path).resolve()
    if not p.is_relative_to(DATA.resolve()):
        raise ValueError(f"Path must be inside {DATA}: {path}")
    return p


def check_public_url(url: str) -> None:
    """Block SSRF: http(s) only, and the host must not resolve to a private/loopback/link-local/metadata IP."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("Only http(s) URLs are allowed")
    # ponytail: checks DNS once; a rebinding host could switch IPs before requests connects. Pin the IP if exposed publicly.
    for info in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80)):
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError(f"Refusing non-public address {ip} for {u.hostname}")


def read_any(path: Path) -> pd.DataFrame:
    return {"csv": pd.read_csv, "json": pd.read_json, "parquet": pd.read_parquet}[path.suffix.lstrip(".")](path)


class ETLTools:
    @staticmethod
    def extract_load(url: str, output_folder: str, format: str = "csv") -> str:
        if format not in FORMATS:
            raise ValueError(f"format must be one of {FORMATS}")
        check_public_url(url)
        resp = requests.get(url, timeout=30, allow_redirects=False)  # a redirect could point inside the network
        resp.raise_for_status()
        data = resp.json()
        # Paginated APIs (e.g. PokeAPI) wrap records in "results"; otherwise take the payload as-is.
        records = data.get("results", data) if isinstance(data, dict) else data
        df = pd.json_normalize(records)
        out = resolve(output_folder)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"extracted_data.{format}"
        {"csv": lambda: df.to_csv(path, index=False),
         "json": lambda: df.to_json(path, orient="records", indent=2),
         "parquet": lambda: df.to_parquet(path, index=False)}[format]()
        return f"Saved {len(df)} rows x {len(df.columns)} cols to {path}"

    @staticmethod
    def transform_load_context(path: str) -> str:
        df = read_any(resolve(path))
        return f"Columns/dtypes:\n{df.dtypes.to_string()}\n\nTop 3 rows:\n{df.head(3).to_string()}"

    @staticmethod
    def execute_code(code: str, timeout: int = 60) -> str:
        """Run LLM-generated code in a throwaway container: no network, read-only root, only data/ writable,
        no env/secrets, non-root, capped CPU/memory/pids/time. Fails closed if Docker is unavailable."""
        ensure_sandbox_image()
        data = DATA.resolve()
        data.mkdir(exist_ok=True)
        name = f"etl-sandbox-{uuid.uuid4().hex[:12]}"
        cmd = ["docker", "run", "--rm", "-i", "--name", name,
               "--network", "none", "--read-only", "--tmpfs", "/tmp:size=64m",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--user", f"{os.getuid()}:{os.getgid()}", "--env", "HOME=/tmp",
               "--memory", "512m", "--cpus", "1", "--pids-limit", "128",
               # Mounted at the same absolute path so host paths in the generated code work unchanged.
               "-v", f"{data}:{data}:rw", "-w", str(data),
               SANDBOX_IMAGE, "python", "-I", "-"]
        try:
            r = subprocess.run(cmd, input=code, capture_output=True, text=True, timeout=timeout, env=_docker_env())
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name], capture_output=True)
            raise RuntimeError(f"Sandboxed code exceeded {timeout}s and was killed")
        if r.returncode:
            raise RuntimeError(r.stderr[-2000:])
        return r.stdout[-2000:] or "Code ran successfully."


SANDBOX_IMAGE = "data-ai-agent-sandbox:1"


def _docker_env() -> dict:
    # The docker CLI only needs these; nothing from .env (API keys, DB creds) is passed along.
    return {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT")}


@cache
def ensure_sandbox_image() -> None:
    if subprocess.run(["docker", "image", "inspect", SANDBOX_IMAGE], capture_output=True, env=_docker_env()).returncode:
        print(f"Building {SANDBOX_IMAGE} (first run only, ~1 min)...", file=sys.stderr)
        # Dockerfile on stdin = empty build context (don't ship .venv/.env to the daemon).
        subprocess.run(["docker", "build", "-q", "-t", SANDBOX_IMAGE, "-"], input=(ROOT / "Dockerfile.sandbox").read_bytes(),
                       check=True, capture_output=True, env=_docker_env())
