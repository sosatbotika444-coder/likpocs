"""Convenience entry point for the DormFlow FastAPI service."""

import os
from pathlib import Path

import uvicorn


BACKEND_DIR = Path(__file__).resolve().parent / "backend"


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        app_dir=str(BACKEND_DIR),
        host=os.getenv("DORMFLOW_HOST", "127.0.0.1"),
        port=int(os.getenv("DORMFLOW_PORT", "8000")),
        reload=os.getenv("DORMFLOW_RELOAD", "false").lower() == "true",
    )
