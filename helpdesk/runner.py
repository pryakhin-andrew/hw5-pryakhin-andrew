from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import data
from .memory import reset_all


def _command(event: dict, scenario: dict, backend: str) -> list[str]:
    base = [sys.executable, "-m", "helpdesk.cli", "--json"]
    if scenario["part"] == 1:
        variant = scenario.get("graph_variant", "original")
        mode = "part1-clarify" if variant == "with_clarification" else "part1"
        return base + ["--mode", mode, "--message", event["message"]]
    return base + [
        "--mode",
        "agent",
        "--user",
        event["user_id"],
        "--thread",
        event["thread_id"],
        "--profile",
        scenario["status_profile"],
        "--backend",
        backend,
        "--message",
        event["message"],
    ]


def _run_event(command: list[str], repo_root: Path) -> dict:
    proc = subprocess.run(command, cwd=repo_root, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(command)}\n{proc.stderr}")
    return json.loads(proc.stdout)


def _render_log(scenario: dict, backend: str, steps: list[dict]) -> str:
    lines = [
        f"# {scenario['id']} - {scenario['title']}",
        "",
        f"- part: {scenario['part']}",
        f"- status_profile: {scenario['status_profile']}",
        f"- graph_variant: {scenario.get('graph_variant', '-')}",
        f"- backend: {backend}",
        "",
    ]
    for index, step in enumerate(steps, 1):
        event = step["event"]
        if event["action"] != "message":
            lines.append(f"## Event {index}: {event['action']} (same storage preserved)")
            lines.append("")
            continue
        result = step["result"]
        lines.append(f"## Event {index}: message")
        lines.append(f"- command: `{step['command']}`")
        if result.get("user_id"):
            lines.append(f"- user_id: {result['user_id']} | thread_id: {result['thread_id']}")
        lines.append(f"- user message: {event['message']}")
        lines.append(f"- nodes visited: {' -> '.join(result['nodes'])}")
        if "category" in result:
            lines.append(f"- category: {result.get('category')}")
        if "prior_messages" in result:
            lines.append(
                f"- conversation memory (prior messages read): {result['prior_messages']}"
            )
        if result.get("preferred_language"):
            lines.append(f"- user memory (language): {result['preferred_language']}")
        for call in result.get("tool_calls", []):
            lines.append(
                f"- tool request: {call['name']} {json.dumps(call['args'], ensure_ascii=False)}"
            )
        for res in result.get("tool_results", []):
            lines.append(
                f"- tool result: {res['name']} -> "
                f"{json.dumps(res['result'], ensure_ascii=False)}"
            )
        if result.get("ticket_file"):
            lines.append(f"- ticket draft: {Path(result['ticket_file']).name}")
        lines.append(f"- loop limit reached: {result.get('loop_limit_reached', False)}")
        lines.append(f"- assistant reply: {result['reply']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def run_scenario(scenario: dict, *, backend: str, repo_root: Path) -> list[dict]:
    if scenario.get("reset_before"):
        reset_all()
    steps: list[dict] = []
    for event in scenario["events"]:
        if event["action"] != "message":
            steps.append({"event": event, "result": None, "command": None})
            continue
        command = _command(event, scenario, backend)
        result = _run_event(command, repo_root)
        printable = " ".join(command[1:]).replace(str(repo_root), ".")
        steps.append({"event": event, "result": result, "command": f"python {printable}"})
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run HW5 demonstration scenarios")
    parser.add_argument("--only", default=None, help="Comma-separated scenario ids, e.g. S06,S07")
    parser.add_argument("--backend", choices=["fake", "openai"], default="fake")
    parser.add_argument("--outdir", default="outputs")
    args = parser.parse_args(argv)

    repo_root = data.REPO_ROOT
    out_dir = repo_root / args.outdir
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = set(args.only.split(",")) if args.only else None

    for scenario in data.scenarios():
        if wanted and scenario["id"] not in wanted:
            continue
        steps = run_scenario(scenario, backend=args.backend, repo_root=repo_root)
        log = _render_log(scenario, args.backend, steps)
        (out_dir / f"{scenario['id']}.md").write_text(log, encoding="utf-8")
        last = next((s["result"] for s in reversed(steps) if s["result"]), {})
        print(f"{scenario['id']}: {last.get('reply', '')[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
