# -*- coding: utf-8 -*-
"""Ollama 封装：健康检查、JSON 题目分析、流式对话"""
import json

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
    models = [m.get("name", "") for m in data.get("models", [])]
    if not any(m == config.MODEL_NAME or m.startswith(config.MODEL_NAME) for m in models):
        return (f"本地还没有模型 {config.MODEL_NAME}。\n"
                f"请运行：ollama pull {config.MODEL_NAME}")
    return None


def analyze(question_text, candidates):
    """题目分析：强制 JSON 输出；解析失败重试 ANALYZE_RETRY 次，仍失败抛 LLMError"""
    prompt = prompts.build_analyze_prompt(question_text, candidates)
    last_err = None
    for _ in range(1 + config.ANALYZE_RETRY):
        try:
            resp = ollama.chat(
                model=config.MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                format="json",
            )
            data = json.loads(resp["message"]["content"])
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


def chat_stream(messages):
    """流式对话：逐 chunk yield 文本。服务异常抛 LLMError"""
    try:
        stream = ollama.chat(model=config.MODEL_NAME, messages=messages, stream=True)
        for chunk in stream:
            text = chunk["message"]["content"]
            if text:
                yield text
    except Exception as e:
        raise LLMError(f"调用本地大模型失败：{e}") from e
