# -*- coding: utf-8 -*-
import main


def test_parse_command_plain_text():
    assert main.parse_command("长方形面积题") == ("", None)


def test_parse_command_known():
    assert main.parse_command("/quit") == ("quit", None)
    assert main.parse_command("/photo D:\\错题\\a.jpg") == ("photo", "D:\\错题\\a.jpg")
    assert main.parse_command("/history 2026-10-08") == ("history", "2026-10-08")
    assert main.parse_command("/history") == ("history", None)


def test_parse_command_unknown_falls_back():
    # 未知斜杠命令按普通文本处理（返回空命令名）
    assert main.parse_command("/xyz abc") == ("", None)
