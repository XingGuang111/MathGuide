# -*- coding: utf-8 -*-
"""MathGuide Web API 与静态页面入口。python web_app.py 启动，监听 0.0.0.0:8000"""
import json
import socket
import tempfile
import threading
import time
from datetime import date as calendar_date
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict

import agent as agent_mod
import config
import db
import llm
import model_settings
import model_gateway
import ocr
import practice
import pet
import pet_chat
import pet_emotions
import session_summary
import homework_review
import homework
import homework_visual
import vision
from typing import Literal


def _get_lan_ip():
    """尝试获取本机局域网 IP，失败则返回 None。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def _make_qrcode_data_url(text):
    """生成二维码并返回 data URL。qrcode 库不可用时返回 None。"""
    try:
        import qrcode
        import io
        import base64
        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


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
                          "homework_item_id": getattr(tutor, 'homework_item_id', None),
                          "question_type": tutor.question_type, "card": tutor.card,
                          "question_card": tutor.question_card,
                          "stage_messages": tutor.stage_messages, "dialogue": tutor.dialogue,
                          "rounds": tutor.rounds, "stage_rounds": tutor.stage_rounds,
                          "compute_expression": tutor.compute_expression,
                          "compute_result_correct": tutor.compute_result_correct,
                          "help_counts": tutor.help_counts, "needs_practice": tutor.needs_practice,
                          "previous_stage_answer": tutor.previous_stage_answer,
                          "teaching_state": tutor.teaching_state,
                          "initial_student_msg": tutor.initial_student_msg,
                          "activity": _activity[sid]}
    path = _session_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshots, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _cleanup():
    for sid in list(_sessions):
        if time.time() - _activity.get(sid, 0) > SESSION_TTL and not getattr(_sessions[sid], 'homework_item_id', None):
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
            if time.time() - activity > SESSION_TTL and not values.get('homework_item_id'):
                continue
            tutor = agent_mod.TutorAgent()
            legacy = values["state"] == "GUIDING" or "stage_messages" not in values
            values.pop("messages", None)
            values["state"] = (agent_mod.AgentState.STAGE1_UNDERSTAND if legacy
                               else agent_mod.AgentState(values["state"]))
            tutor.__dict__.update(values)
            tutor.teaching_state = {**agent_mod.teaching.initial_state(), **tutor.teaching_state}
            if tutor.question_card is None:
                tutor.question_card = tutor.card
            tutor.refresh_question_card()
            tutor.repair_saved_progress()
            if legacy:
                # 旧快照没有当前阶段上下文，保留归档日志并重新确认题意。
                tutor._enter_stage(agent_mod.AgentState.STAGE1_UNDERSTAND)
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
app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


class CleanRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class StartRequest(CleanRequest):
    question: str = Field(min_length=1, max_length=2000)
    homework_item_id: str | None = Field(default=None, min_length=1, max_length=100)


class HomeworkReviewRequest(CleanRequest):
    item_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=60)
    assignment_date: calendar_date
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=2000)
    recheck: bool = False


class HomeworkReflectionRequest(CleanRequest):
    reflection: str = Field(default='', max_length=2000)
    in_notes: bool = False
    in_mistakes: bool = False


class VisualReplyRequest(CleanRequest):
    message: str = Field(min_length=1,max_length=2000)
    request_id: str = Field(min_length=1,max_length=100)


class ReplyRequest(CleanRequest):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)


class SessionRequest(CleanRequest):
    session_id: str = Field(min_length=1)


class PracticeRequest(CleanRequest):
    knowledge_id: int | None = Field(default=None, ge=1, le=50)


class PracticeAnswer(CleanRequest):
    answer: str = Field(min_length=1, max_length=100)


class PetRequest(CleanRequest):
    profile_id: str = Field(min_length=1, max_length=80)


class PetEntertainmentRequest(CleanRequest):
    password: str = Field(min_length=1, max_length=80)


class PetRewardRequest(PetRequest):
    event_id: str = Field(min_length=1, max_length=120)


class PetItemRequest(PetRequest):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    item_id: str = Field(min_length=1, max_length=40)


class PetActionRequest(PetRequest):
    action_id: str = Field(min_length=1, max_length=40)


class PetHatRequest(PetRequest):
    hat_id: str | None = Field(default=None, min_length=1, max_length=40)


class PetChatRequest(PetRequest):
    message: str = Field(min_length=1, max_length=800)
    session_id: str | None = Field(default=None, max_length=100)
    exercise_id: str | None = Field(default=None, max_length=100)


class PetTouchRequest(PetRequest):
    session_id: str | None = Field(default=None, max_length=100)


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


@app.post('/api/homework/reviews')
def submit_homework(payload: HomeworkReviewRequest):
    try:
        return _practice_call(homework_review.submit, payload.item_id, payload.title,
                              payload.assignment_date.isoformat(), payload.question, payload.answer,payload.recheck)
    except llm.LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get('/api/homework/assignments')
def homework_list(date: calendar_date | None = None):
    return homework.listing(date.isoformat() if date else None)


@app.get('/api/homework/assignments/{assignment_id}')
def homework_get(assignment_id: str):
    return _practice_call(homework.get, assignment_id)


@app.put('/api/homework/assignments/{assignment_id}')
def homework_save(assignment_id: str, payload: homework.Assignment):
    return _practice_call(homework.save, assignment_id, payload)


@app.get('/api/homework/summary')
def homework_summary(date: calendar_date):
    return homework.summary(date.isoformat())


@app.get('/api/homework/items/{item_id}')
def homework_item_assignment(item_id: str):
    return _practice_call(homework.item_assignment, item_id)


@app.post('/api/homework/sources')
async def homework_upload(image: UploadFile = File(...)):
    data = await image.read(MAX_UPLOAD_BYTES + 1)
    await image.close()
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail='请选择不超过 10 MB 的非空图片')
    return await run_in_threadpool(_practice_call, homework.upload, data, image.filename or '作业照片')


@app.get('/api/homework/sources/{source_id}/image')
def homework_image(source_id: str, box: str | None = Query(default=None,pattern=r'^\d{1,4},\d{1,4},\d{1,4},\d{1,4}$')):
    data = _practice_call(homework.crop_image,source_id,[int(value) for value in box.split(',')]) if box else _practice_call(homework.image_bytes,source_id)
    return Response(data, media_type='image/png')


def _visual_call(function,*args):
    try:
        return _practice_call(function,*args)
    except llm.LLMError as exc:
        raise HTTPException(status_code=503,detail=str(exc)) from exc


@app.get('/api/homework/vision/status')
def homework_vision_status():
    return vision.status()


@app.post('/api/homework/vision/read')
def homework_visual_read(payload: homework.Region):
    return _visual_call(homework_visual.read_region,payload)


@app.get('/api/homework/items/{item_id}/visual-tutor')
def homework_visual_history(item_id: str):
    return _visual_call(homework_visual.history,item_id)


@app.post('/api/homework/items/{item_id}/visual-tutor')
def homework_visual_reply(item_id: str,payload: VisualReplyRequest):
    return _visual_call(homework_visual.reply,item_id,payload.message,payload.request_id)


@app.post('/api/homework/sources/{source_id}/recognize')
def homework_recognize(source_id: str):
    return _practice_call(homework.recognize_source, source_id)


@app.get('/api/homework/reviews')
def homework_records(collection: Literal['all', 'notes', 'mistakes'] = 'all', date: calendar_date | None = None):
    return homework_review.records(collection, date.isoformat() if date else None)


@app.patch('/api/homework/reviews/{review_id}')
def reflect_homework(review_id: str, payload: HomeworkReflectionRequest):
    return _practice_call(homework_review.reflect, review_id, payload.reflection,
                          payload.in_notes, payload.in_mistakes)


@app.get('/api/practice/{exercise_id}')
def get_practice(exercise_id: str):
    return _practice_call(practice.get, exercise_id)


@app.post('/api/practice/{exercise_id}/hint')
def practice_hint(exercise_id: str):
    return _practice_call(practice.hint, exercise_id)


@app.post('/api/practice/{exercise_id}/answer')
def practice_answer(exercise_id: str, payload: PracticeAnswer):
    return _practice_call(practice.submit, exercise_id, payload.answer)


@app.post('/api/pet')
def get_pet(payload: PetRequest):
    return _practice_call(pet.get, payload.profile_id)


@app.post('/api/pet/reward')
def reward_pet(payload: PetRewardRequest):
    return _practice_call(pet.claim_reward, payload.profile_id, payload.event_id)


@app.post('/api/pet/play/start')
def start_pet_play(payload: PetRequest):
    return _practice_call(pet.start_play, payload.profile_id)


@app.post('/api/pet/entertainment/unlock')
def unlock_entertainment_pet(payload: PetEntertainmentRequest):
    return _practice_call(pet.unlock_entertainment, payload.password)


@app.post('/api/pet/purchase')
def purchase_pet(payload: PetItemRequest):
    return _practice_call(pet.purchase, payload.profile_id, payload.item_id)


@app.post('/api/pet/interact')
def interact_pet(payload: PetItemRequest):
    return _practice_call(pet.interact, payload.profile_id, payload.item_id)


@app.post('/api/pet/learn')
def learn_pet_action(payload: PetActionRequest):
    return _practice_call(pet.learn, payload.profile_id, payload.action_id)


@app.post('/api/pet/perform')
def perform_pet_action(payload: PetActionRequest):
    return _practice_call(pet.perform, payload.profile_id, payload.action_id)


@app.post('/api/pet/equip')
def equip_pet_hat(payload: PetHatRequest):
    return _practice_call(pet.equip_hat, payload.profile_id, payload.hat_id)


def _pet_study_context(payload):
    context = {}
    with _sessions_lock:
        tutor = _sessions.get(payload.session_id) if payload.session_id else None
        if tutor and not tutor.finished:
            context = {'正在做题': True, '题目': tutor.question_text[:500],
                       '阶段': tutor.state.value,
                       '知识点': (tutor.card or {}).get('knowledge_point', '')}
    eid = getattr(payload, 'exercise_id', None)
    if eid:
        try:
            exercise = practice.get(eid)
            if not exercise['answered']:
                context = {'正在专项练习': True, '题目': exercise['question'][:500],
                           '知识点': exercise['knowledge_point']}
        except LookupError:
            pass
    return context


@app.post('/api/pet/chat')
def chat_pet(payload: PetChatRequest):
    return _practice_call(pet_chat.respond, payload.profile_id, payload.message, 'chat', _pet_study_context(payload))


@app.post('/api/pet/touch')
def touch_pet(payload: PetTouchRequest):
    return _practice_call(pet_chat.respond, payload.profile_id, '', 'touch', _pet_study_context(payload))


@app.post('/api/pet/chat/history')
def pet_chat_history(payload: PetRequest):
    return _practice_call(pet_chat.history, payload.profile_id)


def _take_reply(chunks):
    return "".join(chunks).strip()


def _related_practice(tutor):
    kid = (tutor.question_card or tutor.card or {}).get('id')
    return kid if tutor.finished and type(kid) is int and 1 <= kid <= 50 else None


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
    return {"ok": tip is None, "message": tip or "所选 AI 模型已就绪。", "model": model_settings.model_name(),
            "demo": bool(getattr(config, 'DEMO_MODE', False))}


def _require_local_settings(request: Request):
    # Configuration controls shared credentials and server-side destinations.
    if not request.client or request.client.host not in ('127.0.0.1', '::1', 'testclient'):
        raise HTTPException(403, '请在运行 MathGuide 的电脑上通过 localhost 打开模型设置。')
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, '请从 MathGuide 页面打开模型设置。')


@app.get('/api/model-settings')
def get_model_settings(request: Request):
    _require_local_settings(request)
    return model_settings.public()


@app.put('/api/model-settings')
def put_model_settings(payload: model_settings.SettingsRequest, request: Request):
    _require_local_settings(request)
    return model_settings.save(payload)


@app.post('/api/model-settings/test')
def test_model_settings(payload: model_settings.SettingsRequest, request: Request):
    _require_local_settings(request)
    settings = model_settings.candidate(payload)
    tip = model_gateway.check_health(settings)
    return {'ok': tip is None, 'message': tip or '连接成功，所选模型可以使用。'}


@app.post('/api/model-settings/models')
def list_setting_models(payload: model_settings.SettingsRequest, request: Request):
    _require_local_settings(request)
    try:
        return {'models': model_gateway.list_models(model_settings.candidate(payload))}
    except model_gateway.ModelConnectionError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/app.js", include_in_schema=False)
def javascript():
    return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript")


@app.get("/pet.js", include_in_schema=False)
def pet_javascript():
    return FileResponse(STATIC_DIR / "pet.js", media_type="application/javascript")


@app.get("/pet.css", include_in_schema=False)
def pet_styles():
    return FileResponse(STATIC_DIR / "pet.css", media_type="text/css")


@app.post("/api/sessions")
def start_session(payload: StartRequest):
    if payload.homework_item_id:
        _practice_call(homework.verify_item, payload.homework_item_id, payload.question)
    tutor = agent_mod.TutorAgent()
    result = tutor.start_session(payload.question.strip())
    if not result["ok"]:
        # clarify=True 表示题目不完整，把反问当作普通提示返回，前端不视为错误
        if result.get("clarify"):
            return {"clarify": True, "message": result["message"]}
        raise HTTPException(status_code=422, detail=result["message"])
    opening = _take_reply(tutor.begin_guiding())
    tutor.homework_item_id = payload.homework_item_id
    with _sessions_lock:
        _cleanup()
        if not tutor.finished:
            _sessions[tutor.session_id] = tutor
            _activity[tutor.session_id] = time.time()
        _persist()
    if payload.homework_item_id:
        homework.link_session(payload.homework_item_id, payload.question, tutor.session_id)
    return {
        "session_id": tutor.session_id,
        "question_type": result["question_type"],
        "card": tutor.card,
        "reply": opening,
        "finished": tutor.finished,
        "retryable": bool(tutor.last_error),
        "alert": tutor.pop_alert(),
        "practice_knowledge_id": _related_practice(tutor),
        "pet_reaction": pet_emotions.tutor_reaction(tutor),
        "summary": session_summary.build(tutor),
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
        previous_state = tutor.state
        previous_help = sum(tutor.help_counts.values())
        answer = _take_reply(tutor.reply(payload.message))
        progress_event = None if tutor.last_error else pet.record_learning_progress(payload.session_id, tutor.teaching_state)
        with _sessions_lock:
            _activity[payload.session_id] = time.time()
            if tutor.finished:
                _sessions.pop(payload.session_id, None)
                _activity.pop(payload.session_id, None)
            _persist()
        return {"reply": answer, "finished": tutor.finished, "rounds": tutor.rounds, 'pet_progress_event': progress_event,
                "retryable": bool(tutor.last_error),
                "card": tutor.card, "alert": tutor.pop_alert(),
                "summary": session_summary.build(tutor),
                "practice_knowledge_id": _related_practice(tutor),
                "pet_reaction": pet_emotions.tutor_reaction(tutor, previous_state, previous_help)}
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
                "dialogue": list(tutor.dialogue), "finished": tutor.finished,
                "homework_item_id": getattr(tutor, 'homework_item_id', None),
                "summary": session_summary.build(tutor)}
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


@app.get("/api/qrcode")
def qrcode_info():
    """返回局域网访问地址和二维码（手机扫码直接打开）。"""
    ip = _get_lan_ip()
    if not ip:
        return {"ip": None, "url": None, "qrcode": None}
    url = f"http://{ip}:8000"
    return {"ip": ip, "url": url, "qrcode": _make_qrcode_data_url(url)}


if __name__ == "__main__":
    import uvicorn
    # 监听 0.0.0.0，同一局域网下手机/其他设备可直接访问
    uvicorn.run(app, host="0.0.0.0", port=8000)
