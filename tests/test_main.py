# -*- coding: utf-8 -*-
import main
import pytest
from unittest.mock import patch


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


@pytest.mark.parametrize('state', list(main.agent_mod.GUIDING_STATES))
def test_terminal_accepts_answers_in_every_guiding_stage(state):
    tutor = main.agent_mod.TutorAgent()
    tutor.state = state
    with patch('main.llm.check_health', return_value=None), \
         patch('main.db.init_db'), \
         patch('main.agent_mod.TutorAgent', return_value=tutor), \
         patch.object(tutor, 'reply', return_value=iter(['继续想一想'])) as reply, \
         patch('builtins.input', side_effect=['学生回答', '/quit']) as read:
        main.main()
    assert read.call_args_list[0].args == ('你> ',)
    reply.assert_called_once_with('学生回答')
