# -*- coding: utf-8 -*-
"""启发式辅导状态机：分析题目 → 展示公式 → 多轮引导 → 归档"""
import json
import re
import uuid
from datetime import date
from enum import Enum

import config
import db
import knowledge
import llm
import prompts


class AgentState(Enum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    FORMULA_SHOWN = "FORMULA_SHOWN"
    GUIDING = "GUIDING"
    DONE = "DONE"


_TAG_RE = re.compile(r"\[(CONTINUE|UNDERSTOOD)\]")

_FALLBACK_EXPLAIN = (
    "没关系，我们已经试了很多步啦。老师来讲一下完整的思路："
    "先回忆本题的公式，把题目里的数字对应进去，一步一步计算就能得到答案。"
    "你可以把这道题记下来，过几天再自己试一次！"
)


class TutorAgent:
    def __init__(self, db_path=None):
        self.db_path = db_path
        self.state = AgentState.IDLE
        self.finished = False
        self.session_id = None
        self.question_text = ""
        self.question_type = None
        self.card = None
        self.messages = []       # 发给 LLM 的消息（含 system）
        self.dialogue = []       # 归档用对话日志（student/teacher）
        self.rounds = 0

    # ---------- 会话入口 ----------

    def start_session(self, question_text):
        """分析题目并准备辅导。返回 {"ok","card","question_type","message"}"""
        self.question_text = question_text
        self.session_id = uuid.uuid4().hex
        self.state = AgentState.ANALYZING
        try:
            result = llm.analyze(question_text, knowledge.load_candidates(self.db_path))
        except llm.LLMError as e:
            self.state = AgentState.IDLE
            return {"ok": False, "card": None, "question_type": None, "message": str(e)}
        if not result["is_elementary_math"]:
            self.state = AgentState.IDLE
            return {"ok": False, "card": None, "question_type": None,
                    "message": "这道题好像不是小学数学题哦，我只能辅导小学数学题。"}
        self.card = knowledge.resolve(result["knowledge_id"], result["raw_knowledge"], self.db_path)
        self.question_type = result["question_type"]
        self.messages = [
            {"role": "system", "content": prompts.build_tutor_system_prompt(question_text, self.card)}
        ]
        self.dialogue = []
        self.rounds = 0
        self.finished = False
        self.state = AgentState.FORMULA_SHOWN
        return {"ok": True, "card": self.card, "question_type": self.question_type, "message": ""}

    def begin_guiding(self):
        """从 FORMULA_SHOWN 进入 GUIDING，返回 AI 老师的第一个引导问题（generator）"""
        self.state = AgentState.GUIDING
        return self._next_chunk_stream()

    # ---------- 对话 ----------

    def reply(self, student_msg):
        """接收学生回答，yield AI 引导回复 chunk（不含状态标记）。
        迭代结束后 finished 已更新；结束时会话自动归档。
        FORMULA_SHOWN 状态下视为隐式进入引导（跳过 AI 开场白）。"""
        if self.state == AgentState.FORMULA_SHOWN:
            self.state = AgentState.GUIDING
        if self.state != AgentState.GUIDING:
            raise RuntimeError("当前不在辅导中")
        self.messages.append({"role": "user", "content": student_msg})
        self.dialogue.append({"role": "student", "content": student_msg})
        return self._next_chunk_stream()

    def _next_chunk_stream(self):
        """调 LLM 生成一轮回复：剥离标记后 yield 正文；流结束后按标记推进状态"""
        full = []
        try:
            for chunk in llm.chat_stream(self.messages):
                full.append(chunk)
        except llm.LLMError as e:
            yield f"（老师暂时开小差了：{e}）"
            return
        text = "".join(full)
        m = _TAG_RE.search(text)
        tag = m.group(1) if m else "CONTINUE"
        body = _TAG_RE.sub("", text).strip()
        self.messages.append({"role": "assistant", "content": text})
        self.dialogue.append({"role": "teacher", "content": body})
        self.rounds += 1
        yield body + "\n"
        if tag == "UNDERSTOOD":
            yield "\n太棒了，这道题你自己想明白啦！\n"
            self._archive(understood=1)
        elif self.rounds >= config.MAX_GUIDE_ROUNDS:
            yield "\n" + _FALLBACK_EXPLAIN + "\n"
            self._archive(understood=0)
        self.finished = self.state == AgentState.IDLE

    # ---------- 归档与放弃 ----------

    def _archive(self, understood):
        db.save_record({
            "session_id": self.session_id,
            "record_date": date.today().isoformat(),
            "question_type": self.question_type or "未分类",
            "question_text": self.question_text,
            "knowledge_point": self.card["knowledge_point"] if self.card else "未匹配",
            "formula": self.card["formula"] if self.card else "",
            "dialogue_log": json.dumps(self.dialogue, ensure_ascii=False),
            "understood": understood,
        }, self.db_path)
        self.state = AgentState.IDLE
        self.finished = True

    def abort(self):
        """放弃当前题目，不归档"""
        self.state = AgentState.IDLE
        self.finished = True
        self.messages = []
        self.dialogue = []
