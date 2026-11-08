import json

import pytest

from helpdesk import tools


def test_find_instructions_wifi():
    result = tools.find_instructions("wifi")
    assert result["found"] is True
    assert result["instruction_id"] == "GUIDE-WIFI"
    assert len(result["steps"]) == 4


def test_find_instructions_password_alias():
    assert tools.find_instructions("password")["instruction_id"] == "GUIDE-PASSWORD"


def test_find_instructions_unknown_topic():
    result = tools.find_instructions("printer")
    assert result["found"] is False


@pytest.mark.parametrize(
    "profile, service, status",
    [
        ("normal", "wifi", "operational"),
        ("wifi_outage", "wifi", "outage"),
        ("recovery_outage", "account_recovery", "outage"),
        ("status_unavailable", "wifi", "unknown"),
    ],
)
def test_check_service_status(profile, service, status):
    result = tools.check_service_status(service, profile)
    assert result["status"] == status
    assert result["is_known"] is (status != "unknown")


def test_prepare_ticket_writes_local_draft(storage):
    result = tools.prepare_ticket(
        category="wifi",
        summary="Wi-Fi fails on Campus-Demo.",
        steps_tried=["Enabled Wi-Fi", "Tried reconnecting"],
        service_status="operational",
        status_profile="normal",
        user_id="demo-user-a",
        thread_id="t1",
        storage_dir=storage,
    )
    assert result["saved"] is True
    saved = json.loads((storage / "tickets" / f"{result['ticket']['ticket_id']}.json").read_text())
    assert saved["status"] == "draft"
    assert saved["steps_tried"] == ["Enabled Wi-Fi", "Tried reconnecting"]


def test_prepare_ticket_rejects_secrets(storage):
    with pytest.raises(ValueError):
        tools.prepare_ticket(
            category="password",
            summary="My password is hunter2",
            steps_tried=[],
            storage_dir=storage,
        )
