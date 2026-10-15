# -*- coding: utf-8 -*-
import json
import pytest
from unittest.mock import patch, MagicMock
import llm
import config


def test_check_health_ok():
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.list.return_value = {"models": [{"name": config.MODEL_NAME}]}
        assert llm.check_health() is None


def test_check_health_service_down():
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.list.side_effect = ConnectionError("refused")
        tip = llm.check_health()
        assert "Ollama" in tip


def test_check_health_model_missing():
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.list.return_value = {"models": [{"name": "other:7b"}]}
        tip = llm.check_health()
        assert "ollama pull" in tip


def test_analyze_parses_json():
    payload = {"is_elementary_math": True, "knowledge_id": 12, "question_type": "几何应用题"}
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.chat.return_value = {"message": {"content": json.dumps(payload, ensure_ascii=False)}}
        result = llm.analyze("长方形花园", "12. 长方形面积")
    assert result["knowledge_id"] == 12
    assert result["is_elementary_math"] is True


def test_analyze_retries_on_bad_json():
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.chat.return_value = {"message": {"content": "这不是JSON"}}
        with pytest.raises(llm.LLMError):
            llm.analyze("题目", "候选")
    assert mock_ollama.chat.call_count == 1 + 1  # 首次 + ANALYZE_RETRY 次重试


def test_chat_stream_yields_chunks():
    chunks = [
        {"message": {"content": "我们"}},
        {"message": {"content": "先想想"}},
    ]
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.chat.return_value = iter(chunks)
        out = "".join(llm.chat_stream([{"role": "user", "content": "hi"}]))
    assert out == "我们先想想"


def test_analyze_rejects_invented_id_then_repairs():
    bad = {"is_elementary_math": True, "knowledge_id": 999, "question_type": "几何应用题"}
    good = dict(bad, knowledge_id=12)
    with patch("llm.ollama") as client:
        client.chat.side_effect = [
            {"message": {"content": json.dumps(bad)}},
            {"message": {"content": json.dumps(good)}},
        ]
        assert llm.analyze("长方形面积", "12. 长方形面积")["knowledge_id"] == 12
        sent = client.chat.call_args.kwargs["messages"]
        assert sent[0]["role"] == "system"
        assert "上次输出未通过校验" in sent[-1]["content"]


def test_analyze_allows_unmatched_math_without_inventing_formula():
    payload = {"is_elementary_math": True, "knowledge_id": None, "question_type": "计算题"}
    with patch("llm.ollama") as client:
        client.chat.return_value = {"message": {"content": json.dumps(payload)}}
        assert llm.analyze("2+3", "12. 长方形面积")["knowledge_id"] is None


def test_analyze_rejects_non_math_with_formula():
    payload = {"is_elementary_math": False, "knowledge_id": 12, "question_type": None}
    with patch("llm.ollama") as client:
        client.chat.return_value = {"message": {"content": json.dumps(payload)}}
        with pytest.raises(llm.LLMError):
            llm.analyze("写作文", "12. 长方形面积")


def test_tutor_repairs_invalid_status_before_returning():
    with patch("llm.ollama") as client:
        client.chat.side_effect = [
            {"message": {"content": "应该怎么求面积？\nCONTINUE"}},
            {"message": {"content": "应该怎么求面积？\n[CONTINUE]"}},
        ]
        result = "".join(llm.chat_stream([
            {"role": "system", "content": "使用[UNDERSTOOD]和[CONTINUE]"},
            {"role": "user", "content": "不会"},
        ]))
        assert result.endswith("\n[CONTINUE]")
        assert client.chat.call_count == 2


def test_tutor_invalid_status_fails_without_exposing_bad_reply():
    with patch("llm.ollama") as client:
        client.chat.return_value = {"message": {"content": "重复的错误标记"}}
        with pytest.raises(llm.LLMError):
            list(llm.chat_stream([{"role": "system", "content": "[UNDERSTOOD]"}]))


def test_generate_formula_returns_card_for_complete_question():
    payload = {"needs_clarify": False, "is_elementary_math": True,
               "knowledge_point": "圆的面积", "formula": "S=πr²",
               "easy_tip": "半径²是r×r", "grade": "六年级上册"}
    with patch("llm.ollama") as client:
        client.chat.return_value = {"message": {"content": json.dumps(payload, ensure_ascii=False)}}
        result = llm.generate_formula("一个圆的半径是5cm，求面积")
    assert result["kind"] == "card"
    card = result["card"]
    assert card["id"] is None
    assert card["is_temp"] is True
    assert card["grade"] == "六年级上册"
    assert card["knowledge_point"] == "圆的面积"


def test_generate_formula_returns_clarify_for_incomplete_question():
    payload = {"needs_clarify": True, "is_elementary_math": True,
               "clarify_question": "题目里没有告诉我们半径是多少，能补上吗？"}
    with patch("llm.ollama") as client:
        client.chat.return_value = {"message": {"content": json.dumps(payload, ensure_ascii=False)}}
        result = llm.generate_formula("圆的面积")
    assert result == {"kind": "clarify", "question": "题目里没有告诉我们半径是多少，能补上吗？"}


def test_generate_formula_returns_not_math():
    payload = {"needs_clarify": False, "is_elementary_math": False}
    with patch("llm.ollama") as client:
        client.chat.return_value = {"message": {"content": json.dumps(payload)}}
        assert llm.generate_formula("帮我解微积分") == {"kind": "not_math"}


def test_generate_formula_retries_on_invalid_json():
    with patch("llm.ollama") as client:
        client.chat.return_value = {"message": {"content": "这不是JSON"}}
        with pytest.raises(llm.LLMError):
            llm.generate_formula("题目")
    assert client.chat.call_count == 1 + config.ANALYZE_RETRY


def test_generate_formula_rejects_card_missing_fields():
    bad = {"needs_clarify": False, "is_elementary_math": True,
           "knowledge_point": "", "formula": "S=πr²"}
    with patch("llm.ollama") as client:
        client.chat.return_value = {"message": {"content": json.dumps(bad)}}
        with pytest.raises(llm.LLMError):
            llm.generate_formula("题目")
