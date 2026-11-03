"""单元测试默认关闭真实模型诊断；诊断测试显式启用并提供mock。"""
import pytest

import config


@pytest.fixture(autouse=True)
def offline_diagnosis(monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIAGNOSIS', False)
    monkeypatch.setattr(config, 'ENABLE_MODEL_OPENING', False)
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIALOGUE', False)
