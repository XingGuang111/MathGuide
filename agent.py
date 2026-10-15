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
import calculation


class AgentState(Enum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    FORMULA_SHOWN = "FORMULA_SHOWN"
    GUIDING = "GUIDING"
    DONE = "DONE"


_TAG_RE = re.compile(r"\[(CONTINUE|UNDERSTOOD)\]")
_CARD_TAG_RE = re.compile(r"\[CARD:(\d+)\]")
_ALL_TAGS_RE = re.compile(r"\[(?:CONTINUE|UNDERSTOOD|CARD:\d+)\]")

# 学生消息命中以下关键词时，后端启发式判定为「超纲追问」，直接给学生一次性提醒
_OUT_OF_SCOPE_KEYWORDS = (
    "初中", "高中", "大学", "中考", "高考",
    "一元二次", "二次方程", "函数", "导数", "微积分", "积分",
    "三角函数", "正弦", "余弦", "正切",
    "对数", "指数函数", "数列",
    "物理", "化学", "生物",
)
_OUT_OF_SCOPE_ALERT = "这个内容要到更高年级才学哦，咱们先把眼前这道小学题做完。"

# 题目里至少应包含一个数字（阿拉伯或中文），否则几乎肯定是「只是知识点名称」的不完整输入
_HAS_DIGIT_RE = re.compile(r"[\d零一二三四五六七八九十百千万两半]")
_INCOMPLETE_CLARIFY = ("题目里好像还没有具体数值。能把完整题目告诉我吗？"
                       "例如「一个圆的半径是 5 米，求它的面积」。")

# 判断 analyze 选的卡是否语义合理：知识点名称去除通用词后，至少一个特征字出现在题目里
# 小模型在「必须选一个」的约束下会强行匹配相近候选（例如把鸡兔同笼分到长方形面积），
# 用此启发式做后置校验，不依赖模型自觉。
_CARD_STOP_CHARS = set("面积周长公式单位计算问题应用加减乘除的和是在有不")


def _analyze_choice_plausible(question_text, card):
    if not card:
        return False
    kp = card.get("knowledge_point") or ""
    features = [c for c in kp if c not in _CARD_STOP_CHARS and c.strip()]
    if not features:
        return True  # 名称全是通用词，无法判定，放行
    return any(c in question_text for c in features)

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
        self.last_error = None
        self.last_alert = None   # 本轮 [ALERT:...] 提醒，web 层取走后清空

    # ---------- 会话入口 ----------

    def start_session(self, question_text):
        """分析题目并准备辅导。返回 {"ok","card","question_type","message"}"""
        self.__init__(self.db_path)
        self.question_text = question_text
        self.session_id = uuid.uuid4().hex
        self.state = AgentState.ANALYZING
        # 启发式：输入不含任何数字 → 几乎肯定只是知识点名称，跳过 analyze 直接 clarify
        # （小模型在 analyze 阶段无法可靠识别这种情况，会强行匹配到错误候选）
        if not _HAS_DIGIT_RE.search(question_text):
            self.state = AgentState.IDLE
            return {"ok": False, "card": None, "question_type": None,
                    "message": _INCOMPLETE_CLARIFY, "clarify": True}
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
        # 语义合理性校验：analyze 在「必须选一个」的约束下可能强行匹配相近候选；
        # 若卡名特征字一个都没在题目里出现，判定乱选，弃用本地卡改走 AI 生成轨
        if self.card is not None and not _analyze_choice_plausible(question_text, self.card):
            self.card = None
        if self.card is None:
            # 本地未命中（或乱选被弃用）：走 AI 生成轨
            try:
                gen = llm.generate_formula(question_text)
            except llm.LLMError as e:
                self.state = AgentState.IDLE
                return {"ok": False, "card": None, "question_type": None, "message": str(e)}
            if gen["kind"] == "not_math":
                self.state = AgentState.IDLE
                return {"ok": False, "card": None, "question_type": None,
                        "message": "这道题好像不是小学数学题哦，我只能辅导小学数学题。"}
            if gen["kind"] == "clarify":
                self.state = AgentState.IDLE
                return {"ok": False, "card": None, "question_type": None,
                        "message": gen["question"], "clarify": True}
            self.card = gen["card"]
        self.question_type = result["question_type"]
        self.messages = [
            {"role": "system", "content": prompts.build_tutor_system_prompt(
                question_text, self.card, knowledge.load_candidates(self.db_path))}
        ]
        self.dialogue = []
        self.rounds = 0
        self.finished = False
        self.state = AgentState.FORMULA_SHOWN
        return {"ok": True, "card": self.card, "question_type": self.question_type, "message": ""}

    def begin_guiding(self):
        """从 FORMULA_SHOWN 进入 GUIDING，返回 AI 老师的第一个引导问题（generator）"""
        if self.state != AgentState.FORMULA_SHOWN:
            raise RuntimeError("当前不能重复开始辅导")
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
        # 后端启发式：学生提到超纲内容时，直接置一次性提醒（不依赖小模型输出标记）
        if any(kw in student_msg for kw in _OUT_OF_SCOPE_KEYWORDS):
            self.last_alert = _OUT_OF_SCOPE_ALERT
        self.messages.append({"role": "user", "content": student_msg})
        self.dialogue.append({"role": "student", "content": student_msg})
        return self._next_chunk_stream()

    def _next_chunk_stream(self):
        """调 LLM 生成一轮回复：剥离标记后 yield 正文；流结束后按标记推进状态"""
        full = []
        self.last_error = None
        verified = calculation.rectangle(self.question_text, self.card)
        latest = self.messages[-1] if self.messages else {}
        try:
            if verified and latest.get('role') == 'user':
                response, complete = verified.respond(latest['content'])
                full.append(response + '\n' + ('[UNDERSTOOD]' if complete else '[CONTINUE]'))
            else:
                for chunk in llm.chat_stream(self.messages):
                    full.append(chunk)
            if not _TAG_RE.sub("", "".join(full)).strip():
                raise llm.LLMError("模型未返回有效回复，请重试")
        except llm.LLMError as e:
            self.last_error = str(e)
            if self.messages and self.messages[-1]["role"] == "user":
                self.messages.pop()
                self.dialogue.pop()
            yield f"（老师暂时开小差了：{e}）"
            return
        text = "".join(full)
        # 解析换卡标记：仅当 id 在本地库存在且与当前卡不同才切换；其余情况静默忽略
        card_match = _CARD_TAG_RE.search(text)
        if card_match:
            new_card = knowledge.get_by_id(int(card_match.group(1)), self.db_path)
            if new_card and (not self.card or new_card.get("id") != self.card.get("id")):
                self.card = new_card
        tags = _TAG_RE.findall(text)
        tag = tags[-1] if tags and len(set(tags)) == 1 else "CONTINUE"
        body = _ALL_TAGS_RE.sub("", text).strip()
        self.messages.append({"role": "assistant", "content": text})
        self.dialogue.append({"role": "teacher", "content": body})
        self.rounds += 1
        yield body + "\n"
        if tag == "UNDERSTOOD" and any(m["role"] == "student" for m in self.dialogue):
            yield "\n太棒了，这道题你自己想明白啦！\n"
            self._archive(understood=1)
        elif self.rounds >= config.MAX_GUIDE_ROUNDS:
            try:
                explanation = verified.explanation() if verified else "".join(llm.chat_stream(
                    prompts.build_explain_messages(self.question_text, self.card, self.dialogue),
                )).strip()
            except llm.LLMError:
                explanation = "暂时无法生成完整讲解。请回顾题目条件和知识卡片，稍后重新练习。"
            explanation = _TAG_RE.sub("", explanation) or "暂无完整讲解，请稍后重新练习。"
            self.dialogue.append({"role": "teacher", "content": explanation})
            yield "\n" + explanation + "\n"
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

    def pop_alert(self):
        """web 层调用：取出本轮超纲提醒并清空，保证一次性"""
        alert, self.last_alert = self.last_alert, None
        return alert

    def abort(self):
        """放弃当前题目，不归档"""
        self.state = AgentState.IDLE
        self.finished = True
        self.messages = []
        self.dialogue = []
