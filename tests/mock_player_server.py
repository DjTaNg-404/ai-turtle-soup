"""Explicitly scripted development endpoint; this is not a real player model."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

QUESTIONS = [
    "他要水是为了停止打嗝吗？",
    "服务员故意大喊，是想吓他来帮助止嗝吗？",
    "他正在打嗝，想喝水止嗝；服务员故意大喊吓他，让他停止打嗝，所以他道谢离开，不再需要水了吗？",
]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        messages = data.get("messages", [])
        n = sum(m["role"] == "assistant" for m in messages)
        body = json.dumps({
            "choices": [{
                "message": {"role": "assistant", "content": QUESTIONS[min(n, len(QUESTIONS) - 1)]},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 30, "completion_tokens": 20},
        }, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("Scripted demo only: http://127.0.0.1:8766/v1 (no real player model)")
    ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
