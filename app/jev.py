"""TypeSafe Jev native System One API adapter. No chat-completion coercion."""
from __future__ import annotations

import math
import threading
import httpx

from .domain import JudgeConfig
from .judging import DecisionJudge, JudgeError


def parse_choice(data, criteria):
    try:
        answer = data["answers"]["decision"]
        choice = answer["choice"]
        probabilities = answer["probabilities"]
        if choice not in criteria or set(probabilities) != set(criteria):
            raise ValueError
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not math.isfinite(v) or not 0 <= v <= 1 for v in probabilities.values()):
            raise ValueError
        if not 0.98 <= sum(probabilities.values()) <= 1.02:
            raise ValueError
        result = {"choice": choice, "probabilities": dict(probabilities)}
        confidence = answer.get("confidence")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and math.isfinite(confidence) and 0 <= confidence <= 1:
            result["confidence"] = confidence
        return result
    except (KeyError, TypeError, ValueError, AttributeError):
        raise JudgeError("Jev 响应没有有效的 answers.decision 分类结果，请检查是否使用 TypeSafe System One 兼容端点。") from None


class JevJudge(DecisionJudge):
    def __init__(self, config: JudgeConfig, transport=None):
        self.config = config.model_copy(deep=True)
        self.transport = transport
        self.lock = threading.Lock()
        self.device = "api"
        self.error = None

    def status(self):
        return {"ready": bool(self.config.model.strip()), "loading": False, "device": "api",
                "name": "Jev", "provider": "jev", "model": self.config.model,
                "error": self.error, "context": None}

    def load(self):
        if not self.config.model.strip():
            raise JudgeError("请先填写 Jev 模型名称。")
        return self.status()

    def test(self):
        return self.predict({"message": "Hello"}, "Choose ok to confirm the connection.", {"ok": "Connection test", "other": "Other"})

    def predict(self, state, instructions, criteria):
        key = self.config.api_key.get_secret_value()
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        payload = {"model": self.config.model, "state": state,
                   "questions": {"decision": {"type": "choice", "instructions": instructions, "criteria": criteria}}}
        try:
            with httpx.Client(timeout=self.config.timeout, follow_redirects=False, transport=self.transport) as client:
                response = client.post(self.config.endpoint(), headers=headers, json=payload)
        except httpx.TimeoutException:
            raise JudgeError("Jev 主持人请求超时，请重试。") from None
        except httpx.RequestError:
            raise JudgeError("无法连接 Jev 主持人，请检查 API 地址和网络。") from None
        if response.status_code != 200:
            reason = {400: "请求不被服务接受", 401: "密钥无效或已过期", 403: "没有访问权限",
                      404: "接口路径或模型名称不正确", 429: "频率或额度受限"}.get(response.status_code, "服务返回错误")
            raise JudgeError(f"Jev 主持人：HTTP {response.status_code}，{reason}。")
        try:
            data = response.json()
        except ValueError:
            raise JudgeError("Jev API 没有返回 JSON，请检查端点地址。") from None
        return parse_choice(data, criteria)


def create_judge(config: JudgeConfig):
    if config.provider == "jev":
        return JevJudge(config)
    from .judge import LayaJudge
    return LayaJudge()
