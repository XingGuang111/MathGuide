# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch, MagicMock
import ocr


def test_recognize_file_not_found():
    with pytest.raises(ocr.OCRError, match="不存在"):
        ocr.recognize("不存在的图片.jpg")


def test_recognize_bad_extension(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(ocr.OCRError, match="格式"):
        ocr.recognize(str(f))


def test_recognize_success(tmp_path):
    f = tmp_path / "q.jpg"
    f.write_bytes(b"fake")
    fake_engine = MagicMock()
    fake_engine.return_value = (
        [[None, "一个长方形长12米", 0.99], [None, "宽8米，面积是多少？", 0.98]],
        0.5,
    )
    with patch("ocr._get_engine", return_value=fake_engine):
        text = ocr.recognize(str(f))
    assert text == "一个长方形长12米 宽8米，面积是多少？"


def test_recognize_empty_result(tmp_path):
    f = tmp_path / "q.jpg"
    f.write_bytes(b"fake")
    fake_engine = MagicMock()
    fake_engine.return_value = (None, 0.1)
    with patch("ocr._get_engine", return_value=fake_engine):
        assert ocr.recognize(str(f)) == ""


def test_clean_lines():
    assert ocr._clean(["  3.5千米  ", "", "=多少米？ "]) == "3.5千米 =多少米？"
    assert ocr._clean([]) == ""
