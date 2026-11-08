from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from . import session


def _print_human(result: dict) -> None:
    print("Nodes visited:", " -> ".join(result["nodes"]))
    if "category" in result:
        print("Category:", result.get("category"))
    if result.get("preferred_language"):
        print("User memory  (language):", result["preferred_language"])
    if "prior_messages" in result:
        print("Conversation memory (prior messages):", result["prior_messages"])
    for call in result.get("tool_calls", []):
        print("Tool request:", call["name"], json.dumps(call["args"], ensure_ascii=False))
    for res in result.get("tool_results", []):
        print("Tool result: ", res["name"], "->", json.dumps(res["result"], ensure_ascii=False))
    if result.get("ticket_file"):
        print("Ticket draft saved:", result["ticket_file"])
    if result.get("loop_limit_reached"):
        print("Loop limit reached.")
    print("Assistant:", result["reply"])


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="HW5 LangGraph university IT helpdesk")
    parser.add_argument("--mode", choices=["part1", "part1-clarify", "agent"], default="agent")
    parser.add_argument("--message", required=True)
    parser.add_argument("--user", default="demo-user-a")
    parser.add_argument("--thread", default="cli")
    parser.add_argument("--profile", default="normal")
    parser.add_argument("--backend", choices=["fake", "openai"], default="fake")
    parser.add_argument("--model", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.mode in ("part1", "part1-clarify"):
        result = session.run_part1(
            args.message, with_clarification=args.mode == "part1-clarify"
        )
    else:
        result = session.run_agent_message(
            user_id=args.user,
            thread_id=args.thread,
            profile=args.profile,
            message=args.message,
            backend=args.backend,
            model_name=args.model,
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
