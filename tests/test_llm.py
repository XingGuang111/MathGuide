# -*- coding: utf-8 -*-
import json
import pytest
from unittest.mock import patch, MagicMock
import llm


def test_check_health_ok():
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.list.return_value = {"models": [{"name": "qwen2.5:1.5b"}]}
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
