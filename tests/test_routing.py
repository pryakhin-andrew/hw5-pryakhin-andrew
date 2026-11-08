import pytest

from helpdesk.session import run_part1


@pytest.mark.parametrize(
    "message, expected",
    [
        ("I cannot connect to Wi-Fi.", "wifi_help"),
        ("I forgot my PASSWORD.", "password_help"),
        ("My laptop screen is broken.", "other_help"),
        ("My Wi-Fi password does not work.", "wifi_help"),
    ],
)
def test_original_graph_routes(message, expected):
    result = run_part1(message, with_clarification=False)
    assert result["nodes"] == ["read_request", expected]


def test_both_topics_goes_to_wifi_in_original():
    result = run_part1("My Wi-Fi password does not work.", with_clarification=False)
    assert result["category"] == "wifi"


def test_both_topics_goes_to_clarify_in_changed_graph():
    result = run_part1("My Wi-Fi password does not work.", with_clarification=True)
    assert result["nodes"] == ["read_request", "clarify_problem"]
    assert result["category"] == "both"


def test_case_insensitive_routing():
    result = run_part1("I FORGOT MY password", with_clarification=False)
    assert result["nodes"][-1] == "password_help"
