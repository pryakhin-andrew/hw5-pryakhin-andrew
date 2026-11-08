from __future__ import annotations

import re

from . import data

SERVICE_BY_TOPIC = {"wifi": "wifi", "password": "account_recovery"}

_LANGUAGES = {
    "kazakh": "Kazakh",
    "qazaq": "Kazakh",
    "russian": "Russian",
    "english": "English",
}


def _aliases(topic: str) -> list[str]:
    return data.helpdesk()["topic_aliases"][topic]


def mentions_topic(text: str, topic: str) -> bool:
    low = text.lower()
    return any(alias in low for alias in _aliases(topic))


def detect_topic(text: str) -> str | None:
    if mentions_topic(text, "wifi"):
        return "wifi"
    if mentions_topic(text, "password"):
        return "password"
    return None


def mentions_both_topics(text: str) -> bool:
    return mentions_topic(text, "wifi") and mentions_topic(text, "password")


def service_for_topic(topic: str) -> str:
    return SERVICE_BY_TOPIC[topic]


def detect_language_preference(text: str) -> str | None:
    low = text.lower()
    if not re.search(r"\b(prefer|remember|reply|replies|respond|answer)\b", low):
        return None
    for key, label in _LANGUAGES.items():
        if key in low:
            return label
    return None


def asked_about_language(text: str) -> bool:
    low = text.lower()
    return "language" in low and bool(re.search(r"\b(which|what|did|ask)\b", low))


def asks_for_instructions(text: str) -> bool:
    low = text.lower()
    return bool(re.search(r"\b(show|instructions|guide|troubleshoot|troubleshooting)\b", low))


def asks_for_status(text: str) -> bool:
    low = text.lower()
    return bool(
        re.search(r"\b(status|down|outage|operating|operational|unavailable|known problem)\b", low)
    )


def asks_for_ticket(text: str) -> bool:
    return "ticket" in text.lower()


def is_conditional_ticket(text: str) -> bool:
    low = text.lower()
    return "ticket" in low and bool(re.search(r"\bif (it|wi-?fi|the service)[^.]*operat", low))


def asks_recall(text: str) -> bool:
    low = text.lower()
    return bool(
        re.search(r"\b(which|what)\b.*\b(steps|problem|discuss|try|tried|already)\b", low)
    )


def extract_steps(text: str) -> list[str]:
    low = text.lower()
    steps: list[str] = []
    if re.search(r"enabl(e|ed).{0,20}(wi-?fi|it)", low) or "enabled wi" in low:
        steps.append("Enabled Wi-Fi")
    if re.search(r"forgot.{0,20}network", low):
        steps.append("Forgot the saved network")
    if re.search(r"reconnect", low):
        steps.append("Tried reconnecting")
    return steps
