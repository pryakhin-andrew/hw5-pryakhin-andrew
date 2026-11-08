from helpdesk.memory import UserMemory, user_memory_path
from helpdesk.session import run_agent_message


def _send(message, *, user, thread, storage):
    return run_agent_message(
        user_id=user,
        thread_id=thread,
        profile="normal",
        message=message,
        backend="fake",
        storage_dir=storage,
    )


def test_preference_not_shared_between_users(storage):
    _send(
        "Please remember that I prefer replies in Kazakh. I have a Wi-Fi problem.",
        user="demo-user-a",
        thread="isolation-a",
        storage=storage,
    )
    other = _send(
        "Have I told you a preferred language or a previous problem?",
        user="demo-user-b",
        thread="isolation-b",
        storage=storage,
    )
    assert other["preferred_language"] is None
    assert "No preferred language" in other["reply"]


def test_user_memory_store_isolates_users(storage):
    memory = UserMemory(user_memory_path(storage))
    memory.set("demo-user-a", "language", "Kazakh")
    assert memory.get("demo-user-a", "language") == "Kazakh"
    assert memory.get("demo-user-b", "language") is None
