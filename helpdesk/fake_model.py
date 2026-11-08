from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from . import textutils

SERVICE_LABEL = {"wifi": "Wi-Fi", "account_recovery": "account recovery"}

_KZ = {
    "ack": (
        "Жақсы, есте сақтадым. Мәселеңіз Wi-Fi байланысына қатысты. "
        "Сіз жасап көрген қадамдар: {steps}. Бұдан былай жауаптарды қазақ тілінде беремін."
    ),
    "recall": "Сіз Wi-Fi мәселесі туралы айттыңыз. Жасап көрген қадамдарыңыз: {steps}.",
    "language": (
        "Сіз қазақ тілінде жауап беруімді өтіндіңіз. Мен Wi-Fi, құпиясөзді қалпына келтіру, "
        "қызмет күйін тексеру және жергілікті тикет жобаларымен көмектесе аламын."
    ),
}


@dataclass
class _Facts:
    all_text: str
    latest: str
    topic: str | None
    service: str
    steps: list[str]
    want_instructions: bool
    want_status: bool
    want_ticket: bool
    conditional: bool
    recall: bool
    memory_q: bool
    preferred_language: str | None

    @property
    def any_action(self) -> bool:
        return self.want_instructions or self.want_status or self.want_ticket

    @property
    def need_status(self) -> bool:
        return self.want_status or (self.want_ticket and self.conditional)


class FakeHelpdeskModel(BaseChatModel):
    """A deterministic, rule-based stand-in for a tool-calling chat model.

    It emits the same tool-call protocol a real model would, so the LangGraph
    agent is identical for the fake and the real backend. Clearly not an LLM.
    """

    @property
    def _llm_type(self) -> str:
        return "fake-helpdesk"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeHelpdeskModel":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        message = self._decide(messages)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _decide(self, messages) -> AIMessage:
        facts = self._gather(messages)
        executed, results = self._tool_history(messages)

        if (facts.recall or facts.memory_q) and not facts.any_action:
            return AIMessage(content=self._memory_answer(facts))

        if facts.want_instructions and "find_instructions" not in executed:
            return self._tool_call("find_instructions", {"topic": facts.topic or "wifi"})

        if facts.need_status and "check_service_status" not in executed:
            return self._tool_call("check_service_status", {"service": facts.service})

        if facts.want_ticket and "prepare_ticket" not in executed:
            if not (facts.topic and facts.steps):
                return AIMessage(content=self._ask_details())
            if facts.conditional:
                status = results.get("check_service_status")
                if status and status.get("is_operational"):
                    return self._tool_call("prepare_ticket", self._ticket_args(facts, status))
            else:
                return self._tool_call("prepare_ticket", self._ticket_args(facts, None))

        return AIMessage(content=self._final_answer(facts, executed, results))

    def _gather(self, messages) -> _Facts:
        humans = [m.content for m in messages if isinstance(m, HumanMessage)]
        all_text = " ".join(humans)
        latest = humans[-1] if humans else ""
        topic = textutils.detect_topic(all_text)

        steps: list[str] = []
        for text in humans:
            for step in textutils.extract_steps(text):
                if step not in steps:
                    steps.append(step)

        system = next(
            (m.content for m in reversed(messages) if isinstance(m, SystemMessage)), ""
        )
        match = re.search(r"Preferred reply language:\s*([A-Za-z]+)", system)
        preferred = match.group(1) if match and match.group(1).lower() != "none" else None

        return _Facts(
            all_text=all_text,
            latest=latest,
            topic=topic,
            service=textutils.service_for_topic(topic) if topic else "wifi",
            steps=steps,
            want_instructions=textutils.asks_for_instructions(all_text) and topic is not None,
            want_status=textutils.asks_for_status(all_text),
            want_ticket=textutils.asks_for_ticket(all_text),
            conditional=textutils.is_conditional_ticket(all_text),
            recall=textutils.asks_recall(latest),
            memory_q=bool(
                re.search(r"(language|preference|previous problem|told you)", latest.lower())
            ),
            preferred_language=preferred,
        )

    def _tool_history(self, messages) -> tuple[set[str], dict[str, dict]]:
        executed: set[str] = set()
        results: dict[str, dict] = {}
        for message in messages:
            if isinstance(message, ToolMessage):
                executed.add(message.name)
                try:
                    results[message.name] = json.loads(message.content)
                except (json.JSONDecodeError, TypeError):
                    results[message.name] = {}
        return executed, results

    def _tool_call(self, name: str, args: dict) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": f"call_{name}"}],
        )

    def _ticket_args(self, facts: _Facts, status: dict | None) -> dict:
        label = SERVICE_LABEL.get(facts.service, facts.service)
        return {
            "summary": f"{label} problem persists after the steps the user tried.",
            "steps_tried": facts.steps,
            "category": facts.topic,
            "service_status": status["status"] if status else "not checked",
        }

    def _memory_answer(self, facts: _Facts) -> str:
        if facts.preferred_language == "Kazakh":
            if facts.recall and facts.topic == "wifi":
                return _KZ["recall"].format(steps=", ".join(facts.steps) or "белгісіз")
            return _KZ["language"]
        if facts.preferred_language:
            return (
                f"You asked me to reply in {facts.preferred_language}. "
                "I can help with Wi-Fi, password recovery, service status and local ticket drafts."
            )
        if facts.recall and facts.topic:
            label = SERVICE_LABEL.get(facts.service, facts.service)
            return (
                f"You reported a {label} problem. "
                f"The steps you said you tried: {', '.join(facts.steps) or 'none recorded'}."
            )
        return (
            "No preferred language or previous problem is recorded for you yet. "
            "Tell me your problem and what you have already tried, and I can help."
        )

    def _ask_details(self) -> str:
        return (
            "What problem are you having, and what have you already tried? "
            "I need a short description and the steps you tried before I can prepare a ticket draft."
        )

    def _final_answer(self, facts: _Facts, executed: set[str], results: dict[str, dict]) -> str:
        parts: list[str] = []
        label = SERVICE_LABEL.get(facts.service, facts.service)

        if "find_instructions" in executed and not facts.want_status and not facts.want_ticket:
            guide = results.get("find_instructions", {})
            if guide.get("found"):
                return (
                    f"Here are the {label} instructions from the local guide "
                    f"({guide.get('instruction_id')}): "
                    + " ".join(f"{i}. {s}" for i, s in enumerate(guide.get("steps", []), 1))
                )

        status = results.get("check_service_status")
        ticket = results.get("prepare_ticket")

        if ticket and ticket.get("saved"):
            status_word = status["status"] if status else "not checked"
            return (
                f"The demo status source reports {label} is {status_word}. "
                if status
                else ""
            ) + (
                f"I prepared a local ticket draft ({ticket['ticket_file']}) using the steps you "
                f"listed: {', '.join(facts.steps)}. Nothing has been sent."
            )

        if facts.want_ticket and facts.conditional and status:
            if status.get("is_outage"):
                return (
                    f"The demo status source reports an outage for {label}. You asked me to prepare "
                    "a ticket only if the service was operating, so I have not prepared one. "
                    "The data gives no repair time."
                )
            if not status.get("is_known"):
                return (
                    f"I could not determine the {label} status, so I cannot confirm it is "
                    "operating. I have not prepared a ticket. Would you like a draft that records "
                    "the status could not be checked?"
                )

        if status and not facts.want_ticket:
            if status.get("is_outage"):
                return (
                    f"The demo status source reports an outage for {label} (a known problem). "
                    "The data gives no repair time."
                )
            if status.get("is_operational"):
                return f"The demo status source reports {label} is operating, with no reported outage."
            return f"The demo {label} status source is unavailable, so I could not determine it."

        if facts.preferred_language == "Kazakh" and facts.topic == "wifi":
            return _KZ["ack"].format(steps=", ".join(facts.steps) or "белгісіз")

        if facts.topic:
            noted = f" Steps you have tried: {', '.join(facts.steps)}." if facts.steps else ""
            return (
                f"Noted. Your problem concerns {label}.{noted} "
                "Tell me if you would like the instructions, a status check, or a ticket draft."
            )

        return (
            "I can help with Wi-Fi or password problems, service status and local ticket drafts. "
            "What would you like to do?"
        )
