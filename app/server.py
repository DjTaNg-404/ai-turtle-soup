from __future__ import annotations
import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from .domain import Puzzle, PlayerConfig, PlayerAction, JudgeConfig
from .judging import JudgeError
from .jev import create_judge
from .player import APIPlayer, PlayerError

ROOT = Path(__file__).resolve().parents[1]

class Session:
    def __init__(self, puzzle, config, judge=None):
        self.puzzle = puzzle
        self.id = uuid.uuid4().hex
        self.created = time.time()
        self.status = "paused"
        self.phase = "等待开始"
        self.rounds = []
        self.progress = {"stage": "unresolved", "label": "等待提问", "probabilities": {}, "window_rounds": 0, "submitted_solution": False, "evidence_source": "affirmed_questions", "confirmed_count": 0, "confirmed_rounds": []}
        self.pending = None
        self.error = None
        self.task = None
        self.continuous = False
        self.player = config.public()
        self.judge = judge or JudgeConfig().identity()

    def public(self):
        return {"id": self.id, "created": self.created, "status": self.status, "phase": self.phase,
                "puzzle": self.puzzle.model_dump(), "rounds": self.rounds, "progress": self.progress,
                "pending": self.pending, "error": self.error, "continuous": self.continuous,
                "busy": bool(self.task and not self.task.done()), "player": self.player,
                "judge": self.judge, "format_version": 2}

class CreateGame(BaseModel):
    puzzle: Puzzle
    run: bool = True

class Control(BaseModel):
    action: str

class Controller:
    def __init__(self, judge, player, data_dir):
        self.judge = judge
        self.player = player
        self.config = PlayerConfig()
        self.judge_config = JudgeConfig()
        self.sessions = {}
        self.current = None
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.data_dir.parent / "player-settings.json"
        if self.settings_path.is_file():
            try:
                raw = json.loads(self.settings_path.read_text())
                allowed = {k: raw[k] for k in ["base_url", "model"] if k in raw}
                self.config = PlayerConfig.model_validate(allowed)
            except (OSError, ValueError, TypeError):
                pass

        self.judge_settings_path = self.data_dir.parent / "judge-settings.json"
        if self.judge_settings_path.is_file():
            try:
                raw = json.loads(self.judge_settings_path.read_text())
                allowed = {k: raw[k] for k in ["provider", "base_url", "model"] if k in raw}
                self.judge_config = JudgeConfig.model_validate(allowed)
            except (OSError, ValueError, TypeError):
                pass
        if judge is None:
            self.judge = create_judge(self.judge_config)

    def save_settings(self):
        public = {"base_url": self.config.base_url, "model": self.config.model}
        temp = self.settings_path.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(public, f, ensure_ascii=False, indent=2)
        temp.replace(self.settings_path)
        public_judge = {k: getattr(self.judge_config, k) for k in ["provider", "base_url", "model"]}
        temp = self.judge_settings_path.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(public_judge, f, ensure_ascii=False, indent=2)
        temp.replace(self.judge_settings_path)

    def save(self, s):
        data = s.public()
        data["busy"] = False
        # Persist replay state only: API credentials never enter a Session.
        target = self.data_dir / f"{s.id}.json"
        temp = target.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp.replace(target)

    def busy(self):
        return any(s.task and not s.task.done() for s in self.sessions.values())

    def get(self, sid):
        if sid in self.sessions:
            return self.sessions[sid]
        if len(sid) != 32 or any(c not in "0123456789abcdef" for c in sid):
            raise HTTPException(404, "没有找到这局记录")
        path = self.data_dir / f"{sid}.json"
        if not path.is_file():
            raise HTTPException(404, "没有找到这局记录")
        data = json.loads(path.read_text())
        s = Session(Puzzle.model_validate(data["puzzle"]), self.config)
        for key in ["id", "created", "rounds", "progress", "pending", "player"]:
            setattr(s, key, data[key])
        s.judge = data.get("judge", JudgeConfig().identity())
        if isinstance(s.progress, list):
            s.progress = {"stage": "unresolved", "label": "旧版对局", "probabilities": {}, "window_rounds": 0, "submitted_solution": False}
        s.status = data["status"] if data["status"] in {"won", "exhausted", "ended"} else "paused"
        s.phase = "对局记录" if s.status in {"won", "exhausted", "ended"} else "已恢复，可继续"
        self.sessions[s.id] = s
        return s

    def start(self, s, continuous):
        if s.task and not s.task.done():
            raise HTTPException(409, "当前轮尚未结束，请等待")
        if self.busy():
            raise HTTPException(409, "另一局仍在运行，请先暂停")
        if s.status in {"won", "exhausted", "ended"}:
            raise HTTPException(409, "这局已经结束，请新开一局")
        if not self.config.model.strip():
            raise HTTPException(400, "请先配置玩家 API 和模型名称")
        s.continuous = continuous
        s.error = None
        s.status = "running"
        s.phase = "准备本轮"
        s.player = self.config.public()
        s.judge = self.judge_config.identity()
        s.task = asyncio.create_task(self.run(s, self.config.model_copy(deep=True), self.judge))
        self.current = s.id

    async def run(self, s, config, judge):
        try:
            while True:
                if len(s.rounds) >= s.puzzle.max_rounds:
                    s.status, s.phase = "exhausted", "已达到轮数上限"
                    break
                # Load before spending any API call.
                s.phase = "准备主持人"
                await asyncio.to_thread(judge.load)
                if s.pending is None:
                    s.phase = "玩家正在提问"
                    start = time.perf_counter()
                    action, usage = await self.player.next(config, s.puzzle, s.rounds)
                    s.pending = {"action": action.model_dump(), "player_ms": round((time.perf_counter()-start)*1000), "usage": usage}
                    self.save(s)
                action = PlayerAction.model_validate(s.pending["action"])
                s.phase = s.judge["name"] + " 正在判断并对照汤底"
                result = await asyncio.to_thread(judge.evaluate, s.puzzle, action, s.rounds, s.progress)
                turn = {**s.pending, **result, "number": len(s.rounds)+1, "player_model": config.model, "judge": dict(s.judge)}
                s.rounds.append(turn)
                s.progress = result["progress"]
                s.pending = None
                if result["solved"]:
                    s.status, s.phase = "won", s.judge["name"] + " 判定通关"
                elif len(s.rounds) >= s.puzzle.max_rounds:
                    s.status, s.phase = "exhausted", "已达到轮数上限"
                elif not s.continuous:
                    s.status, s.phase = "paused", "已暂停"
                self.save(s)
                if s.status != "running":
                    break
                s.phase = "下一轮即将开始"
                # A brief visible pause gives the observer time to stop the next API request.
                await asyncio.sleep(1.2)
                if not s.continuous:
                    s.status, s.phase = "paused", "已暂停"
                    break
        except (PlayerError, JudgeError) as exc:
            s.status, s.phase, s.error = "error", "本轮暂停，可重试", str(exc)
        except asyncio.CancelledError:
            s.status, s.phase = "paused", "服务已停止；可恢复对局"
            raise
        except Exception:
            # Internal errors must not serialize request headers, API responses or credentials.
            s.status, s.phase, s.error = "error", "本轮暂停", "内部处理失败。对局已保留，请查看终端后重试。"
            import traceback
            traceback.print_exc()
        finally:
            s.continuous = s.continuous and s.status == "running"
            self.save(s)


def create_app(judge=None, player=None, data_dir=None):
    ctl = Controller(judge, player or APIPlayer(), data_dir or ROOT / ".data/runs")

    @asynccontextmanager
    async def lifespan(app):
        yield
        tasks = [s.task for s in ctl.sessions.values() if s.task and not s.task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="AI 海龟汤", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.controller = ctl
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "只接受本页面发起的请求"}, 403)
            if not request.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse({"detail": "请求必须为 JSON"}, 415)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        messages = [f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse({"detail": "；".join(messages)}, 422)

    @app.get("/api/status")
    async def status():
        return {"judge": ctl.judge.status(), "player": ctl.config.public(), "current": ctl.current, "busy": ctl.busy(), "judge_config": ctl.judge_config.public()}

    @app.post("/api/config")
    async def config(value: PlayerConfig, request: Request):
        if ctl.busy():
            raise HTTPException(409, "请等当前轮结束后再更换玩家配置")
        raw = await request.json()
        if raw.get("keep_key") and value.base_url == ctl.config.base_url and not value.api_key.get_secret_value():
            value.api_key = ctl.config.api_key
        ctl.config = value
        ctl.save_settings()
        return value.public()

    @app.post("/api/player/test")
    async def player_test():
        if not ctl.config.model.strip():
            raise HTTPException(400, "请先填写模型名称并保存")
        try:
            await ctl.player.test(ctl.config)
        except PlayerError as exc:
            raise HTTPException(400, str(exc)) from None
        return {"ok": True}

    @app.post("/api/judge/config")
    async def judge_config(value: JudgeConfig, request: Request):
        if ctl.busy():
            raise HTTPException(409, "请等当前轮结束后再更换主持人")
        raw = await request.json()
        if raw.get("keep_key") and value.provider == ctl.judge_config.provider and value.base_url == ctl.judge_config.base_url and not value.api_key.get_secret_value():
            value.api_key = ctl.judge_config.api_key
        previous = ctl.judge_config
        ctl.judge_config = value
        if value.provider != "laya" or previous.provider != "laya":
            ctl.judge = create_judge(value)
        ctl.save_settings()
        return {"config": value.public(), "judge": ctl.judge.status()}

    @app.post("/api/judge/test")
    async def judge_test():
        if ctl.busy():
            raise HTTPException(409, "请等当前轮结束后再测试主持人")
        try:
            await asyncio.to_thread(getattr(ctl.judge, "test", ctl.judge.load))
        except JudgeError as exc:
            raise HTTPException(400, str(exc)) from None
        return {"ok": True, "judge": ctl.judge.status()}

    @app.post("/api/judge/load")
    async def judge_load():
        try:
            return await asyncio.to_thread(ctl.judge.load)
        except JudgeError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.post("/api/games")
    async def create_game(value: CreateGame):
        if ctl.busy():
            raise HTTPException(409, "请先暂停当前对局，等待本轮结束")
        if value.run and not ctl.config.model.strip():
            raise HTTPException(400, "请先接入玩家 API")
        s = Session(value.puzzle, ctl.config, ctl.judge_config.identity())
        ctl.sessions[s.id] = s
        ctl.current = s.id
        ctl.save(s)
        if value.run:
            ctl.start(s, True)
        return s.public()

    @app.get("/api/games")
    async def list_games():
        result = []
        for p in sorted(ctl.data_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:50]:
            try:
                data = json.loads(p.read_text())
                result.append({"id": data["id"], "title": data["puzzle"]["title"], "created": data["created"],
                               "rounds": len(data["rounds"]), "status": data["status"]})
            except (OSError, ValueError, KeyError):
                continue
        return result

    @app.get("/api/games/{sid}")
    async def get_game(sid: str):
        return ctl.get(sid).public()

    @app.post("/api/games/{sid}/control")
    async def control(sid: str, value: Control):
        s = ctl.get(sid)
        if value.action == "pause":
            s.continuous = False
            if s.task and not s.task.done():
                s.phase = "当前轮完成后暂停"
            elif s.status not in {"won", "exhausted", "ended"}:
                s.status, s.phase = "paused", "已暂停"
        elif value.action in {"step", "resume"}:
            ctl.start(s, value.action == "resume")
        elif value.action in {"end", "leave"}:
            if s.task and not s.task.done():
                raise HTTPException(409, "请先暂停并等待本轮结束")
            if s.status not in {"won", "exhausted", "ended"}:
                s.status, s.phase, s.continuous = "ended", "已结束", False
            if value.action == "leave" and ctl.current == s.id:
                ctl.current = None
        else:
            raise HTTPException(400, "未知的对局操作")
        ctl.save(s)
        return s.public()

    @app.get("/api/games/{sid}/export")
    async def export_game(sid: str):
        return JSONResponse(ctl.get(sid).public(), headers={"Content-Disposition": f'attachment; filename="turtle-soup-{sid[:8]}.json"'})

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "static/index.html")
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    return app

app = create_app()
