"""A real local-model smoke check; no external player API is called."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.domain import Puzzle, parse_action
from app.judge import LayaJudge


def main():
    puzzle = Puzzle(
        surface="一个人走进酒吧要了一杯水。酒保却拿枪对着他，他说了声谢谢就离开了。为什么？",
        bottom="这个人正在打嗝，想喝水止嗝。酒保看出他在打嗝，故意用枪吓唬他。惊吓使他停止打嗝，所以他感谢酒保，不再需要喝水就离开了。",
    )
    question = parse_action("他是因为打嗝才想喝水，酒保用枪吓唬他，让他停止打嗝，所以他道谢后没喝水就走了吗？")
    result = LayaJudge().evaluate(puzzle, question, [], {})
    print(json.dumps({
        "reply": result["reply"],
        "stage": result["progress"]["stage"],
        "solved": result["solved"],
        "device": result["device"],
        "judge_ms": result["judge_ms"],
    }, ensure_ascii=False, indent=2))
    if not result["solved"]:
        raise SystemExit("The pinned-checkpoint smoke example was not recognized as complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
