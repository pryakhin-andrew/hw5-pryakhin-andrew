from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from . import data, graph_part1
from .agent import MAX_TOOL_LOOPS, build_agent_app, build_model
from .memory import UserMemory, checkpoint_path, user_memory_path


def run_part1(message: str, *, with_clarification: bool = False) -> dict:
    app = graph_part1.build_graph(with_clarification=with_clarification)
    nodes: list[str] = []
    state: dict = {"message": message}
    for update in app.stream({"message": message}, stream_mode="updates"):
        for node, delta in update.items():
            nodes.append(node)
            state.update(delta or {})
    return {
        "variant": "with_clarification" if with_clarification else "original",
        "message": message,
        "nodes": nodes,
        "category": state.get("category"),
        "reply": state.get("reply"),
    }


def run_agent_message(
    *,
    user_id: str,
    thread_id: str,
    profile: str,
    message: str,
    backend: str = "fake",
    model_name: str | None = None,
    storage_dir: Path | None = None,
) -> dict:
    storage = Path(storage_dir) if storage_dir else data.storage_dir()
    storage.mkdir(parents=True, exist_ok=True)
    user_mem = UserMemory(user_memory_path(storage))
    model = build_model(backend, model_name)

    nodes: list[str] = []
    tool_calls: list[dict] = []
    tool_results: list[dict] = []
    ticket_file: str | None = None

    with SqliteSaver.from_conn_string(str(checkpoint_path(storage))) as checkpointer:
        app = build_agent_app(
            model=model,
            user_id=user_id,
            thread_id=thread_id,
            profile=profile,
            checkpointer=checkpointer,
            user_memory=user_mem,
            storage_dir=storage,
        )
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}
        prior = app.get_state(config).values.get("messages", [])
        prior_messages = len(prior)

        for update in app.stream({"messages": [HumanMessage(message)]}, config, stream_mode="updates"):
            for node, delta in update.items():
                nodes.append(node)
                for msg in (delta or {}).get("messages", []):
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        for call in msg.tool_calls:
                            tool_calls.append({"name": call["name"], "args": call["args"]})
                    if isinstance(msg, ToolMessage):
                        parsed = _parse(msg.content)
                        tool_results.append({"name": msg.name, "result": parsed})
                        if msg.name == "prepare_ticket" and isinstance(parsed, dict):
                            ticket_file = parsed.get("ticket_file") or ticket_file

        final = app.get_state(config).values["messages"]

    reply = next(
        (m.content for m in reversed(final) if isinstance(m, AIMessage) and m.content), ""
    )
    tool_turns = sum(1 for m in final if isinstance(m, AIMessage) and getattr(m, "tool_calls", None))

    return {
        "user_id": user_id,
        "thread_id": thread_id,
        "profile": profile,
        "backend": backend,
        "message": message,
        "nodes": nodes,
        "prior_messages": prior_messages,
        "preferred_language": user_mem.get(user_id, "language"),
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "ticket_file": ticket_file,
        "loop_limit_reached": tool_turns > MAX_TOOL_LOOPS,
        "reply": reply,
    }


def _parse(content):
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content
