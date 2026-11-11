import ipaddress
import socket
import subprocess
import sys
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
        # ponytail: separate process, empty env (no API keys/DB creds), timeout, cwd=data/ — still NOT a
        # sandbox: the code can touch the filesystem and network as this user. Upgrade path:
        # `docker run --rm --network none --read-only -v ./data:/data --memory 512m python:3.12-slim`.
        DATA.mkdir(exist_ok=True)
        r = subprocess.run([sys.executable, "-I", "-c", code], cwd=DATA, env={},
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError(r.stderr[-2000:])
        return r.stdout[-2000:] or "Code ran successfully."
