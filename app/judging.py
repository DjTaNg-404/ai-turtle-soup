"""Shared game judgments with separate question and confirmed-evidence contexts."""
from __future__ import annotations
import time
from .domain import LABELS, Puzzle, PlayerAction


class JudgeError(Exception):
    pass


def confirmed_evidence(rounds, action, answer):
    """Keep affirmed originals across the whole game, without rewriting negations."""
    records = []
    for number, turn in enumerate(rounds, 1):
        verdict = turn.get("verdict", {}).get("choice")
        kind = turn["action"]["kind"]
        # Old exports without structured verdicts can still carry a literal yes reply.
        if verdict == "yes" or (kind == "solution" and verdict == "correct") or (
            verdict is None and turn.get("reply") == "是"
        ):
            records.append((turn.get("number", number), turn["action"]["text"], kind))
    if answer["choice"] == "yes" or (action.kind == "solution" and answer["choice"] == "correct"):
        records.append((len(rounds) + 1, action.text, action.kind))
    return records


class DecisionJudge:
    def fits(self, state, instructions, criteria):
        return True

    def evaluate(self, puzzle: Puzzle, action: PlayerAction, rounds, progress):
        self.load()
        with self.lock:
            start = time.perf_counter()
            if action.kind == "question":
                answer = self.predict(
                    {"story": puzzle.surface, "truth": puzzle.bottom, "question": action.text},
                    "Based only on the story truth, answer the player's current yes/no question. Read negations carefully. Undocumented irrelevant details are unknown.",
                    {"yes": "是。The proposition is supported by the truth.",
                     "no": "不是。The proposition contradicts the truth.",
                     "irrelevant": "无关。The detail is irrelevant or unspecified by the story."})
                reply = LABELS[answer["choice"]]
            else:
                # Keep old solution actions from bypassing the affirmative-only context.
                answer = self.predict(
                    {"story": puzzle.surface, "truth": puzzle.bottom, "player_solution": action.text},
                    "Does the player's proposed solution correctly explain the story's central cause and outcome? Check for contradictions.",
                    {"correct": "The solution correctly explains the essential cause and outcome.",
                     "incomplete": "The solution is missing an essential cause or outcome.",
                     "contradicted": "The solution contains a factual contradiction."})
                reply = "解答尚未完整"

            confirmed = confirmed_evidence(rounds, action, answer)
            if confirmed:
                evidence = [
                    f"玩家问：{text}\n裁判答：是" if kind == "question"
                    else f"玩家解答：{text}\n裁判答：正确"
                    for _, text, kind in confirmed
                ]
                state = {"premise": "\n".join(evidence), "hypothesis": puzzle.bottom}
                instructions = (
                    "The premise contains only propositions confirmed by affirmative answers. "
                    "Preserve negations in the original questions. Do these confirmed propositions "
                    "jointly reconstruct the hypothesis's core events, cause and outcome? "
                    "Being true or consistent is insufficient. Do not fill gaps using the hypothesis."
                )
                criteria = {
                    "complete": "entailment: confirmed propositions jointly cover the core events, cause and outcome",
                    "partial": "neutral: part of the core explanation is still missing",
                    "conflict": "contradiction: the confirmed propositions conflict with the story truth"}
                if not self.fits(state, instructions, criteria):
                    raise JudgeError(
                        f"通关判定的累计 {len(confirmed)} 条肯定记录与汤底超出当前主持人的输入上限。"
                        "历史记录和当前问题已保留，未删减早期线索；请切换支持更长输入的主持人后重试。"
                    )
                stage_check = self.predict(state, instructions, criteria)
            else:
                # Zero affirmative evidence cannot establish the hidden solution.
                stage_check = {"choice": "partial", "probabilities": {}}

            solved = answer["choice"] in {"correct", "yes"} and stage_check["choice"] == "complete"
            labels = {"partial": "继续探索", "complete": "已还原" if solved else "可能还原", "conflict": "存在矛盾"}
            stage = stage_check["choice"]
            progress_result = {
                "stage": stage,
                "label": labels[stage] if confirmed else "尚无肯定线索",
                "probabilities": stage_check["probabilities"],
                "evidence_source": "affirmed_questions",
                "confirmed_count": len(confirmed),
                "confirmed_rounds": [number for number, _, _ in confirmed],
                "window_rounds": len(confirmed),  # Compatibility; new UI uses confirmed_count.
                "submitted_solution": action.kind == "solution",
            }
            if action.kind == "solution":
                reply = "通关，解答正确" if solved else "解答与汤底存在矛盾" if answer["choice"] == "contradicted" or stage == "conflict" else "解答尚未完整，请继续提问"
            return {"reply": reply, "verdict": answer, "progress": progress_result, "solved": solved,
                    "judge_ms": round((time.perf_counter()-start)*1000), "device": self.device}
