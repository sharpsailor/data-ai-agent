import subprocess
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
FORMATS = ("csv", "json", "parquet")


def resolve(path: str) -> Path:
    """Relative paths are anchored at the project root, not the caller's cwd."""
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def read_any(path: Path) -> pd.DataFrame:
    return {"csv": pd.read_csv, "json": pd.read_json, "parquet": pd.read_parquet}[path.suffix.lstrip(".")](path)


class ETLTools:
    @staticmethod
    def extract_load(url: str, output_folder: str, format: str = "csv") -> str:
        if format not in FORMATS:
            raise ValueError(f"format must be one of {FORMATS}")
        resp = requests.get(url, timeout=30)
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
        # ponytail: separate process + timeout, not a real sandbox (still has fs/network).
        # Upgrade path: run inside `docker run --network none -v ./data:/data python:3.12-slim`.
        r = subprocess.run([sys.executable, "-I", "-c", code], cwd=ROOT,
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError(r.stderr[-2000:])
        return r.stdout[-2000:] or "Code ran successfully."
