# -*- coding: utf-8 -*-
"""MathGuide 全局配置常量。"""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

# 本地大模型（Ollama）。服务端当前已加载 Qwen2.5-3B Q4_K_M。
MODEL_NAME = "mathguide-qwen25-3b:latest"

# 数据文件路径
DB_PATH = str(BASE_DIR / "data" / "mathguide.db")
FORMULAS_JSON = str(BASE_DIR / "data" / "formulas.json")

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
