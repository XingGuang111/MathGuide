"""Persistent text-model profiles. Secrets never appear in public settings."""
import threading
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Annotated, Literal

import config

SETTINGS_PATH = config.BASE_DIR / 'data' / 'ai-settings.json'
_lock = threading.RLock()


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    provider: Literal['ollama', 'compatible'] = 'ollama'
    ollama_url: str = Field(default='http://127.0.0.1:11434', max_length=500)
    ollama_model: str = Field(default=config.MODEL_NAME, min_length=1, max_length=200)
    base_url: str = Field(default='https://api.deepseek.com/v1', max_length=500)
    online_model: str = Field(default='deepseek-chat', min_length=1, max_length=200)
    api_key: str = Field(default='', max_length=4096)
    ollama_models: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=100)
    online_models: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def include_active_models(self):
        for name, active in (('ollama_models', self.ollama_model), ('online_models', self.online_model)):
            models = list(dict.fromkeys([active, *getattr(self, name)]))
            if len(models) > 100:
                raise ValueError('最多保存 100 个常用模型')
            setattr(self, name, models)
        return self

    @field_validator('ollama_url', 'base_url')
    @classmethod
    def valid_url(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('请填写 http 或 https 服务地址，不要包含密钥、查询参数或片段')
        return value.rstrip('/')

    @field_validator('api_key')
    @classmethod
    def valid_key(cls, value):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('密钥不能包含控制字符')
        return value


class SettingsRequest(ModelSettings):
    # Empty key retains the saved key only for the same endpoint.
    clear_api_key: bool = False


def current():
    with _lock:
        path = Path(SETTINGS_PATH)
        if not path.exists():
            return ModelSettings(ollama_model=config.MODEL_NAME)
        return ModelSettings.model_validate_json(path.read_text(encoding='utf-8'))


def public(settings=None):
    settings = settings or current()
    return {**settings.model_dump(exclude={'api_key'}), 'has_api_key': bool(settings.api_key),
            'vision_model': config.VISION_MODEL_NAME}


def candidate(request):
    saved = current()
    data = request.model_dump(exclude={'clear_api_key'})
    if request.clear_api_key:
        data['api_key'] = ''
    elif not request.api_key and request.base_url == saved.base_url:
        data['api_key'] = saved.api_key
    return ModelSettings(**data)


def save(request):
    with _lock:
        settings = candidate(request)
        path = Path(SETTINGS_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(settings.model_dump_json(indent=2), encoding='utf-8')
        temporary.replace(path)
        return public(settings)


def model_name(settings=None):
    settings = settings or current()
    return settings.ollama_model if settings.provider == 'ollama' else settings.online_model
