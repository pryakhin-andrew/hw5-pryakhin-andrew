# HW5 - My LangGraph helpdesk

Provider/model for the real run: OpenAI, `gpt-4o-mini`. The default backend everywhere else is a
deterministic fake model (`helpdesk/fake_model.py`) so the graph, tools and memory are identical
with or without an API key.

## Part 1 - How the graph works

### My graph and state

```
START -> read_request -> (conditional edge on state["category"])
                         |- "wifi"     -> wifi_help     -> END
                         |- "password" -> password_help -> END
                         |- "other"    -> other_help    -> END
```

State (`helpdesk/graph_part1.py`, `Part1State`):

| Field | What it holds |
| --- | --- |
| `message` | The user's original message (set at START, never changed) |
| `category` | `wifi` / `password` / `other` (and `both` in the changed graph), written by `read_request` |
| `reply` | The instructions or question, written by one help node |

What each node reads and changes:

- `read_request` reads `message`, writes `category`. It makes no reply.
- `wifi_help` / `password_help` read nothing from the decision, call `find_instructions`, write `reply`.
- `other_help` writes a `reply` that asks whether the issue is Wi-Fi or a password.

### The four questions

1. **What does each node read and change?** `read_request` reads `message` and writes `category`.
   The help nodes write `reply`. Only `read_request` classifies, only the help nodes answer.
2. **Node update vs conditional edge.** A node returns a partial state update (a dict that is merged
   into the state). A conditional edge returns no data, it returns the *name of the next node*. In my
   graph `read_request` returns `{"category": ...}` (data), and the function `_route` returns a node
   name (`"wifi_help"`), it does not touch the state.
3. **Does the next node get only the previous update or the whole state?** The whole merged graph
   state. `wifi_help` sees `message` and `category`, not just the `{"category": ...}` that
   `read_request` produced.
4. **START, END, compile.** `START` is the virtual entry the first edge leaves from. `END` is the
   virtual exit a node points to when the run should stop. Compiling turns the node and edge
   definitions into a runnable graph (`graph.compile()`); before that it is only a description.

### Predictions before running

Run and traces: `outputs/S01.md`-`outputs/S05.md`.

| Message | Predicted route | Actual route | What I learned |
| --- | --- | --- | --- |
| I cannot connect to Wi-Fi. | wifi_help | read_request -> wifi_help | Matches. |
| I forgot my PASSWORD. | password_help | read_request -> password_help | Case is ignored, routing is lower-cased. |
| My laptop screen is broken. | other_help | read_request -> other_help | No keyword, so the default branch. |
| My Wi-Fi password does not work. | wifi_help | read_request -> wifi_help | Both words appear, but the `wifi` rule is checked first, so `password` never runs. |

The both-topics result is caused by rule order in `_classify`: `wifi` is tested before `password`,
so a message with both goes to `wifi_help`.

### My change to the graph

Changed graph (`build_graph(with_clarification=True)`):

```
START -> read_request -> |- "wifi"     -> wifi_help       -> END
                         |- "password" -> password_help   -> END
                         |- "both"     -> clarify_problem  -> END
                         |- "other"    -> other_help       -> END
```

`read_request` now returns `"both"` when `mentions_both_topics` is true, and the new
`clarify_problem` node asks which problem to solve first. Trace (`outputs/S05.md`):
`read_request -> clarify_problem`, `category = both`. This is a different path through the graph,
not a different sentence from the same help node.

**What LangGraph controls vs my functions.** LangGraph owns the control flow: it runs `read_request`,
calls the routing function, follows the chosen edge, merges each node's update into the state, and
stops at `END`. My Python decides the content: how to classify a message, which instructions to
return, and what text to reply. No model makes any decision in this part.

## Part 2 - Model and tools

### The loop

```
START -> remember -> agent --(tool_calls?)--> tools -> agent -> ... -> END
                       |                                   ^
                       |--------- no tool_calls -----------|-> END
```

- `agent` calls the model with a system prompt plus the conversation. The model answers with text,
  or with one or more tool requests.
- The conditional edge `route` (`helpdesk/agent.py`) sends the run to `tools` when the last message
  has `tool_calls`, otherwise to `END`.
- `tools` is a LangGraph `ToolNode`. It executes the requested tools and appends the results, then
  control returns to `agent`, which sees the results and either requests more tools or answers.

### The four questions

1. **Run a tool or end?** The `route` function checks whether the model's last message carries
   `tool_calls`. Tool calls present -> `tools`, otherwise -> `END`.
2. **Who requests vs who executes?** The model (in `agent`) *requests* a tool by name and arguments.
   My program (the `ToolNode` in `tools`) *executes* the real Python function. The model never runs
   code.
3. **What changes in the state after a tool result?** A `ToolMessage` with the result is appended to
   `state["messages"]`. The next `agent` call reads it and conditions its answer on it.
4. **Difference from Part 1.** In Part 1 the branch is fixed by my `if/elif` rules. In Part 2 the
   branch is decided at run time by the model from the conversation and the tool results, so the same
   request can lead to different actions.

### The three tools (callable directly)

Each tool is a plain function in `helpdesk/tools.py` and is tested without the agent
(`tests/test_tools.py`):

- `find_instructions(topic)` - returns the local guide and its `instruction_id`.
- `check_service_status(service, profile)` - returns the status for the selected snapshot.
- `prepare_ticket(...)` - writes a local `TCK-*.json` draft from the template and rejects secrets.

### A run that uses several tools

`outputs/S06.md` (fake) and `outputs/real/S06.md` (real `gpt-4o-mini`). Second message:
"Check whether Wi-Fi is down. If it is operating, prepare a ticket." The model calls
`check_service_status`, sees `operational`, then calls `prepare_ticket`. Nodes:
`remember -> agent -> tools -> agent -> tools -> agent`. The same request during `wifi_outage`
(`outputs/S07.md`) checks the status, sees the outage, and does **not** prepare a ticket. During
`status_unavailable` (`outputs/S08.md`) it reports the status is unknown and offers a draft instead.
This shows the action depends on the tool result, not on a fixed rule.

### The loop limit

Enforced in `route` (`helpdesk/agent.py`). It counts the model messages that carried tool calls and
stops at `MAX_TOOL_LOOPS = 4`, so the model-tool cycle cannot run forever. A compile-time
`recursion_limit` is also passed as a second backstop. The `loop_limit_reached` flag is saved in each
trace.

## Part 3 - Memory

- **Conversation memory** is the message history per `thread_id`, saved by a LangGraph SQLite
  checkpointer (`local-storage/conversations.sqlite`). On each call the graph loads the saved state,
  appends the new message, and saves again, so recall survives a restart.
- **User memory** is a saved preference per `user_id` in my own SQLite table
  (`local-storage/user_memory.sqlite`, `UserMemory`). The `remember` node writes it when a message
  states a preference, the `agent` node reads it into the system prompt.

`thread_id` identifies one conversation. `user_id` identifies the person. One user can have many
threads. A new thread starts with empty conversation history, but the same user's saved preference is
still available. The application sets both ids, the model never chooses whose data to load.

Looking up Wi-Fi instructions is **retrieval**: the same reference file is read fresh every time,
independent of who asks. Recalling the chosen language is **memory**: it was learned from an earlier
message by a specific user and stored for later.

| Situation | Command used | Log file | What happened |
| --- | --- | --- | --- |
| Refer to an earlier message | `runner --only S10` | `outputs/S10.md` | Second message "Which steps did I already try?" is answered from the saved thread (prior messages read: 2). |
| Close, restart and resume | `runner --only S11` | `outputs/S11.md` | After a real process restart, thread `restart-a` recalls the Wi-Fi problem and steps, in Kazakh. |
| Same user, new conversation | `runner --only S12` | `outputs/S12.md` | New thread `preference-a2` has no history (prior messages: 0) but reads the saved Kazakh preference. |
| Different user | `runner --only S13` | `outputs/S13.md` | `demo-user-b` has no preference and no prior problem. The first user's data does not appear. |

## Part 4 - Running and checking my work

- Setup, exact run commands, Python version, memory location and reset: see `README.md`.
- Pinned versions: `requirements.txt` (langgraph 1.2.20, langchain-core 1.7.6, langchain-openai 1.7.4,
  langgraph-checkpoint-sqlite 3.1.3, python-dotenv 1.2.4, pytest 9.2.0). Developed on Python 3.15,
  CI on 3.12.
- Tests (`tests/`) and what each catches:
  - `test_routing.py` - a broken classifier or edge would send a message to the wrong help node, or
    break the both-topics rule.
  - `test_tools.py` - a tool returning the wrong guide/status, not writing the draft, or leaking a
    secret into a ticket.
  - `test_memory.py` - conversation state not persisting across a restart, or a preference not
    surviving into a new thread.
  - `test_users.py` - one user's preference leaking to another user.
- CI: `.github/workflows/ci.yml` runs the tests on every push/pull request with no API key, using the
  fake model. The real-model run is kept out of CI.

## Choices and limitations

- **Storage.** The LangGraph SQLite checkpointer for conversation state, because it is the supported
  persistence layer and survives a restart. A separate small SQLite table for user preferences, to
  keep user memory and conversation memory cleanly apart and keyed differently (`user_id` vs
  `thread_id`).
- **Fake model.** A deterministic rule-based model drives the same graph as the real one, so Part 1,
  the tools and all memory behaviour are reproducible and CI needs no key. It is clearly not an LLM
  and is labelled as such.
- **Limitations.** The fake model understands the demonstration phrasings, not arbitrary language.
  Step extraction is keyword based, so unusual wording may miss a step. The real model's exact
  wording varies between runs, only the tool decisions are constrained by the system prompt.

## Supplied scenarios - my actual results

Fake-model logs in `outputs/`, real-model logs for the Part 2 cases in `outputs/real/`.
Command prefix: `python -m helpdesk.runner --only <id>`.

| Scenario | Command or manual steps | Log file | What happened / what I changed |
| --- | --- | --- | --- |
| S01 - Simple Wi-Fi route | `runner --only S01` | `outputs/S01.md` | `read_request -> wifi_help`, Wi-Fi guide returned. |
| S02 - Case-insensitive password route | `runner --only S02` | `outputs/S02.md` | `PASSWORD` lower-cased, `read_request -> password_help`. |
| S03 - Unsupported request | `runner --only S03` | `outputs/S03.md` | No keyword, `other_help` asks Wi-Fi or password. |
| S04 - Two topics before the change | `runner --only S04` | `outputs/S04.md` | Original graph, `wifi` rule wins, routes to `wifi_help`. |
| S05 - Two topics after clarification | `runner --only S05` | `outputs/S05.md` | Changed graph, `category=both`, `clarify_problem` asks which first. |
| S06 - Instructions then local ticket | `runner --only S06` | `outputs/S06.md`, `outputs/real/S06.md` | Instructions, status `operational`, ticket draft saved. |
| S07 - Same request during Wi-Fi outage | `runner --only S07` | `outputs/S07.md`, `outputs/real/S07.md` | Status `outage`, no ticket, no repair time invented. |
| S08 - Status source unavailable | `runner --only S08` | `outputs/S08.md`, `outputs/real/S08.md` | Status `unknown`, no ticket, offers a draft noting the status could not be checked. |
| S09 - Missing ticket details | `runner --only S09` | `outputs/S09.md` | First asks for problem and steps, then drafts with `service_status = not checked`. |
| S10 - Use the current conversation | `runner --only S10` | `outputs/S10.md` | Recalls the steps from the same thread. |
| S11 - Persist and recall after restart | `runner --only S11` | `outputs/S11.md` | New process, same storage, recalls problem and steps in Kazakh. |
| S12 - Preference across threads without replay | `runner --only S12` | `outputs/S12.md` | New thread, no history, Kazakh preference still read. |
| S13 - Do not share memory between users | `runner --only S13` | `outputs/S13.md` | `demo-user-b` sees none of `demo-user-a`'s data. |
| S14 - Password recovery outage | `runner --only S14` | `outputs/S14.md`, `outputs/real/S14.md` | Looks up `account_recovery`, reports the known outage, no repair time. |
