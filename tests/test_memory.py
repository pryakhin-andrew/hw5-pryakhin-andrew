from helpdesk.session import run_agent_message


def _send(message, *, user, thread, storage, profile="normal"):
    return run_agent_message(
        user_id=user,
        thread_id=thread,
        profile=profile,
        message=message,
        backend="fake",
        storage_dir=storage,
    )


def test_conversation_recall_after_restart(storage):
    _send(
        "My issue is Wi-Fi. I enabled it and tried reconnecting, but it still fails.",
        user="demo-user-a",
        thread="restart-a",
        storage=storage,
    )
    second = _send(
        "Which problem and steps did we discuss?",
        user="demo-user-a",
        thread="restart-a",
        storage=storage,
    )
    assert second["prior_messages"] >= 2
    assert "Wi-Fi" in second["reply"] or "Wi" in second["reply"]
    assert "Enabled Wi-Fi" in second["reply"]


def test_preference_persists_across_threads(storage):
    _send(
        "Please remember that I prefer replies in Kazakh. I have a Wi-Fi problem.",
        user="demo-user-a",
        thread="pref-a1",
        storage=storage,
    )
    later = _send(
        "Which language did I ask you to use?",
        user="demo-user-a",
        thread="pref-a2",
        storage=storage,
    )
    assert later["preferred_language"] == "Kazakh"
    assert later["prior_messages"] == 0


def test_new_thread_has_no_conversation_history(storage):
    _send("I have a Wi-Fi problem.", user="demo-user-a", thread="thread-1", storage=storage)
    other = _send("Hello", user="demo-user-a", thread="thread-2", storage=storage)
    assert other["prior_messages"] == 0
