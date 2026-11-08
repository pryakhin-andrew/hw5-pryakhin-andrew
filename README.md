# HW5 - University IT helpdesk with LangGraph

A terminal helpdesk assistant built in four stages with LangGraph:

1. A rule-based routing graph (no LLM).
2. A model that chooses three tools (`find_instructions`, `check_service_status`, `prepare_ticket`).
3. Conversation memory (LangGraph checkpointer) and user memory (persistent preference).
4. Tests and GitHub Actions CI that run without an API key.

All helpdesk data is fictional and local. No real accounts or services are involved, and tickets
are only local drafts.

## Requirements

- Python 3.12 or newer (developed on 3.15, CI runs on 3.12).
- The pinned packages in `requirements.txt`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Part 1 needs no API key. For the real-model run in Part 2, copy the environment file and set a
tool-capable OpenAI model:

```bash
cp .env.example .env
```

Then edit `.env`:

```
OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-4o-mini
HELPDESK_STORAGE_DIR=local-storage
```

The key is read from `.env` (git-ignored). Provider: OpenAI. Model used for the saved real run:
`gpt-4o-mini`.

## Run the assistant

Part 1 (rule-based, no model):

```bash
python -m helpdesk.cli --mode part1 --message "I cannot connect to Wi-Fi."
python -m helpdesk.cli --mode part1-clarify --message "My Wi-Fi password does not work."
```

Parts 2 and 3 (model and tools). Default backend is the deterministic fake model, add
`--backend openai` to use the real model:

```bash
python -m helpdesk.cli --mode agent --user demo-user-a --thread s06 --profile normal \
  --message "Show me the Wi-Fi troubleshooting steps."

python -m helpdesk.cli --mode agent --user demo-user-a --thread s06 --profile normal --backend openai \
  --message "Check whether Wi-Fi is down. If it is operating, prepare a ticket about this problem."
```

Arguments: `--user` and `--thread` identify the user and the conversation, `--profile` selects a
service-status snapshot (`normal`, `wifi_outage`, `recovery_outage`, `status_unavailable`),
`--json` prints the full trace as JSON. Each invocation is one process, so running the command
again demonstrates a real restart against the same storage.

## Run the supplied scenarios

```bash
python -m helpdesk.runner --backend fake                       # all S01-S14 -> outputs/
python -m helpdesk.runner --backend openai --only S06,S07,S08,S14 --outdir outputs/real
```

The runner handles `reset_before` and `restart_process` from `data/scenarios.json`. Every message
runs as its own subprocess, so a `restart_process` event is a genuine new process reading the same
SQLite storage. Logs are written to `outputs/`.

## Memory and how to clear it

Set by `HELPDESK_STORAGE_DIR` (default `local-storage/`, git-ignored):

- `local-storage/conversations.sqlite` - LangGraph SQLite checkpointer. Conversation state per
  `thread_id`.
- `local-storage/user_memory.sqlite` - a small `user_prefs` table keyed by `user_id`. Learned
  preferences such as the reply language.
- `local-storage/tickets/` - local ticket drafts (`TCK-*.json`).

Clear everything:

```bash
rm -rf local-storage
```

Or clear memory from Python:

```python
from helpdesk.memory import reset_all
reset_all()
```

## Tests

```bash
python -m pytest -q
```

Tests use the fake model and a temporary storage directory, so they need no API key. They cover
routing, the three tools called directly, conversation recall after a restart, preference
persistence across threads, and isolation between users and conversations.

## Continuous integration

`.github/workflows/ci.yml` installs `requirements.txt` and runs `pytest` on every push and pull
request, with no API key. The real-model demonstration is kept separate and is never run in CI.

## Layout

```
helpdesk/
  data.py          load JSON fixtures, resolve storage dir
  textutils.py     topic / intent / preference detection
  tools.py         find_instructions, check_service_status, prepare_ticket (callable directly)
  graph_part1.py   rule-based graph (original and clarify variants)
  fake_model.py    deterministic tool-calling stand-in for the LLM
  agent.py         model + tools graph, memory nodes, loop limit
  memory.py        UserMemory (SQLite) and checkpointer/paths
  session.py       run one message, collect the trace
  cli.py           terminal entry point
  runner.py        replay data/scenarios.json
tests/             routing, tools, memory, user isolation
outputs/           saved scenario logs (fake model) and outputs/real (real model)
```
