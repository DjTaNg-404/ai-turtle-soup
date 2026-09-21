import copy
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.domain import LABELS, PlayerAction, Puzzle, parse_action, player_messages
from app.judging import DecisionJudge, JudgeError
from app.server import create_app


PUZZLE = Puzzle(surface="一个人要水，却没有喝水就道谢离开了。", bottom="HIDDEN：他打嗝，服务员吓好了他，因此不再需要水。")


def turn(number, text, verdict, kind="question"):
    return {"number": number, "action": {"kind": kind, "text": text},
            "verdict": {"choice": verdict, "probabilities": {"INTERNAL": 1}},
            "reply": LABELS.get(verdict, "正确" if verdict == "correct" else "解答不完整")}


class RecordingJudge(DecisionJudge):
    def __init__(self, answer="yes", stage="partial", fits=True):
        self.answer, self.stage, self.accepts_context = answer, stage, fits
        self.calls, self.contexts = [], []
        self.lock = threading.Lock()
        self.device = "test"

    def status(self):
        return {"ready": True}

    def load(self):
        return self.status()

    def fits(self, state, instructions, criteria):
        self.contexts.append(copy.deepcopy(state))
        return self.accepts_context

    def predict(self, state, instructions, criteria):
        self.calls.append((copy.deepcopy(state), instructions, dict(criteria)))
        choice = self.stage if "complete" in criteria else self.answer
        return {"choice": choice, "probabilities": {choice: 1}}


def test_separate_contexts_keep_all_affirmed_rounds_and_original_negations():
    history = [turn(1, "这个人并没有喝水，对吗？", "yes")]
    history += [turn(n, f"早期已确认问题{n}？", "yes") for n in range(2, 13)]
    history += [turn(13, "BAD_NO：他自杀了吗？", "no"),
                turn(14, "BAD_IR：衣服是红色的吗？", "irrelevant")]
    current = parse_action("服务员大喊是为了帮这个人止嗝吗？")
    judge = RecordingJudge()
    result = judge.evaluate(PUZZLE, current, history, {})
    question_state = judge.calls[0][0]
    assert question_state == {"story": PUZZLE.surface, "truth": PUZZLE.bottom, "question": current.text}
    stage_state = judge.calls[1][0]
    assert set(stage_state) == {"premise", "hypothesis"}
    assert stage_state["hypothesis"] == PUZZLE.bottom
    for row in history[:12]:
        assert row["action"]["text"] in stage_state["premise"]
    assert current.text in stage_state["premise"]
    assert all(word not in stage_state["premise"] for word in ["BAD_NO", "BAD_IR", "INTERNAL", "HIDDEN"])
    assert result["progress"]["confirmed_count"] == 13
    assert result["progress"]["confirmed_rounds"] == list(range(1, 13)) + [15]
    assert "Being true or consistent is insufficient" in judge.calls[1][1]

    messages = player_messages(PUZZLE, history)
    assert [m["content"] for m in messages if m["role"] == "assistant"] == [r["action"]["text"] for r in history]
    for label in ["裁判：是", "裁判：不是", "裁判：无关"]:
        assert any(m["content"] == label for m in messages)
    assert "裁判回答当前问题时不看历史对话" in messages[0]["content"]
    assert all(PUZZLE.bottom not in m["content"] for m in messages)


@pytest.mark.parametrize("answer", ["no", "irrelevant"])
def test_no_affirmative_evidence_skips_completion_without_inventing_probabilities(answer):
    judge = RecordingJudge(answer=answer, stage="complete")
    result = judge.evaluate(PUZZLE, parse_action("这个人是在买酒吗？"), [], {"stage": "complete"})
    assert len(judge.calls) == 1
    assert not result["solved"]
    assert result["progress"]["confirmed_count"] == 0
    assert result["progress"]["stage"] == "partial"
    assert result["progress"]["probabilities"] == {}


@pytest.mark.parametrize("answer", ["no", "irrelevant"])
def test_rejected_current_question_never_enters_completion_context(answer):
    judge = RecordingJudge(answer=answer, stage="complete")
    history = [turn(1, "这个人正在打嗝吗？", "yes")]
    result = judge.evaluate(PUZZLE, parse_action("CURRENT_REJECTED"), history, {})
    assert len(judge.calls) == 2
    assert "CURRENT_REJECTED" not in judge.calls[1][0]["premise"]
    assert result["progress"]["confirmed_rounds"] == [1]
    assert not result["solved"]


def test_legacy_solutions_only_contribute_after_confirmation():
    history = [turn(1, "ACCEPTED_SOLUTION", "correct", "solution"),
               turn(2, "REJECTED_SOLUTION", "contradicted", "solution")]
    judge = RecordingJudge(answer="incomplete")
    result = judge.evaluate(PUZZLE, PlayerAction(kind="solution", text="CURRENT_UNCONFIRMED"), history, {})
    evidence = judge.calls[1][0]["premise"]
    assert "ACCEPTED_SOLUTION" in evidence
    assert "REJECTED_SOLUTION" not in evidence and "CURRENT_UNCONFIRMED" not in evidence
    assert result["progress"]["confirmed_rounds"] == [1]
    assert not result["solved"]


def test_overflow_preserves_early_evidence_instead_of_truncating_it():
    judge = RecordingJudge(fits=False)
    history = [turn(n, f"确认记录 {n}", "yes") for n in range(1, 13)]
    original = copy.deepcopy(history)
    with pytest.raises(JudgeError, match="累计 13 条肯定记录"):
        judge.evaluate(PUZZLE, parse_action("新问题"), history, {})
    assert len(judge.calls) == 1
    assert len(judge.contexts) == 1
    assert all(row["action"]["text"] in judge.contexts[0]["premise"] for row in history)
    assert history == original


def test_overflow_retry_does_not_repeat_player_call(tmp_path):
    class Player:
        calls = 0

        async def next(self, config, puzzle, rounds):
            self.calls += 1
            return parse_action("这个人正在打嗝吗？"), {}

    def wait(client, sid):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            data = client.get("/api/games/" + sid).json()
            if not data["busy"]:
                return data
            time.sleep(0.01)
        raise AssertionError("Game is still running")

    judge, player = RecordingJudge(fits=False), Player()
    with TestClient(create_app(judge=judge, player=player, data_dir=tmp_path / "runs")) as client:
        client.post("/api/config", json={"model": "test-player"})
        sid = client.post("/api/games", json={"puzzle": PUZZLE.model_dump(), "run": True}).json()["id"]
        failed = wait(client, sid)
        assert failed["status"] == "error" and failed["pending"] and not failed["rounds"]
        assert "未删减早期线索" in failed["error"]
        judge.accepts_context = True
        client.post(f"/api/games/{sid}/control", json={"action": "step"})
        restored = wait(client, sid)
        assert restored["status"] == "paused" and len(restored["rounds"]) == 1
        assert restored["progress"]["confirmed_rounds"] == [1]
        assert player.calls == 1
