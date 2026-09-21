"""Chat Completions adapter. Reasoning content is never used as a player action."""
from __future__ import annotations
import httpx
from .domain import PlayerConfig, parse_action, player_messages


class PlayerError(Exception):
    pass


def request_payload(config: PlayerConfig, messages) -> dict:
    # Let the provider choose its normal output budget and reasoning behavior.
    # The game is expressed in the prompt, not through a forced response schema.
    return {"model": config.model, "messages": messages, "stream": False}


def content_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for block in value:
            if not isinstance(block, dict) or block.get("type") not in {"text", "output_text"}:
                continue
            text = block.get("text")
            if isinstance(text, dict):
                text = text.get("value")
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return ""


def extract_completion(data) -> tuple[str, dict]:
    """Normalize final-answer blocks and diagnose empty/truncated responses safely.

    Never echo upstream bodies, refusal messages, reasoning or credentials.
    """
    if not isinstance(data, dict):
        raise PlayerError("API 返回的 JSON 不是 Chat Completions 响应对象。")
    if data.get("error"):
        raise PlayerError("API 在响应中返回了错误。请检查服务状态、模型权限或账户额度。")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise PlayerError("API 响应缺少 choices。请使用 Chat Completions 兼容端点，而不是 Responses 或 Messages 端点。")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise PlayerError("API 响应缺少 message。当前请求需要非流式 Chat Completions 响应。")
    finish = choice.get("finish_reason")
    reasoning_only = bool(message.get("reasoning_content") or message.get("reasoning"))
    text = content_text(message.get("content")).strip()
    if finish in {"length", "max_tokens"} and not text:
        raise PlayerError("服务在生成正式回答之前就达到了自身输出上限。请重试；应用未设置 token 限额。")
    if finish == "content_filter" or message.get("refusal"):
        raise PlayerError("模型拒绝了这次请求，或输出被服务过滤。可以调整汤面后重试。")
    if not text:
        if reasoning_only:
            raise PlayerError("API 只返回了思考内容，此次没有收到正式回答，请重试。")
        if message.get("tool_calls") or finish == "tool_calls":
            raise PlayerError("模型返回了工具调用，没有普通文字回答。请检查 API 网关是否强制启用了工具。")
        raise PlayerError("API 返回了空的最终回答。请重试；若持续出现，请检查模型设置或 API 网关。")
    raw_usage = data.get("usage")
    usage = {k: v for k, v in raw_usage.items()
             if k in {"prompt_tokens", "completion_tokens", "total_tokens"} and isinstance(v, int) and not isinstance(v, bool)} if isinstance(raw_usage, dict) else {}
    return text, usage


class APIPlayer:
    def __init__(self, transport=None):
        self.transport = transport

    async def request(self, config: PlayerConfig, messages) -> tuple[str, dict]:
        headers = {"Content-Type": "application/json"}
        key = config.api_key.get_secret_value()
        if key:
            headers["Authorization"] = "Bearer " + key
        try:
            async with httpx.AsyncClient(timeout=config.timeout, follow_redirects=False, transport=self.transport) as client:
                response = await client.post(config.endpoint(), headers=headers, json=request_payload(config, messages))
        except httpx.TimeoutException:
            raise PlayerError(f"玩家 API 在 {config.timeout} 秒内没有响应，请稍后重试。") from None
        except httpx.RequestError:
            raise PlayerError("无法连接玩家 API，请检查地址、代理和网络。") from None
        if response.status_code != 200:
            reason = {401: "密钥无效或已过期", 403: "没有访问权限", 404: "接口路径或模型名称不正确",
                      429: "频率或额度受限", 400: "请求参数不被服务接受，请确认地址和模型支持 Chat Completions"}.get(response.status_code, "服务返回错误")
            raise PlayerError(f"玩家 API：HTTP {response.status_code}，{reason}。")
        try:
            data = response.json()
        except ValueError:
            raise PlayerError("API 没有返回 JSON。请检查地址是否为 API 端点，而不是网页地址。") from None
        return extract_completion(data)

    async def next(self, config, puzzle, rounds):
        content, usage = await self.request(config, player_messages(puzzle, rounds))
        try:
            action = parse_action(content)
        except ValueError as exc:
            raise PlayerError(str(exc)) from None
        return action, usage

    async def test(self, config):
        content, _ = await self.request(config, [{"role": "user", "content": '我们正在玩海龟汤，你是玩家。请只问一个简短问题。'}])
        try:
            parse_action(content)
        except ValueError as exc:
            raise PlayerError(str(exc)) from None
