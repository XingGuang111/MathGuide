# -*- coding: utf-8 -*-
"""MathGuide Web API 与静态页面入口。python -m uvicorn web_app:app --host 127.0.0.1 --port 8000"""
import json
import tempfile
import threading
import time
from datetime import date as calendar_date
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ConfigDict

import agent as agent_mod
import config
import db
import llm
import ocr
import practice


STATIC_DIR = config.BASE_DIR / "web"

_sessions: dict[str, agent_mod.TutorAgent] = {}
_sessions_lock = threading.Lock()
_turn_locks = {}
_activity = {}
SESSION_TTL = 24 * 60 * 60
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _session_file():
    return Path(config.DB_PATH).with_suffix(".sessions.json")


def _persist():
    snapshots = {}
    for sid, tutor in _sessions.items():
        snapshots[sid] = {"state": tutor.state.value, "finished": tutor.finished,
                          "session_id": sid, "question_text": tutor.question_text,
                          "question_type": tutor.question_type, "card": tutor.card,
                          "messages": tutor.messages, "dialogue": tutor.dialogue,
                          "rounds": tutor.rounds, "activity": _activity[sid]}
    path = _session_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshots, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _cleanup():
    for sid in list(_sessions):
        if time.time() - _activity.get(sid, 0) > SESSION_TTL:
            lock = _turn_locks.setdefault(sid, threading.Lock())
            if lock.acquire(blocking=False):
                try:
                    _sessions.pop(sid, None)
                    _activity.pop(sid, None)
                    _turn_locks.pop(sid, None)
                finally:
                    lock.release()


def _restore():
    path = _session_file()
    if not path.exists():
        return
    try:
        snapshots = json.loads(path.read_text(encoding="utf-8"))
        for sid, values in snapshots.items():
            activity = values.pop("activity", 0)
            if time.time() - activity > SESSION_TTL:
                continue
            tutor = agent_mod.TutorAgent()
            values["state"] = agent_mod.AgentState(values["state"])
            tutor.__dict__.update(values)
            _sessions[sid] = tutor
            _activity[sid] = activity
    except (ValueError, TypeError, KeyError, AttributeError):
        # 损坏快照不会阻止学习记录和首页使用。
        return


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    _restore()
    yield


app = FastAPI(title="MathGuide", version="1.0.0", lifespan=lifespan)


class CleanRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class StartRequest(CleanRequest):
    question: str = Field(min_length=1, max_length=2000)


class ReplyRequest(CleanRequest):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)


class SessionRequest(CleanRequest):
    session_id: str = Field(min_length=1)


class PracticeRequest(CleanRequest):
    knowledge_id: int | None = Field(default=None, ge=1, le=50)


class PracticeAnswer(CleanRequest):
    answer: str = Field(min_length=1, max_length=100)


def _practice_call(function, *args):
    try:
        return function(*args)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post('/api/practice')
def create_practice(payload: PracticeRequest):
    return _practice_call(practice.create, payload.knowledge_id)


@app.get('/api/practice/{exercise_id}')
def get_practice(exercise_id: str):
    return _practice_call(practice.get, exercise_id)


@app.post('/api/practice/{exercise_id}/hint')
def practice_hint(exercise_id: str):
    return _practice_call(practice.hint, exercise_id)


@app.post('/api/practice/{exercise_id}/answer')
def practice_answer(exercise_id: str, payload: PracticeAnswer):
    return _practice_call(practice.submit, exercise_id, payload.answer)


def _take_reply(chunks):
    return "".join(chunks).strip()


def _get_session(session_id):
    with _sessions_lock:
        _cleanup()
        tutor = _sessions.get(session_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="会话不存在或服务已重启，请重新开始。")
    return tutor


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    tip = llm.check_health()
    return {"ok": tip is None, "message": tip or "Ollama 与模型已就绪。", "model": config.MODEL_NAME}


@app.get("/app.js", include_in_schema=False)
def javascript():
    return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript")


@app.post("/api/sessions")
def start_session(payload: StartRequest):
    tutor = agent_mod.TutorAgent()
    result = tutor.start_session(payload.question.strip())
    if not result["ok"]:
        # clarify=True 表示题目不完整，把反问当作普通提示返回，前端不视为错误
        if result.get("clarify"):
            return {"clarify": True, "message": result["message"]}
        raise HTTPException(status_code=422, detail=result["message"])
    opening = _take_reply(tutor.begin_guiding())
    with _sessions_lock:
        _cleanup()
        if not tutor.finished:
            _sessions[tutor.session_id] = tutor
            _activity[tutor.session_id] = time.time()
        _persist()
    return {
        "session_id": tutor.session_id,
        "question_type": result["question_type"],
        "card": tutor.card,
        "reply": opening,
        "finished": tutor.finished,
        "retryable": bool(tutor.last_error),
        "alert": tutor.pop_alert(),
    }


@app.post("/api/replies")
def reply(payload: ReplyRequest):
    tutor = _get_session(payload.session_id)
    lock = _turn_locks.setdefault(payload.session_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="老师正在处理上一条消息，请稍候。")
    try:
        if tutor.finished:
            raise HTTPException(status_code=409, detail="本轮辅导已经结束，请开始一道新题。")
        answer = _take_reply(tutor.reply(payload.message))
        with _sessions_lock:
            _activity[payload.session_id] = time.time()
            if tutor.finished:
                _sessions.pop(payload.session_id, None)
                _activity.pop(payload.session_id, None)
            _persist()
        return {"reply": answer, "finished": tutor.finished, "rounds": tutor.rounds,
                "retryable": bool(tutor.last_error),
                "card": tutor.card, "alert": tutor.pop_alert()}
    finally:
        lock.release()


@app.post("/api/sessions/abort")
def abort(payload: SessionRequest):
    tutor = _get_session(payload.session_id)
    lock = _turn_locks.setdefault(payload.session_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="请等待当前回复完成后换题。")
    try:
        tutor.abort()
        with _sessions_lock:
            _sessions.pop(payload.session_id, None)
            _activity.pop(payload.session_id, None)
            _persist()
    finally:
        lock.release()
    return {"ok": True}


@app.get("/api/sessions/{session_id}")
def session_snapshot(session_id: str):
    tutor = _get_session(session_id)
    lock = _turn_locks.setdefault(session_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="当前辅导正在回复，请稍后恢复。")
    try:
        return {"session_id": session_id, "question": tutor.question_text,
                "question_type": tutor.question_type, "card": tutor.card,
                "dialogue": list(tutor.dialogue), "finished": tutor.finished}
    finally:
        lock.release()


@app.post("/api/ocr")
async def recognize_image(image: UploadFile = File(...)):
    suffix = Path(image.filename or "").suffix.lower()
    if suffix not in config.OCR_IMAGE_EXTS:
        raise HTTPException(status_code=415, detail="仅支持 JPG、JPEG、PNG、BMP 图片。")
    data = await image.read(MAX_UPLOAD_BYTES + 1)
    await image.close()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="图片不能超过 10 MB。")
    if not data:
        raise HTTPException(status_code=400, detail="上传的图片为空。")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp.write(data)
            temp_path = Path(temp.name)
        text = await run_in_threadpool(ocr.recognize, str(temp_path))
    except ocr.OCRError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
    if not text:
        raise HTTPException(status_code=422, detail="没有识别到文字，请换一张更清晰的图片。")
    return {"text": text}


@app.get("/api/history")
def history(date: calendar_date | None = Query(default=None), qtype: str | None = Query(default=None)):
    if qtype and qtype not in config.QUESTION_TYPES:
        raise HTTPException(status_code=422, detail="不支持的题型。")
    rows = db.query_history(date=date.isoformat() if date else None, qtype=qtype)
    for row in rows:
        try:
            row["dialogue"] = json.loads(row.pop("dialogue_log"))
        except (TypeError, json.JSONDecodeError):
            row["dialogue"] = []
            row.pop("dialogue_log", None)
    return rows


@app.get("/api/stats")
def stats():
    return db.weak_stats()
