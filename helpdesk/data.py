from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


def _load(name: str) -> dict:
    with (DATA_DIR / name).open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def helpdesk() -> dict:
    return _load("helpdesk.json")


@lru_cache(maxsize=None)
def service_status() -> dict:
    return _load("service_status.json")


@lru_cache(maxsize=None)
def ticket_template() -> dict:
    return _load("ticket_template.json")


@lru_cache(maxsize=None)
def scenarios() -> list[dict]:
    return _load("scenarios.json")["scenarios"]


def storage_dir() -> Path:
    path = Path(os.environ.get("HELPDESK_STORAGE_DIR", REPO_ROOT / "local-storage"))
    if not path.is_absolute():
        path = REPO_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path
