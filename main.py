# -*- coding: utf-8 -*-
"""MathGuide 终端入口：REPL 循环与命令分发"""
import json
import sys

import agent as agent_mod
import config
import db
import llm
import ocr

KNOWN_COMMANDS = {"photo", "history", "stats", "new", "help", "quit"}

HELP = """可用命令：
  直接输入题目        开始一轮启发式辅导
  /photo 图片路径     拍照搜题（OCR 识别后可修正）
  /history            查看全部历史记录
  /history 日期       按日期查看，如 /history 2026-10-08
  /history 题型       按题型查看，如 /history 几何应用题
  /stats              薄弱知识点统计
  /new                放弃当前题目
  /help               查看本帮助
  /quit               退出"""

_BANNER = f"""{'=' * 50}
  MathGuide 小学数学启发式辅导 (模型: {config.MODEL_NAME})
  直接输入题目开始辅导；拍题用 /photo 图片路径
  /help 查看全部命令
{'=' * 50}"""


def parse_command(text):
    """解析斜杠命令 → (命令名, 参数)；普通输入或未知命令返回 ("", None)"""
    text = text.strip()
    if not text.startswith("/"):
        return "", None
    head, _, arg = text[1:].partition(" ")
    head = head.lower()
    if head not in KNOWN_COMMANDS:
        return "", None
    return head, (arg.strip() or None)


def _print_card(result):
    if result["card"]:
        c = result["card"]
        print(f"\n【知识点】{c['knowledge_point']}  【题型】{result['question_type']}")
        print(f"【公式】{c['formula']}")
        print(f"【易错提示】{c['easy_tip']}\n")
    else:
        print(f"\n【题型】{result['question_type']}（未匹配到公式，直接开始辅导）\n")


def _stream_and_print(chunks):
    print("AI老师> ", end="", flush=True)
    for chunk in chunks:
        print(chunk, end="", flush=True)
    print()


def _handle_photo(tutor, arg):
    if not arg:
        print("用法：/photo 图片路径")
        return
    try:
        text = ocr.recognize(arg)
    except ocr.OCRError as e:
        print(f"OCR 失败：{e}\n也可以直接把题目打字发给我。")
        return
    if not text:
        print("没有识别到文字，请换一张更清晰的印刷体题目照片。")
        return
    print(f"\n【OCR 识别结果】\n{text}")
    print("（直接回车确认，或输入修正后的题目）")
    confirm = input("确认> ").strip()
    question = confirm if confirm else text
    _start_tutoring(tutor, question)


def _start_tutoring(tutor, question):
    result = tutor.start_session(question)
    if not result["ok"]:
        print(result["message"])
        return
    _print_card(result)
    _stream_and_print(tutor.begin_guiding())


def _handle_history(arg):
    date, qtype = None, None
    if arg:
        if len(arg) == 10 and arg[4] == "-" and arg[7] == "-":
            date = arg
        else:
            qtype = arg
    rows = db.query_history(date=date, qtype=qtype)
    if not rows:
        print("没有找到相关记录。")
        return
    for i, r in enumerate(rows, 1):
        mark = "✓独立解出" if r["understood"] else "✗老师讲解"
        print(f"[{i}] {r['record_date']} | {r['question_type']} | {r['knowledge_point']} | {mark}")
        print(f"    {r['question_text'][:40]}")
    sel = input("输入序号查看完整对话（直接回车返回）：").strip()
    if sel.isdigit() and 1 <= int(sel) <= len(rows):
        r = rows[int(sel) - 1]
        print(f"\n【公式】{r['formula']}")
        for msg in json.loads(r["dialogue_log"]):
            who = "你" if msg["role"] == "student" else "AI老师"
            print(f"{who}> {msg['content']}")


def _handle_stats():
    stats = db.weak_stats()
    if not stats:
        print("还没有练习记录。")
        return
    print("\n【薄弱知识点统计】（按未独立掌握次数排序）")
    for s in stats:
        print(f"  {s['knowledge_point']}: 共{s['total']}次, 未独立掌握{s['not_understood']}次")


def main():
    tip = llm.check_health()
    if tip:
        print(tip)
        sys.exit(1)
    db.init_db()
    print(_BANNER)
    tutor = agent_mod.TutorAgent()
    while True:
        try:
            guiding = tutor.state == agent_mod.AgentState.GUIDING
            text = input(("你> " if guiding else "题目> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if not text:
            continue
        cmd, arg = parse_command(text)
        if cmd == "quit":
            print("再见！")
            break
        elif cmd == "help":
            print(HELP)
        elif cmd == "new":
            tutor.abort()
            print("好的，换一道题吧。")
        elif cmd == "history":
            _handle_history(arg)
        elif cmd == "stats":
            _handle_stats()
        elif cmd == "photo":
            if guiding:
                print("正在辅导中，先 /new 结束当前题目。")
            else:
                _handle_photo(tutor, arg)
        elif guiding:
            _stream_and_print(tutor.reply(text))
            if tutor.finished:
                print("✔ 本轮辅导已保存")
        else:
            _start_tutoring(tutor, text)


if __name__ == "__main__":
    main()
