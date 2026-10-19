import socket
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network is forbidden in offline tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def project():
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def live_eval_stage(tmp_path_factory):
    """Publish the 100-game fixture once per session. No model and no download."""
    from chess_analytics.analyst.live_eval import stage_live_fixture

    root = Path(__file__).resolve().parents[1]
    return stage_live_fixture(root, tmp_path_factory.mktemp("live-eval-100"))
