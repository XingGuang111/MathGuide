# -*- coding: utf-8 -*-
"""MathGuide 全局配置常量"""

# 本地大模型（Ollama），可改 "qwen2.5:3b" 获得更好效果
MODEL_NAME = "qwen2.5:1.5b"

# 数据文件路径
DB_PATH = "data/mathguide.db"
FORMULAS_JSON = "data/formulas.json"

# 单题最大引导轮数，超过则兜底讲解，防止无限对话
MAX_GUIDE_ROUNDS = 12

# 题目分析 JSON 解析失败重试次数
ANALYZE_RETRY = 1

# OCR 支持的图片扩展名（小写）
OCR_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}

# 题型枚举（README 定稿 6 类）
QUESTION_TYPES = [
    "计算题",
    "几何应用题",
    "行程应用题",
    "百分数应用题",
    "单位换算题",
    "平均数应用题",
]
