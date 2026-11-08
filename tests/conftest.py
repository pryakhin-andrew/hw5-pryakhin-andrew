import pytest


@pytest.fixture
def storage(tmp_path):
    return tmp_path / "store"
