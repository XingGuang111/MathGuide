# -*- coding: utf-8 -*-
"""RapidOCR 封装：懒加载引擎、图片识别、文本清洗"""
from pathlib import Path

import config


class OCRError(Exception):
    """OCR 不可用（文件不存在/格式不支持/引擎初始化失败）"""


_engine = None  # 懒加载：首次使用时才初始化（导入本模块不占内存）


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
        except Exception as e:
            raise OCRError(f"OCR 引擎初始化失败：{e}") from e
    return _engine


def recognize(image_path):
    """识别图片中的题目文字，返回清洗后的单行文本；识别不到返回空串"""
    path = Path(image_path.strip().strip('"'))
    if not path.exists():
        raise OCRError(f"图片不存在：{path}")
    if path.suffix.lower() not in config.OCR_IMAGE_EXTS:
        raise OCRError(f"不支持的图片格式 {path.suffix}，支持：{' '.join(sorted(config.OCR_IMAGE_EXTS))}")
    engine = _get_engine()
    result, _ = engine(str(path))
    if not result:
        return ""
    lines = [item[1] for item in result]
    return _clean(lines)


def _clean(lines):
    """合并识别行：去空白行、去首尾空白，用空格连接为单行题干"""
    return " ".join(line.strip() for line in lines if line and line.strip())
