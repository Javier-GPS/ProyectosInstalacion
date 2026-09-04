"""Run the local API with ``python -m luminaire_optimizer``."""

import os
from pathlib import Path

import uvicorn


def _load_dotenv() -> None:
    """Load local configuration before Uvicorn imports the API."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if key.strip() and value:
            os.environ.setdefault(key.strip(), value)


if __name__ == "__main__":
    _load_dotenv()
    uvicorn.run("luminaire_optimizer.api:app", host="127.0.0.1", port=8760, reload=False)
