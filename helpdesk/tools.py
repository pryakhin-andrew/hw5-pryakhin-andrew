from __future__ import annotations

import copy
import json
import re
import time
import uuid
from pathlib import Path

from . import data

_SECRET_PATTERN = re.compile(
    r"\b(password|passcode|api[_-]?key|recovery code|otp|one[- ]time code)\b", re.IGNORECASE
)


def find_instructions(topic: str) -> dict:
    topic = (topic or "").strip().lower()
    if topic in ("wi-fi", "wifi"):
        topic = "wifi"
    guide = data.helpdesk()["instructions"].get(topic)
    if guide is None:
        return {
            "found": False,
            "topic": topic,
            "error": "No instructions for this topic. Supported: wifi, password.",
        }
    return {
        "found": True,
        "topic": topic,
        "title": guide["title"],
        "steps": guide["steps"],
        "instruction_id": guide["instruction_id"],
    }


def check_service_status(service: str, profile: str) -> dict:
    service = (service or "").strip().lower()
    if service in ("password", "account recovery", "recovery"):
        service = "account_recovery"
    if service in ("wi-fi",):
        service = "wifi"
    profiles = data.service_status()["profiles"]
    if profile not in profiles:
        return {"service": service, "profile": profile, "error": "Unknown status profile."}
    entry = profiles[profile].get(service)
    if entry is None:
        return {"service": service, "profile": profile, "error": "Unknown service."}
    return {
        "service": service,
        "profile": profile,
        "status": entry["status"],
        "message": entry["message"],
        "is_operational": entry["status"] == "operational",
        "is_outage": entry["status"] == "outage",
        "is_known": entry["status"] != "unknown",
    }


def _reject_secrets(values: list[str]) -> None:
    for value in values:
        if value and _SECRET_PATTERN.search(value):
            raise ValueError("Tickets must not contain passwords, API keys or recovery codes.")


def prepare_ticket(
    *,
    category: str | None,
    summary: str,
    steps_tried: list[str] | None = None,
    service_status: str | None = None,
    status_profile: str | None = None,
    user_id: str | None = None,
    thread_id: str | None = None,
    reference_ids: list[str] | None = None,
    storage_dir: Path | str | None = None,
) -> dict:
    steps_tried = list(steps_tried or [])
    reference_ids = list(reference_ids or [])
    _reject_secrets([summary, *steps_tried])

    ticket = copy.deepcopy(data.ticket_template()["ticket"])
    ticket_id = "TCK-" + time.strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
    ticket.update(
        {
            "ticket_id": ticket_id,
            "status": "draft",
            "user_id": user_id,
            "thread_id": thread_id,
            "category": category,
            "summary": summary,
            "steps_tried": steps_tried,
            "service_status": service_status,
            "status_profile": status_profile,
            "reference_ids": reference_ids,
        }
    )

    base = Path(storage_dir) if storage_dir is not None else data.storage_dir()
    tickets_dir = base / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    path = tickets_dir / f"{ticket_id}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(ticket, fh, indent=2)

    return {"saved": True, "ticket_file": str(path), "ticket": ticket, "delivery": "local draft only"}
