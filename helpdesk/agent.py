from __future__ import annotations

import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from . import data, textutils, tools
from .fake_model import FakeHelpdeskModel
from .memory import UserMemory

MAX_TOOL_LOOPS = 4

SYSTEM_TEMPLATE = """You are a university IT helpdesk assistant for a practice exercise.
Scope: {scope}.
Use the tools to answer. Call find_instructions to retrieve Wi-Fi or password steps,
check_service_status to look up whether a service is operating, and prepare_ticket to save
a LOCAL ticket draft. A ticket is only a local draft; nothing is sent to a real helpdesk.

Rules:
- Only prepare a ticket if the user asked for one. If the user said to prepare it only when the
  service is operating, first check the status and do not prepare a ticket during an outage or
  when the status is unknown.
- Never invent troubleshooting steps, repair times, or a service status. Use only the user's
  stated steps and the tool results.
- Never put a password, API key or recovery code in a ticket.
- If a ticket is requested but the problem or the steps tried are missing, ask for them instead
  of guessing.
Preferred reply language: {language}. If a language other than None is set, reply in it."""


def build_model(backend: str, model_name: str | None = None):
    if backend == "fake":
        return FakeHelpdeskModel()
    from langchain_openai import ChatOpenAI

    name = model_name or os.environ.get("MODEL_NAME") or "gpt-4o-mini"
    return ChatOpenAI(model=name, temperature=0)


def _build_tools(*, profile: str, user_id: str, thread_id: str, storage_dir: Path | None):
    @tool
    def find_instructions(topic: str) -> dict:
        """Look up local Wi-Fi or password instructions. topic is 'wifi' or 'password'."""
        return tools.find_instructions(topic)

    @tool
    def check_service_status(service: str) -> dict:
        """Check whether a service is operating or has a known outage.
        service is 'wifi' or 'account_recovery'."""
        return tools.check_service_status(service, profile)

    @tool
    def prepare_ticket(
        summary: str,
        steps_tried: list[str],
        category: str | None = None,
        service_status: str | None = None,
    ) -> dict:
        """Save a LOCAL ticket draft from the problem summary and the steps the user already
        tried. Never include passwords, API keys or recovery codes."""
        return tools.prepare_ticket(
            category=category,
            summary=summary,
            steps_tried=steps_tried,
            service_status=service_status,
            status_profile=profile,
            user_id=user_id,
            thread_id=thread_id,
            storage_dir=storage_dir,
        )

    return [find_instructions, check_service_status, prepare_ticket]


def _system_prompt(language: str | None) -> str:
    scope = "; ".join(data.helpdesk()["scope"])
    return SYSTEM_TEMPLATE.format(scope=scope, language=language or "None")


def build_agent_app(
    *,
    model,
    user_id: str,
    thread_id: str,
    profile: str,
    checkpointer,
    user_memory: UserMemory,
    storage_dir: Path | None = None,
):
    tool_list = _build_tools(
        profile=profile, user_id=user_id, thread_id=thread_id, storage_dir=storage_dir
    )
    model_with_tools = model.bind_tools(tool_list)

    def remember(state: MessagesState) -> dict:
        last = _last_human(state["messages"])
        if last is not None:
            language = textutils.detect_language_preference(last.content)
            if language:
                user_memory.set(user_id, "language", language)
        return {}

    def agent(state: MessagesState) -> dict:
        language = user_memory.get(user_id, "language")
        system = SystemMessage(_system_prompt(language))
        response = model_with_tools.invoke([system] + state["messages"])
        return {"messages": [response]}

    def route(state: MessagesState) -> str:
        messages = state["messages"]
        last = messages[-1]
        if getattr(last, "tool_calls", None):
            tool_turns = sum(
                1 for m in messages if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
            )
            if tool_turns > MAX_TOOL_LOOPS:
                return END
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("remember", remember)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tool_list))
    graph.add_edge(START, "remember")
    graph.add_edge("remember", "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer)


def _last_human(messages) -> HumanMessage | None:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message
    return None
