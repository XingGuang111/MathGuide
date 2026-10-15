# -*- coding: utf-8 -*-
"""Ollama 封装：健康检查、JSON 题目分析、流式对话"""
import json
import re

import ollama

import config
import prompts


class LLMError(Exception):
    """LLM 调用失败（服务不可达 / 输出无法解析）"""


def check_health():
    """启动检查：返回 None 表示正常；否则返回给用户的中文提示"""
    try:
        data = ollama.list()
    except Exception:
        return ("无法连接 Ollama 服务。\n"
                "请先安装 Ollama（https://ollama.com/download）并启动它，然后重试。")
    models = [m.get("model") or m.get("name", "") for m in data.get("models", [])]
    if config.MODEL_NAME not in models:
        return (f"本地还没有模型 {config.MODEL_NAME}。\n"
                f"请运行：ollama pull {config.MODEL_NAME}")
    return None


def analyze(question_text, candidates):
    """题目分析：强制 JSON 输出；解析失败重试 ANALYZE_RETRY 次，仍失败抛 LLMError"""
    prompt = prompts.build_analyze_prompt(question_text, candidates)
    candidate_ids = {int(n) for n in re.findall(r"(?:^|\|)\s*(\d+)\.", candidates)}
    last_err = None
    for _ in range(1 + config.ANALYZE_RETRY):
        try:
            resp = ollama.chat(
                model=config.MODEL_NAME,
                messages=[{"role": "system", "content": prompts.ANALYZE_SYSTEM},
                          {"role": "user", "content": prompt}]
                         + ([{"role": "user", "content": f"上次输出未通过校验：{last_err}。请重新输出有效JSON。"}] if last_err else []),
                format="json",
                options={"temperature": 0, "num_predict": 256},
            )
            data = json.loads(resp["message"]["content"])
            if not isinstance(data, dict) or type(data.get("is_elementary_math")) is not bool:
                raise TypeError("is_elementary_math 必须为布尔值")
            if data["is_elementary_math"]:
                if data.get("question_type") not in config.QUESTION_TYPES:
                    raise TypeError("题型不在支持范围内")
                kp_id = data.get("knowledge_id")
                if kp_id is not None and (type(kp_id) is not int or kp_id not in candidate_ids):
                    raise TypeError("知识点编号必须来自候选目录，无法匹配时用null")
            elif data.get("knowledge_id") is not None or data.get("question_type") is not None:
                raise TypeError("非数学内容的编号和题型必须为null")
            return {
                "is_elementary_math": bool(data.get("is_elementary_math")),
                "knowledge_id": data.get("knowledge_id"),
                "question_type": data.get("question_type"),
                "raw_knowledge": data.get("knowledge_point"),
            }
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            last_err = e
        except Exception as e:
            raise LLMError(f"调用本地大模型失败：{e}") from e
    raise LLMError(f"大模型输出格式异常（已重试{config.ANALYZE_RETRY}次）：{last_err}")


def generate_formula(question_text):
    """本地知识库未命中时，调用大模型生成临时知识点卡片或澄清反问。
    返回 dict：
      - {"kind": "card", "card": {...}}         完整题目，AI 生成临时卡
      - {"kind": "clarify", "question": "..."}  题目不完整，需要学生补充
      - {"kind": "not_math"}                    非小学数学
    解析失败重试 ANALYZE_RETRY 次，仍失败抛 LLMError。"""
    prompt = prompts.build_generate_formula_prompt(question_text)
    last_err = None
    for _ in range(1 + config.ANALYZE_RETRY):
        try:
            resp = ollama.chat(
                model=config.MODEL_NAME,
                messages=[{"role": "system", "content": prompts.GENERATE_FORMULA_SYSTEM},
                          {"role": "user", "content": prompt}]
                         + ([{"role": "user", "content": f"上次输出未通过校验：{last_err}。请只输出一行有效JSON。"}] if last_err else []),
                format="json",
                options={"temperature": 0, "num_predict": 256},
            )
            data = json.loads(resp["message"]["content"])
            if not isinstance(data, dict):
                raise TypeError("输出必须是 JSON 对象")
            if data.get("is_elementary_math") is False:
                return {"kind": "not_math"}
            if data.get("needs_clarify") is True:
                question = data.get("clarify_question")
                if not isinstance(question, str) or not question.strip():
                    raise TypeError("needs_clarify=true 时必须给出 clarify_question")
                return {"kind": "clarify", "question": question.strip()}
            # 完整卡片路径
            card = {
                "id": None,
                "knowledge_point": data.get("knowledge_point"),
                "formula": data.get("formula"),
                "easy_tip": data.get("easy_tip") or "",
                "grade": data.get("grade") or "",
                "is_temp": True,
            }
            if not isinstance(card["knowledge_point"], str) or not card["knowledge_point"].strip():
                raise TypeError("knowledge_point 不能为空")
            if not isinstance(card["formula"], str) or not card["formula"].strip():
                raise TypeError("formula 不能为空")
            return {"kind": "card", "card": card}
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            last_err = e
        except Exception as e:
            raise LLMError(f"调用本地大模型失败：{e}") from e
    raise LLMError(f"大模型输出格式异常（已重试{config.ANALYZE_RETRY}次）：{last_err}")


def chat_stream(messages):
    """流式对话：逐 chunk yield 文本。服务异常抛 LLMError"""
    try:
        # 辅导状态用于归档，必须在正文交给上层前校验。
        tutor = any(m.get("role") == "system" and "[UNDERSTOOD]" in m.get("content", "") for m in messages)
        if tutor:
            request = list(messages)
            for attempt in range(2):
                resp = ollama.chat(model=config.MODEL_NAME, messages=request,
                                   options={"temperature": 0, "num_predict": 384})
                content = resp["message"]["content"].strip()
                tags = re.findall(r"\[(?:CONTINUE|UNDERSTOOD)\]", content)
                if len(tags) == 1 and re.search(r"\n\[(?:CONTINUE|UNDERSTOOD)\]$", content):
                    yield content
                    return
                request = list(messages) + [{"role": "user", "content":
                    "请重新回复上一条学生消息。正文简短，只问一个问题；最后另起一行写[CONTINUE]或[UNDERSTOOD]，必须保留方括号，不加列表符号。不要因为此格式纠正判定学生已经学会。"}]
            raise LLMError("辅导回复格式不符合约定，请重试")
        stream = ollama.chat(
            model=config.MODEL_NAME, messages=messages, stream=True,
            options={"temperature": 0.2, "num_predict": 512},
        )
        for chunk in stream:
            text = chunk["message"]["content"]
            if text:
                yield text
    except Exception as e:
        raise LLMError(f"调用本地大模型失败：{e}") from e
