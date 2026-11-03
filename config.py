# -*- coding: utf-8 -*-
"""MathGuide 全局配置常量。"""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

# 本地大模型（Ollama）。服务端当前已加载 Qwen2.5-3B Q4_K_M。
MODEL_NAME = "mathguide-qwen25-3b:latest"
VISION_MODEL_NAME = "qwen2.5vl:3b"  # 本地看图模型，用于带图作业；ollama pull qwen2.5vl:3b
VISION_TIMEOUT_SECONDS = 120
PET_CHAT_TIMEOUT_SECONDS = 25
PET_DAILY_PLAY_MINUTES = 10  # 每个学习档案每日玩耍额度；修改后重启服务生效。

# 数据文件路径
DB_PATH = str(BASE_DIR / "data" / "mathguide.db")
FORMULAS_JSON = str(BASE_DIR / "data" / "formulas.json")

# 可直接维护的辅导规则和示例；修改后在下一轮回复时重新读取。
TUTOR_SYSTEM_PATH = BASE_DIR / "docs" / "system prompt.txt"
TUTOR_EXAMPLES_PATH = BASE_DIR / "docs" / "primary_math_tutor.jsonl"
TUTOR_DIALOGUE_PATH = BASE_DIR / "docs" / "Dialogue Example.md"

# 单题最大引导轮数，超过则兜底讲解，防止无限对话
MAX_GUIDE_ROUNDS = 12

# 题目分析 JSON 解析失败重试次数
ANALYZE_RETRY = 1

# 每轮先分析学生，再由模型组织回复；本地规则仅核验事实和约束教学动作。
ENABLE_MODEL_DIAGNOSIS = True
ENABLE_MODEL_DIALOGUE = True
ENABLE_MODEL_OPENING = True  # 结合本题组织首次问句，失败时使用题型相关的安全开场。
DIAGNOSIS_MIN_CONFIDENCE = 0.6
DIAGNOSIS_TIMEOUT_SECONDS = 20

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
