"""单元测试默认关闭真实模型诊断；诊断测试显式启用并提供mock。"""
import pytest

import config
import model_settings


@pytest.fixture(autouse=True)
def isolated_model_settings(tmp_path, monkeypatch):
    """Keep local saved credentials and model choices out of unit tests."""
    monkeypatch.setattr(model_settings, 'SETTINGS_PATH', tmp_path / 'ai-settings.json')


@pytest.fixture(autouse=True)
def offline_diagnosis(monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIAGNOSIS', False)
    monkeypatch.setattr(config, 'ENABLE_MODEL_OPENING', False)
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIALOGUE', False)
