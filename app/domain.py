from __future__ import annotations
import json
import re
from urllib.parse import urlsplit, urlunsplit
from typing import Literal
from pydantic import BaseModel, Field, SecretStr, field_validator

LABELS = {"yes": "是", "no": "不是", "irrelevant": "无关"}

class PlayerConfig(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    api_key: SecretStr = SecretStr("")
    timeout: int = Field(default=180, ge=10, le=600)

    @field_validator("base_url")
    @classmethod
    def url_valid(cls, value):
        p = urlsplit(value.strip())
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password or p.query or p.fragment:
            raise ValueError("请填写 HTTP(S) API 地址，不要在地址中包含密钥、参数或账号。")
        return value.strip().rstrip("/")

    def endpoint(self):
        p = urlsplit(self.base_url)
        path = p.path.rstrip("/")
        if not path:
            path = "/v1"
        if not path.endswith("/chat/completions"):
            path += "/chat/completions"
        return urlunsplit((p.scheme, p.netloc, path, "", ""))

    def public(self):
        return {"base_url": self.base_url, "model": self.model, "has_key": bool(self.api_key.get_secret_value()),
                "timeout": self.timeout}

class JudgeConfig(PlayerConfig):
    provider: Literal["laya", "jev"] = "laya"
    base_url: str = "https://api.typesafe.ai/v1/systemone"
    model: str = "jev-latest"

    def endpoint(self):
        p = urlsplit(self.base_url)
        path = p.path.rstrip("/") or "/v1"
        if not path.endswith("/systemone"):
            path += "/systemone"
        return urlunsplit((p.scheme, p.netloc, path, "", ""))

    def public(self):
        return {**super().public(), "provider": self.provider}

    def identity(self):
        return {"provider": self.provider,
                "name": "Laya Multilingual" if self.provider == "laya" else "Jev",
                "model": "multilingual" if self.provider == "laya" else self.model}


class Puzzle(BaseModel):
    title: str = Field(default="未命名的汤", max_length=80)
    surface: str = Field(min_length=2, max_length=2000)
    bottom: str = Field(min_length=2, max_length=3000)
    max_rounds: int = Field(default=20, ge=1, le=50)
    @field_validator("surface", "bottom")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("汤面和汤底不能为空")
        return value.strip()

class PlayerAction(BaseModel):
    kind: str
    text: str = Field(min_length=1)
    @field_validator("kind")
    @classmethod
    def valid_kind(cls, value):
        if value not in {"question", "solution"}:
            raise ValueError("玩家动作必须为 question 或 solution")
        return value
    @field_validator("text")
    @classmethod
    def strip_text(cls, value):
        if not value.strip():
            raise ValueError("玩家返回了空问题")
        return value.strip()

def parse_action(content: str) -> PlayerAction:
    """Accept ordinary conversation; tolerate old saved JSON-format answers."""
    text = content.strip()
    candidate = re.sub(r"^```(?:json)?\s*", "", text)
    candidate = re.sub(r"\s*```$", "", candidate)
    try:
        obj = json.loads(candidate)
    except (ValueError, TypeError):
        obj = None
    if isinstance(obj, dict) and obj.get("kind") in {"question", "solution"} and isinstance(obj.get("text"), str) and obj["text"].strip():
        return PlayerAction(kind=obj["kind"], text=obj["text"])
    return PlayerAction(kind="question", text=text)

PLAYER_RULES = '''我们正在玩海龟汤，你是玩家。你只知道汤面，裁判知道汤底。
根据汤面和此前的问答，每次只问一个问题，裁判会回答“是 / 不是 / 无关”。尽量不要重复已经确认的事情。
裁判回答当前问题时不看历史对话。每个问题请说清具体人物和事件，让它结合汤面即可独立理解，避免“所以是这样吗”等依赖上一轮的表达。
如果你认为已经猜出了汤底，就用一个完整的问题说出你猜到的经过和原因，请裁判确认。'''

def player_messages(puzzle: Puzzle, rounds: list[dict]):
    # Deliberate allowlist. Never serialize the puzzle/session object into a player request.
    messages = [{"role": "system", "content": PLAYER_RULES},
                {"role": "user", "content": "汤面：\n" + puzzle.surface + f"\n最多 {puzzle.max_rounds} 轮。请开始。"}]
    for turn in rounds:
        messages.append({"role": "assistant", "content": turn["action"]["text"]})
        reply = turn["reply"]
        messages.append({"role": "user", "content": f"裁判：{reply}"})
    if rounds:
        messages.append({"role": "user", "content": f"当前第 {len(rounds)+1}/{puzzle.max_rounds} 轮。请问下一个问题。"})
    return messages
