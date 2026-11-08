from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from . import textutils, tools


class Part1State(TypedDict):
    message: str
    category: str
    reply: str


def _instructions_reply(topic: str) -> str:
    guide = tools.find_instructions(topic)
    steps = " ".join(f"{i}. {s}" for i, s in enumerate(guide["steps"], 1))
    return f"{guide['title']} ({guide['instruction_id']}): {steps}"


def read_request(state: Part1State) -> dict:
    return {"category": _classify(state["message"])}


def _classify(message: str, *, with_clarification: bool = False) -> str:
    if with_clarification and textutils.mentions_both_topics(message):
        return "both"
    topic = textutils.detect_topic(message)
    return topic or "other"


def wifi_help(state: Part1State) -> dict:
    return {"reply": _instructions_reply("wifi")}


def password_help(state: Part1State) -> dict:
    return {"reply": _instructions_reply("password")}


def other_help(state: Part1State) -> dict:
    return {
        "reply": "I can help with Wi-Fi or password problems. "
        "Does your issue concern Wi-Fi or a password?"
    }


def clarify_problem(state: Part1State) -> dict:
    return {
        "reply": "Your message mentions both topics. "
        "Is the problem connecting to Wi-Fi, or recovering your account password?"
    }


def _route(state: Part1State) -> str:
    return state["category"]


def build_graph(*, with_clarification: bool = False):
    graph = StateGraph(Part1State)

    def read(state: Part1State) -> dict:
        return {"category": _classify(state["message"], with_clarification=with_clarification)}

    graph.add_node("read_request", read)
    graph.add_node("wifi_help", wifi_help)
    graph.add_node("password_help", password_help)
    graph.add_node("other_help", other_help)

    graph.add_edge(START, "read_request")

    route_map = {"wifi": "wifi_help", "password": "password_help", "other": "other_help"}
    if with_clarification:
        graph.add_node("clarify_problem", clarify_problem)
        route_map["both"] = "clarify_problem"

    graph.add_conditional_edges("read_request", _route, route_map)

    for node in set(route_map.values()):
        graph.add_edge(node, END)

    return graph.compile()
