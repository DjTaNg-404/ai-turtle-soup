import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.domain import JudgeConfig, Puzzle, parse_action, player_messages
from app.jev import JevJudge, parse_choice
from app.judging import JudgeError
from app.server import create_app

PUZZLE = {"surface": "他要水却没有喝，为什么？", "bottom": "PRIVATE_BOTTOM：他打嗝，服务员吓好了他。"}
HOST_KEY = "HOST_KEY_SENTINEL"


def response(choice, options):
    return {"model": "jev-test", "answers": {"decision": {
        "type": "choice", "choice": choice, "confidence": 1,
        "probabilities": {k: int(k == choice) for k in options},
    }}}


def test_jev_native_protocol_uses_two_dependent_judgments():
    requests = []
    def upstream(request):
        assert request.headers["Authorization"] == "Bearer " + HOST_KEY
        data = json.loads(request.content)
        requests.append(data)
        options = data["questions"]["decision"]["criteria"]
        return httpx.Response(200, json=response("yes" if "yes" in options else "complete", options))
    judge = JevJudge(JudgeConfig(provider="jev", api_key=HOST_KEY), httpx.MockTransport(upstream))
    result = judge.evaluate(Puzzle(**PUZZLE), parse_action("他打嗝，服务员吓好他，所以不喝水就走了吗？"), [], {})
    assert result["solved"] and result["reply"] == "是"
    assert len(requests) == 2
    assert requests[0]["state"]["truth"] == PUZZLE["bottom"]
    assert requests[1]["state"]["hypothesis"] == PUZZLE["bottom"]
    assert "裁判答：是" in requests[1]["state"]["premise"]
    assert all(set(r) == {"model", "state", "questions"} for r in requests)
    assert HOST_KEY not in json.dumps(requests)
    assert HOST_KEY not in json.dumps(result)


@pytest.mark.parametrize("url", ["https://api.typesafe.ai", "https://api.typesafe.ai/v1", "https://api.typesafe.ai/v1/systemone"])
def test_jev_endpoint(url):
    assert JudgeConfig(provider="jev", base_url=url).endpoint() == "https://api.typesafe.ai/v1/systemone"


@pytest.mark.parametrize("payload", [
    {}, {"answers": None},
    {"answers": {"decision": {"choice": "SECRET_UNKNOWN", "probabilities": {}}}},
    {"answers": {"decision": {"choice": "yes", "probabilities": {"yes": float("nan"), "no": 0}}}},
    {"answers": {"decision": {"choice": "yes", "probabilities": {"yes": True, "no": 0}}}},
    {"answers": {"decision": {"choice": "yes", "probabilities": {"yes": 0.3, "no": 0.3}}}},
])
def test_invalid_jev_results_do_not_leak_raw_data(payload):
    with pytest.raises(JudgeError) as exc:
        parse_choice(payload, {"yes": "", "no": ""})
    assert "SECRET_UNKNOWN" not in str(exc.value)


def test_jev_errors_do_not_echo_provider_body():
    judge = JevJudge(JudgeConfig(provider="jev"), httpx.MockTransport(
        lambda request: httpx.Response(401, json={"error": "SECRET_PROVIDER_BODY"})))
    with pytest.raises(JudgeError, match="HTTP 401") as exc:
        judge.test()
    assert "SECRET_PROVIDER_BODY" not in str(exc.value)


class PlainPlayer:
    def __init__(self):
        self.calls = 0

    async def next(self, config, puzzle, rounds):
        self.calls += 1
        assert "PRIVATE_BOTTOM" not in json.dumps(player_messages(puzzle, rounds))
        return parse_action("他打嗝，服务员吓好他，所以不用喝水了吗？"), {}


def wait_idle(client, sid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        data = client.get("/api/games/" + sid).json()
        if not data["busy"]:
            return data
        time.sleep(0.01)
    raise AssertionError("Game is still running")


def test_jev_game_retry_identity_and_private_settings(tmp_path, monkeypatch):
    calls = []
    failures = [True]
    def upstream(request):
        data = json.loads(request.content)
        calls.append(data)
        if failures[0]:
            failures[0] = False
            return httpx.Response(503, text="PRIVATE_RESPONSE")
        options = data["questions"]["decision"]["criteria"]
        return httpx.Response(200, json=response("yes" if "yes" in options else "complete", options))

    monkeypatch.setattr("app.server.create_judge", lambda c: JevJudge(c, httpx.MockTransport(upstream)))
    player = PlainPlayer()
    with TestClient(create_app(player=player, data_dir=tmp_path / "runs")) as client:
        client.post("/api/config", json={"model": "player-model", "api_key": "PLAYER_KEY_SENTINEL"})
        saved = client.post("/api/judge/config", json={"provider": "jev", "api_key": HOST_KEY})
        assert saved.status_code == 200 and HOST_KEY not in saved.text
        retained = client.post("/api/judge/config", json={"provider": "jev", "keep_key": True})
        assert retained.json()["config"]["has_key"]
        sid = client.post("/api/games", json={"puzzle": PUZZLE, "run": True}).json()["id"]
        failed = wait_idle(client, sid)
        assert failed["status"] == "error" and failed["pending"]
        assert "PRIVATE_RESPONSE" not in failed["error"]
        client.post(f"/api/games/{sid}/control", json={"action": "step"})
        won = wait_idle(client, sid)
        assert won["status"] == "won" and player.calls == 1
        assert won["rounds"][0]["judge"]["provider"] == "jev"
        assert won["judge"]["name"] == "Jev"
        assert "Laya" not in won["phase"]
        for path in tmp_path.rglob("*.json"):
            assert HOST_KEY not in path.read_text() and "PLAYER_KEY_SENTINEL" not in path.read_text()
        replaced = client.post("/api/judge/config", json={"provider": "jev", "base_url": "https://new.example/v1", "keep_key": True})
        assert not replaced.json()["config"]["has_key"]
    with TestClient(create_app(data_dir=tmp_path / "runs")) as client:
        config = client.get("/api/status").json()["judge_config"]
        assert config["provider"] == "jev" and not config["has_key"]
        assert client.get("/api/games/" + sid).json()["judge"]["name"] == "Jev"


def test_host_cannot_change_during_a_round(tmp_path):
    class SlowPlayer(PlainPlayer):
        async def next(self, config, puzzle, rounds):
            await asyncio.sleep(0.1)
            return await super().next(config, puzzle, rounds)
    class NoDownloadJudge:
        def load(self):
            return self.status()
        def status(self):
            return {"ready": True}
        def evaluate(self, *args):
            raise JudgeError("test stop")
    with TestClient(create_app(judge=NoDownloadJudge(), player=SlowPlayer(), data_dir=tmp_path / "runs")) as client:
        client.post("/api/config", json={"model": "player"})
        sid = client.post("/api/games", json={"puzzle": PUZZLE, "run": True}).json()["id"]
        assert client.post("/api/judge/config", json={"provider": "jev"}).status_code == 409
        wait_idle(client, sid)
